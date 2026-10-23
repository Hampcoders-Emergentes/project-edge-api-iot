import requests
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import config
from database import RelayCommand

router = APIRouter(
    prefix="/api/electrolink/relay",
    tags=["relay"]
)

class ESP32RelayAckPayload(BaseModel):
    commandId: str
    deviceId: str
    executedSuccessfully: bool
    executedAt: int  # Milliseconds uptime on ESP32

@router.post("/acknowledge", status_code=status.HTTP_200_OK)
async def acknowledge_relay(payload: ESP32RelayAckPayload):
    try:
        # Find local command
        try:
            cmd = RelayCommand.get(RelayCommand.command_id == payload.commandId)
            cmd.executed = True
            cmd.save()
        except RelayCommand.DoesNotExist:
            # If the command wasn't cached locally (e.g. database reset), we still process the ack
            cmd = RelayCommand.create(
                command_id=payload.commandId,
                device_id=payload.deviceId,
                target_state="UNKNOWN",
                executed=True,
                synced=False
            )

        # Attempt to forward to Cloud Backend immediately
        utc_now = datetime.now(timezone.utc).isoformat()
        backend_payload = {
            "commandId": payload.commandId,
            "deviceId": payload.deviceId,
            "executedSuccessfully": payload.executedSuccessfully,
            "executedAt": utc_now
        }

        try:
            url = f"{config.BACKEND_BASE_URL}/iot/edge/relay/acknowledge"
            response = requests.post(url, json=backend_payload, timeout=5)
            if response.status_code in [200, 204]:
                cmd.synced = True
                cmd.save()
                print(f"[RelayAck] Forwarded successfully to Cloud: {payload.commandId}")
            else:
                print(f"[RelayAck] Failed to forward to Cloud (HTTP {response.status_code}). Queued for sync.")
        except Exception as ex:
            print(f"[RelayAck] Cloud Backend offline ({str(ex)}). Queued for sync.")

        return {"status": "success"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process acknowledgment: {str(e)}"
        )
