import time
import json
import requests
import threading
from datetime import datetime, timezone
import config
from database import Reading, RelayCommand, DeviceConfig, db

class SyncWorker:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[SyncWorker] Started background sync worker.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            print("[SyncWorker] Stopped background sync worker.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                # 1. Sync readings to Cloud Backend
                self._sync_readings()

                # 2. Sync relay command acknowledgments to Cloud Backend
                self._sync_relay_acknowledgments()

                # 3. Pull new relay commands from Cloud Backend
                self._pull_relay_commands()

                # 4. Pull device configurations (thresholds) from Cloud Backend
                self._pull_device_configurations()

            except Exception as e:
                print(f"[SyncWorker] Error in sync cycle: {str(e)}")

            # Sleep for configured interval, waking up if stopped
            self._stop_event.wait(config.SYNC_INTERVAL_SECONDS)

    def _sync_readings(self):
        db.connect(reuse_if_open=True)
        unsynced = Reading.select().where(Reading.synced == False).order_by(Reading.id.asc()).limit(config.SYNC_BATCH_SIZE)
        
        if not unsynced:
            db.close()
            return

        print(f"[SyncWorker] Found {len(unsynced)} unsynced readings. Syncing...")
        for r in unsynced:
            # Format to Cloud Backend IngestReadingResource schema
            payload = {
                "deviceId": r.device_id,
                "readingId": r.reading_id,
                "timestamp": r.timestamp.isoformat(),
                "voltage": r.voltage,
                "current": r.current_acs,
                "currentIna": r.current_ina,
                "powerFactor": 1.0,  # default
                "frequency": 60.0,   # default
                "source": "EdgeDevice"
            }
            try:
                url = f"{config.BACKEND_BASE_URL}/iot/edge/readings"
                headers = {}
                if config.EDGE_API_KEY:
                    headers["X-Api-Key"] = config.EDGE_API_KEY
                res = requests.post(url, json=payload, headers=headers, timeout=5)
                if res.status_code in [200, 204]:
                    r.synced = True
                    r.save()
                else:
                    print(f"[SyncWorker] Ingestion rejected for reading {r.reading_id}: HTTP {res.status_code}. Stopping batch.")
                    break
            except Exception as ex:
                print(f"[SyncWorker] Failed to sync reading {r.reading_id} due to connection error. Retrying later.")
                break
        db.close()

    def _sync_relay_acknowledgments(self):
        db.connect(reuse_if_open=True)
        unsynced_acks = RelayCommand.select().where((RelayCommand.executed == True) & (RelayCommand.synced == False)).order_by(RelayCommand.id.asc())

        if not unsynced_acks:
            db.close()
            return

        print(f"[SyncWorker] Found {len(unsynced_acks)} unsynced relay acknowledgments. Syncing...")
        for ack in unsynced_acks:
            payload = {
                "commandId": ack.command_id,
                "deviceId": ack.device_id,
                "executedSuccessfully": True,
                "executedAt": ack.created_at.isoformat()
            }
            try:
                url = f"{config.BACKEND_BASE_URL}/iot/edge/relay/acknowledge"
                headers = {}
                if config.EDGE_API_KEY:
                    headers["X-Api-Key"] = config.EDGE_API_KEY
                res = requests.post(url, json=payload, headers=headers, timeout=5)
                if res.status_code in [200, 204]:
                    ack.synced = True
                    ack.save()
                else:
                    print(f"[SyncWorker] Acknowledgment rejected for command {ack.command_id}: HTTP {res.status_code}.")
            except Exception as ex:
                print(f"[SyncWorker] Connection error syncing acknowledgment {ack.command_id}. Retrying later.")
                break
        db.close()

    def _pull_relay_commands(self):
        db.connect(reuse_if_open=True)
        # Find distinct device IDs from readings to fetch commands for
        devices = [r.device_id for r in Reading.select(Reading.device_id).distinct()]
        
        # If no devices are logged yet, check a default test device
        if not devices:
            devices = ["dev-electrolink-esp32-01"]

        for device_id in devices:
            try:
                url = f"{config.BACKEND_BASE_URL}/iot/devices/{device_id}/relay/history"
                headers = {}
                if config.EDGE_API_KEY:
                    headers["X-Api-Key"] = config.EDGE_API_KEY
                res = requests.get(url, headers=headers, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    commands = data.get("commands", [])
                    for cmd in commands:
                        cmd_status = cmd.get("status")
                        # We only pull commands that are Pending or Sent
                        if cmd_status in ["Pending", "Sent"]:
                            cmd_id = cmd.get("commandId")
                            target_state = cmd.get("targetRelayState")
                            
                            # Check if we already have this command recorded locally
                            exists = RelayCommand.select().where(RelayCommand.command_id == cmd_id).exists()
                            if not exists:
                                RelayCommand.create(
                                    command_id=cmd_id,
                                    device_id=device_id,
                                    target_state=target_state,
                                    executed=False,
                                    synced=False
                                )
                                print(f"[SyncWorker] Pulled pending relay command from Cloud: {cmd_id} (Target: {target_state})")
            except Exception as ex:
                # Silent fail for pulling, backend might be offline
                pass
        db.close()

    def _pull_device_configurations(self):
        db.connect(reuse_if_open=True)
        devices = [r.device_id for r in Reading.select(Reading.device_id).distinct()]
        if not devices:
            devices = ["dev-electrolink-esp32-01"]

        for device_id in devices:
            try:
                url = f"{config.BACKEND_BASE_URL}/iot/edge/devices/{device_id}/thresholds"
                headers = {}
                if config.EDGE_API_KEY:
                    headers["X-Api-Key"] = config.EDGE_API_KEY
                res = requests.get(url, headers=headers, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    thresholds = data.get("thresholds", {})
                    config_json = json.dumps(data)

                    # Compare with existing to detect changes
                    existing = DeviceConfig.get_or_none(DeviceConfig.device_id == device_id)
                    changed = False
                    if existing and existing.config_json:
                        try:
                            old = json.loads(existing.config_json)
                            old_t = old.get("thresholds", {})
                            if old_t != thresholds:
                                changed = True
                        except Exception:
                            pass

                    if existing:
                        existing.config_json = config_json
                        existing.updated_at = datetime.utcnow()
                        existing.save()
                    else:
                        DeviceConfig.create(
                            device_id=device_id,
                            config_json=config_json
                        )

                    prefix = "Thresholds CHANGED" if changed else "Config pulled"
                    print(f"[SyncWorker] {prefix} for {device_id}: {thresholds}")
                elif res.status_code == 404:
                    print(f"[SyncWorker] No thresholds for device {device_id} (using defaults)")
            except Exception as ex:
                pass
        db.close()
