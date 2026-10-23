import time
import random
import requests

EDGE_API_URL = "http://localhost:3000/api/electrolink"
DEVICE_ID = "electrolink-esp32-01"

print(f"--- ElectroLink ESP32 Device Simulator Started ---")
print(f"Targeting Edge API: {EDGE_API_URL}")
print(f"Device ID: {DEVICE_ID}")
print("-" * 50)

relay_state = False
start_time = time.time()

try:
    while True:
        # Calculate uptime in milliseconds (matching millis() from ESP32)
        uptime_ms = int((time.time() - start_time) * 1000)

        # Generate mock electrical readings
        voltage = 120.0 + random.uniform(-2.0, 2.0)  # ~120V AC
        currentAcs = random.uniform(0.1, 0.8)        # ~0.1 - 0.8 Amps (ACS712)
        currentIna = currentAcs + random.uniform(-0.05, 0.05)  # INA219 mas preciso, ligeramente distinto
        power = voltage * currentAcs                 # Watts
        
        # Determine simple threshold alert status
        status_text = "NORMAL"
        if currentAcs > 0.6:
            status_text = "DANGER"
        elif currentAcs > 0.2:
            status_text = "ALERT"

        payload = {
            "deviceId": DEVICE_ID,
            "currentAcs": round(currentAcs, 3),
            "currentIna": round(currentIna, 3),
            "voltage": round(voltage, 1),
            "power": round(power, 2),
            "relay": relay_state,
            "status": status_text,
            "timestamp": uptime_ms
        }

        print(f"\n[ESP32] Sending Reading:")
        print(f"  Voltage: {payload['voltage']}V | ACS: {payload['currentAcs']}A | INA: {payload['currentIna']}A | Power: {payload['power']}W | Relay: {payload['relay']} | Status: {payload['status']}")

        try:
            res = requests.post(f"{EDGE_API_URL}/readings", json=payload, timeout=3)
            if res.status_code == 200:
                data = res.json()
                print(f"[Edge Response] Success: {data}")
                
                # Check for pending relay command
                if "relayCommand" in data:
                    cmd = data["relayCommand"]
                    cmd_id = cmd["commandId"]
                    target_state = cmd["targetState"]
                    
                    print(f"[ESP32] Received Relay Command: {cmd_id} -> Set State: {target_state}")
                    
                    # Apply mock execution
                    relay_state = (target_state == "ON")
                    print(f"[ESP32] Relay state updated to: {relay_state}")

                    # Send Acknowledgment
                    ack_payload = {
                        "commandId": cmd_id,
                        "deviceId": DEVICE_ID,
                        "executedSuccessfully": True,
                        "executedAt": int((time.time() - start_time) * 1000)
                    }
                    print(f"[ESP32] Sending Acknowledgment for Command: {cmd_id}")
                    ack_res = requests.post(f"{EDGE_API_URL}/relay/acknowledge", json=ack_payload, timeout=3)
                    print(f"[Edge Ack Response] Success: {ack_res.json()}")
            else:
                print(f"[Edge Response] Error {res.status_code}: {res.text}")
        except Exception as ex:
            print(f"[ESP32] Connection to Edge API failed: {str(ex)}")

        time.sleep(5)

except KeyboardInterrupt:
    print("\nSimulator stopped by user.")
