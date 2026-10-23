import uuid
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from database import Reading, RelayCommand, DeviceConfig

router = APIRouter(
    prefix="/api/electrolink",
    tags=["readings"]
)

class ESP32ReadingPayload(BaseModel):
    deviceId: str
    currentAcs: float
    currentIna: float
    voltage: float
    power: float
    relay: bool
    status: str
    timestamp: int  # Milliseconds since ESP32 boot

@router.post("/readings", status_code=status.HTTP_200_OK)
async def ingest_reading(payload: ESP32ReadingPayload):
    try:
        reading_uuid = str(uuid.uuid4())
        utc_timestamp = datetime.now(timezone.utc)

        Reading.create(
            device_id=payload.deviceId,
            reading_id=reading_uuid,
            voltage=payload.voltage,
            current_acs=payload.currentAcs,
            current_ina=payload.currentIna,
            power=payload.power,
            relay=payload.relay,
            status=payload.status,
            timestamp=utc_timestamp,
            synced=False
        )

        # Look up thresholds from DeviceConfig (pulled from backend via SyncWorker)
        thresholds = {"normalLimit": 0.20, "alertLimit": 0.60}  # defaults
        try:
            cfg = DeviceConfig.get_or_none(DeviceConfig.device_id == payload.deviceId)
            if cfg and cfg.config_json:
                parsed = json.loads(cfg.config_json)
                t = parsed.get("thresholds", {})
                if t.get("normalLimit") is not None and t.get("alertLimit") is not None:
                    thresholds = t
        except Exception:
            pass  # fallback to defaults on any error

        print(f"[Readings] Returning thresholds for {payload.deviceId}: {thresholds}")

        pending_cmd = (RelayCommand
                       .select()
                       .where((RelayCommand.device_id == payload.deviceId) & (RelayCommand.executed == False))
                       .order_by(RelayCommand.created_at.asc())
                       .first())

        response_data = {
            "status": "success",
            "thresholds": thresholds
        }
        if pending_cmd:
            response_data["relayCommand"] = {
                "commandId": pending_cmd.command_id,
                "targetState": pending_cmd.target_state
            }

        return response_data

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save reading: {str(e)}"
        )
