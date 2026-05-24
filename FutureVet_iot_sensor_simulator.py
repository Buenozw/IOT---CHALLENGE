import json
import math
import random
import time
import threading
from datetime import datetime, timezone

PET_PROFILES = {
    "Rex": {"species": "dog", "breed": "Labrador", "age_years": 3,
            "baseline_temp": 38.5, "baseline_hr": 90},
    "Luna": {"species": "cat", "breed": "Siamese", "age_years": 5,
             "baseline_temp": 38.3, "baseline_hr": 150},
    "Bolinha": {"species": "dog", "breed": "Poodle", "age_years": 1,
                "baseline_temp": 38.8, "baseline_hr": 110},
}

def simulate_reading(pet_name: str, tick: int) -> dict:
    profile = PET_PROFILES[pet_name]

    
    hour = (tick // 12) % 24
    activity_base = (
        0.2 + 0.6 * abs(math.sin(math.pi * (hour - 6) / 12))
        if 6 <= hour <= 22 else 0.1
    )
    activity = max(0.0, min(1.0, activity_base + random.gauss(0, 0.05)))

    temp = round(profile["baseline_temp"] + activity * 0.8 + random.gauss(0, 0.05), 1)

    hr = int(profile["baseline_hr"] * (0.8 + activity * 0.4) + random.gauss(0, 3))

    alerts = []
    if temp > profile["baseline_temp"] + 1.5:
        alerts.append("HIGH_TEMPERATURE")
    if hr > profile["baseline_hr"] * 1.5:
        alerts.append("ELEVATED_HEART_RATE")
    if activity < 0.05 and 9 <= hour <= 17:
        alerts.append("LOW_ACTIVITY_DAYTIME")

    return {
        "pet_id": pet_name.lower(),
        "pet_name": pet_name,
        "species": profile["species"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sensors": {
            "temperature_celsius": temp,
            "heart_rate_bpm": hr,
            "activity_score": round(activity, 3),
            "steps_last_minute": int(activity * 120),
        },
        "location": {
            "lat": round(-23.5505 + random.gauss(0, 0.001), 6),
            "lng": round(-46.6333 + random.gauss(0, 0.001), 6),
            "accuracy_m": random.randint(3, 15),
        },
        "battery_pct": max(0, 95 - tick // 200),
        "alerts": alerts,
        "health_score": round(100 - len(alerts) * 15 - abs(temp - profile["baseline_temp"]) * 5, 1),
    }

def try_mqtt_publish(payload: dict, topic: str) -> bool:
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(client_id="FutureVet-collar-sim")
        client.connect("broker.hivemq.com", 1883, keepalive=10)
        result = client.publish(topic, json.dumps(payload), qos=1)
        client.disconnect()
        return result.rc == 0
    except Exception:
        return False

READINGS_STORE: list[dict] = []

def http_publish(payload: dict) -> bool:
    READINGS_STORE.append(payload)
    if len(READINGS_STORE) > 500:
        READINGS_STORE.pop(0)
    return True

def run_sensor_loop(duration_seconds: int = 30, interval_seconds: int = 5):
    print("=" * 60)
    print("  FutureVet IoT Sensor Simulator")
    print("  Protocol: MQTT (HiveMQ) with HTTP fallback")
    print("=" * 60)

    tick = 0
    end_time = time.time() + duration_seconds

    while time.time() < end_time:
        for pet_name in PET_PROFILES:
            reading = simulate_reading(pet_name, tick)
            topic = f"FutureVet/sensors/{reading['pet_id']}"

            mqtt_ok = try_mqtt_publish(reading, topic)
            http_publish(reading)

            transport = "MQTT âœ“" if mqtt_ok else "HTTP  âœ“"
            alerts_str = ", ".join(reading["alerts"]) if reading["alerts"] else "â€”"
            print(
                f"[{reading['timestamp'][11:19]}] {pet_name:8s} | "
                f"ðŸŒ¡ {reading['sensors']['temperature_celsius']}Â°C | "
                f"ðŸ’“ {reading['sensors']['heart_rate_bpm']} bpm | "
                f"ðŸƒ {reading['sensors']['activity_score']:.2f} | "
                f"âš¡ {reading['battery_pct']}% | "
                f"ðŸš¨ {alerts_str} | {transport}"
            )

        tick += 1
        time.sleep(interval_seconds)

    print("\nâœ…  Simulation complete.")
    print(f"   {len(READINGS_STORE)} readings stored in local buffer.")
    return READINGS_STORE

if __name__ == "__main__":
    readings = run_sensor_loop(duration_seconds=30, interval_seconds=5)

    sample_path = "/home/claude/FutureVet/sensor_readings_sample.json"
    with open(sample_path, "w") as f:
        json.dump(readings[-30:], f, indent=2, ensure_ascii=False)
    print(f"\nðŸ“„ Sample readings saved â†’ {sample_path}")

