import json
import math
import random
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

MQTT_BROKER    = "broker.hivemq.com"
MQTT_PORT      = 1883
MQTT_TOPIC_SUB = "FutureVet/sensors/#"
MQTT_CLIENT_ID = "FutureVet-server-bridge"

PET_PROFILES = {
    "rex":     {"name": "Rex",     "species": "dog",    "breed": "Labrador", "age": 4,
                "baseline_temp": 38.5, "baseline_hr": 90,  "weight_kg": 28.3},
    "luna":    {"name": "Luna",    "species": "cat",    "breed": "Siamês",   "age": 2,
                "baseline_temp": 38.3, "baseline_hr": 150, "weight_kg": 4.1},
    "bolinha": {"name": "Bolinha", "species": "rabbit", "breed": "Rex",      "age": 1,
                "baseline_temp": 38.8, "baseline_hr": 200, "weight_kg": 2.3},
}

READINGS_BUFFER: dict[str, list[dict]] = {pet: [] for pet in PET_PROFILES}
BUFFER_LOCK     = threading.Lock()
SOURCE_STATUS   = {"mqtt": False, "fallback": True, "last_mqtt_msg": None}
TICK            = 0

def start_mqtt_bridge():
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("[MQTT] paho-mqtt não instalado. Execute: pip install paho-mqtt")
        print("[MQTT] Usando apenas simulador local como fonte de dados.")
        return

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            SOURCE_STATUS["mqtt"] = True
            print(f"[MQTT] ✓ Conectado ao {MQTT_BROKER}:{MQTT_PORT}")
            print(f"[MQTT] Assinando '{MQTT_TOPIC_SUB}' – aguardando dados do Wokwi...")
            client.subscribe(MQTT_TOPIC_SUB, qos=1)
        else:
            print(f"[MQTT] ✗ Falha ao conectar (rc={rc}) – usando fallback local")

    def on_disconnect(client, userdata, rc):
        SOURCE_STATUS["mqtt"] = False
        if rc != 0:
            print(f"[MQTT] Desconectado inesperadamente (rc={rc}) – reconectando...")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())

            parts  = msg.topic.split("/")
            pet_id = parts[-1].lower() if len(parts) >= 3 else payload.get("pet_id", "rex")

            if pet_id not in PET_PROFILES:
                return

            if "timestamp" not in payload:
                payload["timestamp"] = datetime.now(timezone.utc).isoformat()

            payload["_source"] = "wokwi_mqtt"
            SOURCE_STATUS["last_mqtt_msg"] = datetime.now().strftime("%H:%M:%S")

            ts = datetime.now().strftime("%H:%M:%S")
            sensors = payload.get("sensors", {})
            print(
                f"[{ts}] WOKWI→ {pet_id} | "
                f"T:{sensors.get('temperature_celsius','?')}°C | "
                f"HR:{sensors.get('heart_rate_bpm','?')} bpm | "
                f"Score:{payload.get('health_score','?')}"
            )

            with BUFFER_LOCK:
                READINGS_BUFFER[pet_id].append(payload)
                if len(READINGS_BUFFER[pet_id]) > 200:
                    READINGS_BUFFER[pet_id].pop(0)

        except Exception as e:
            print(f"[MQTT] Erro ao processar mensagem: {e}")

    def on_log(client, userdata, level, buf):
        pass

    client = mqtt.Client(client_id=MQTT_CLIENT_ID, clean_session=True)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.on_log        = on_log

    print(f"[MQTT] Conectando a {MQTT_BROKER}:{MQTT_PORT}...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_forever()
    except Exception as e:
        SOURCE_STATUS["mqtt"] = False
        print(f"[MQTT] Não foi possível conectar: {e}")
        print("[MQTT] Usando simulador local como fonte de dados.")

def simulate_reading(pet_id: str, tick: int) -> dict:
    p    = PET_PROFILES[pet_id]
    hour = (tick // 12) % 24

    activity_base = (
        0.2 + 0.6 * abs(math.sin(math.pi * (hour - 6) / 12))
        if 6 <= hour <= 22 else 0.1
    )
    activity = max(0.0, min(1.0, activity_base + random.gauss(0, 0.05)))
    temp     = round(p["baseline_temp"] + activity * 0.8 + random.gauss(0, 0.05), 1)
    hr       = int(p["baseline_hr"] * (0.8 + activity * 0.4) + random.gauss(0, 3))
    steps    = int(activity * 120)

    alerts = []
    if temp > p["baseline_temp"] + 1.5: alerts.append("HIGH_TEMPERATURE")
    if hr > p["baseline_hr"] * 1.5:     alerts.append("ELEVATED_HEART_RATE")
    if activity < 0.05 and 9 <= hour <= 17: alerts.append("LOW_ACTIVITY_DAYTIME")

    return {
        "pet_id":   pet_id,
        "pet_name": p["name"],
        "species":  p["species"],
        "breed":    p["breed"],
        "age":      p["age"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sensors": {
            "temperature_celsius": temp,
            "heart_rate_bpm":      hr,
            "activity_score":      round(activity, 3),
            "steps_last_minute":   steps,
            "weight_kg":           p["weight_kg"],
        },
        "location": {
            "lat": round(-23.5505 + random.gauss(0, 0.001), 6),
            "lng": round(-46.6333 + random.gauss(0, 0.001), 6),
        },
        "battery_pct":  max(0, 95 - tick // 200),
        "health_score": max(0.0, round(100 - len(alerts) * 15 - abs(temp - p["baseline_temp"]) * 5, 1)),
        "alerts":       alerts,
        "protocol":     "HTTP",
        "_source":      "local_simulator",
    }


def fallback_loop(interval: float = 3.0):
    global TICK
    print("[Fallback] Simulador local iniciado (complementa Wokwi quando offline)")
    while True:
        time.sleep(interval)
        TICK += 1
        with BUFFER_LOCK:
            for pet_id in PET_PROFILES:
                buf = READINGS_BUFFER[pet_id]
                last_is_real = (
                    buf and buf[-1].get("_source") == "wokwi_mqtt"
                    and (datetime.now(timezone.utc) -
                         datetime.fromisoformat(buf[-1]["timestamp"])
                         ).total_seconds() < 10
                )
                if not last_is_real:
                    reading = simulate_reading(pet_id, TICK)
                    buf.append(reading)
                    if len(buf) > 200:
                        buf.pop(0)

class FutureVetHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[HTTP {ts}] {fmt % args}")

    def _json(self, data, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path   = urlparse(self.path).path.rstrip("/")
        parts  = [p for p in path.split("/") if p]

        if len(parts) == 3 and parts[:2] == ["api", "latest"]:
            pet_id = parts[2].lower()
            if pet_id not in READINGS_BUFFER:
                return self._json({"error": f"Pet '{pet_id}' não encontrado"}, 404)
            with BUFFER_LOCK:
                buf = READINGS_BUFFER[pet_id]
                self._json(buf[-1] if buf else {})
            return

        if len(parts) == 3 and parts[:2] == ["api", "history"]:
            pet_id = parts[2].lower()
            if pet_id not in READINGS_BUFFER:
                return self._json({"error": f"Pet '{pet_id}' não encontrado"}, 404)
            with BUFFER_LOCK:
                history = [
                    {"timestamp": r["timestamp"],
                     "heart_rate_bpm": r["sensors"]["heart_rate_bpm"],
                     "temperature_celsius": r["sensors"]["temperature_celsius"],
                     "activity_score": r["sensors"]["activity_score"],
                     "_source": r.get("_source", "unknown")}
                    for r in READINGS_BUFFER[pet_id]
                ]
            self._json(history)
            return

        if parts == ["api", "readings"]:
            with BUFFER_LOCK:
                result = {pet: buf[-20:] for pet, buf in READINGS_BUFFER.items()}
            self._json(result)
            return

        if parts == ["api", "status"]:
            with BUFFER_LOCK:
                sources = {}
                for pet, buf in READINGS_BUFFER.items():
                    if buf:
                        last = buf[-1]
                        age  = (datetime.now(timezone.utc) -
                                datetime.fromisoformat(last["timestamp"])).total_seconds()
                        sources[pet] = {
                            "readings": len(buf),
                            "source":   last.get("_source", "unknown"),
                            "last_temp": last["sensors"]["temperature_celsius"],
                            "last_hr":   last["sensors"]["heart_rate_bpm"],
                            "age_seconds": round(age, 1),
                        }
                    else:
                        sources[pet] = {"readings": 0}

            self._json({
                "status": "ok",
                "mqtt_connected": SOURCE_STATUS["mqtt"],
                "last_wokwi_msg": SOURCE_STATUS["last_mqtt_msg"],
                "mqtt_broker": f"{MQTT_BROKER}:{MQTT_PORT}",
                "mqtt_topic":  MQTT_TOPIC_SUB,
                "tick": TICK,
                "pets": sources,
                "tip": "Se mqtt_connected=false, o Wokwi não está rodando ou paho-mqtt não está instalado."
            })
            return

        self._json({"error": "Rota não encontrada", "path": self.path}, 404)

def main():
    HOST, PORT = "localhost", 8080

    print("[FutureVet] Gerando histórico inicial (48 leituras por pet)...")
    for tick_init in range(48):
        for pet_id in PET_PROFILES:
            READINGS_BUFFER[pet_id].append(simulate_reading(pet_id, tick_init))

    t_mqtt = threading.Thread(target=start_mqtt_bridge, daemon=True)
    t_mqtt.start()

    t_fallback = threading.Thread(target=fallback_loop, args=(3.0,), daemon=True)
    t_fallback.start()

    print("=" * 58)
    print("  FutureVet – Servidor HTTP + Bridge MQTT")
    print(f"  API:    http://{HOST}:{PORT}/api/status")
    print(f"  MQTT:   {MQTT_BROKER} → tópico: {MQTT_TOPIC_SUB}")
    print("  Ctrl+C  para encerrar")
    print("=" * 58)
    print()
    print("  Para verificar se o Wokwi está enviando dados:")
    print(f"  → Abra http://{HOST}:{PORT}/api/status no navegador")
    print('  → Procure: "mqtt_connected": true')
    print('  →          "source": "wokwi_mqtt"')
    print()

    server = HTTPServer((HOST, PORT), FutureVetHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[FutureVet] Servidor encerrado.")


if __name__ == "__main__":
    main()
