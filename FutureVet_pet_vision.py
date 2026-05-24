import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

PET_CLASSES = {
    15: ("cat",  "Gato",  (255, 140,   0)),
    16: ("dog",  "Cão",   ( 50, 205,  50)),
    17: ("horse", "Cavalo", (138,  43, 226)),
}

def infer_behavior(x1, y1, x2, y2, frame_h, prev_box=None):
    area = (x2 - x1) * (y2 - y1)
    aspect = (x2 - x1) / max(y2 - y1, 1)

    movement = 0.0
    if prev_box:
        cx1, cy1 = (x1 + x2) / 2, (y1 + y2) / 2
        px1, py1 = (prev_box[0] + prev_box[2]) / 2, (prev_box[1] + prev_box[3]) / 2
        movement = ((cx1 - px1) ** 2 + (cy1 - py1) ** 2) ** 0.5

    if movement > 30:
        return "Ativo", (0, 200, 100)
    if aspect > 1.8:
        return "Deitado", (100, 100, 255)
    if y2 > frame_h * 0.85:
        return "Comendo/Bebendo", (0, 220, 220)
    return "Parado", (200, 200, 200)

def draw_detections(frame, detections, frame_count):
    h, w = frame.shape[:2]

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 50), (15, 15, 25), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    ts = datetime.now().strftime("%H:%M:%S")
    cv2.putText(frame, f"FutureVet Vision  |  {ts}  |  Frame #{frame_count}",
                (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    pet_count = len(detections)
    status_color = (0, 200, 80) if pet_count > 0 else (120, 120, 120)
    cv2.putText(frame, f"Pets detectados: {pet_count}",
                (w - 220, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 1, cv2.LINE_AA)

    for det in detections:
        x1, y1, x2, y2 = det["box"]
        color = det["color"]
        conf  = det["confidence"]
        label = det["label_pt"]
        behavior, beh_color = det["behavior"]

        thickness = 2 if conf > 0.7 else 1
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        label_text = f"{label}  {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
        cv2.putText(frame, label_text, (x1 + 4, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)

        cv2.putText(frame, behavior, (x1 + 4, y2 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, beh_color, 1, cv2.LINE_AA)

        score = int(80 + conf * 20)
        score_text = f"Score Saude: {score}"
        cv2.putText(frame, score_text, (x1 + 4, y2 + 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 230, 255), 1, cv2.LINE_AA)
    return frame

def load_detector():
    try:
        from ultralytics import YOLO
        model = YOLO("yolov8n.pt")
        print("✅  YOLOv8n carregado com sucesso.")
        return "yolo", model
    except ImportError:
        print("⚠️   ultralytics não instalado. Usando detector placeholder (OpenCV blob).")
        return "placeholder", None

def detect_yolo(frame, model):
    results = model(frame, verbose=False)[0]
    detections = []
    for box in results.boxes:
        cls_id = int(box.cls[0])
        if cls_id not in PET_CLASSES:
            continue
        conf = float(box.conf[0])
        if conf < 0.4:
            continue
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        label, label_pt, color = PET_CLASSES[cls_id]
        h, _ = frame.shape[:2]
        behavior = infer_behavior(x1, y1, x2, y2, h)
        detections.append({"box": (x1, y1, x2, y2), "label": label,
                            "label_pt": label_pt, "color": color,
                            "confidence": conf, "behavior": behavior})
    return detections

def detect_placeholder(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array([5, 40, 60])
    upper = np.array([30, 200, 220])
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = frame.shape[:2]
    detections = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 2000:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        conf = min(0.99, area / (h * w * 0.15))
        behavior = infer_behavior(x, y, x + bw, y + bh, h)
        detections.append({"box": (x, y, x + bw, y + bh), "label": "dog",
                            "label_pt": "Pet", "color": (50, 205, 50),
                            "confidence": conf, "behavior": behavior})
    return detections[:3]

def generate_demo_frame():

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (40, 45, 55)

    cv2.rectangle(frame, (0, 320), (640, 480), (30, 35, 45), -1)
    cv2.ellipse(frame, (320, 310), (90, 70), 0, 0, 360, (90, 120, 160), -1)
    cv2.circle(frame, (320, 220), 55, (100, 130, 170), -1)

    pts_ear_l = np.array([[275, 200], [255, 155], [295, 190]], np.int32)
    pts_ear_r = np.array([[365, 200], [385, 155], [345, 190]], np.int32)

    cv2.fillPoly(frame, [pts_ear_l, pts_ear_r], (80, 100, 140))
    cv2.circle(frame, (300, 215), 8, (220, 220, 220), -1)
    cv2.circle(frame, (340, 215), 8, (220, 220, 220), -1)
    cv2.circle(frame, (300, 215), 4, (30, 30, 30), -1)
    cv2.circle(frame, (340, 215), 4, (30, 30, 30), -1)
    cv2.ellipse(frame, (320, 235), (10, 7), 0, 0, 360, (50, 50, 50), -1)

    cv2.putText(frame, "DEMO - Simulacao FutureVet", (10, 460),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

    detections = [{
        "box": (230, 160, 410, 385),
        "label": "dog",
        "label_pt": "Cão",
        "color": (50, 205, 50),
        "confidence": 0.92,
        "behavior": infer_behavior(230, 160, 410, 385, 480),
    }]
    return frame, detections

EVENT_LOG: list[dict] = []

def log_event(detections: list, frame_count: int):
    if not detections:
        return
    for det in detections:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "frame": frame_count,
            "species": det["label"],
            "confidence": round(det["confidence"], 3),
            "behavior": det["behavior"][0],
            "box": det["box"],
        }
        EVENT_LOG.append(entry)
        if len(EVENT_LOG) > 1000:
            EVENT_LOG.pop(0)

def main():
    parser = argparse.ArgumentParser(description="FutureVet Computer Vision")
    parser.add_argument("--source", default="0", help="Video source: 0=webcam, path to file")
    parser.add_argument("--demo",   action="store_true", help="Run demo mode (no camera needed)")
    parser.add_argument("--output", default="vision_output.jpg",
                        help="Path to save output frame")
    args = parser.parse_args()

    backend, model = load_detector()

    if args.demo:
        print("\n🐾  FutureVet Vision – MODO DEMO")
        print("   Gerando frame sintético com detecção simulada...\n")
        frame, detections = generate_demo_frame()
        log_event(detections, 1)
        annotated = draw_detections(frame.copy(), detections, 1)
        cv2.imwrite(args.output, annotated)
        print(f"✅  Frame anotado salvo → {args.output}")

        log_path = "vision_events.json"
        with open(log_path, "w") as f:
            json.dump(EVENT_LOG, f, indent=2, ensure_ascii=False)
        print(f"📄  Event log salvo → {log_path}")
        return

    source = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"❌  Não foi possível abrir fonte: {source}")
        sys.exit(1)

    print(f"\n🐾  FutureVet Vision – Fonte: {source}")
    print("   Pressione Q para sair.\n")

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if backend == "yolo":
            detections = detect_yolo(frame, model)
        else:
            detections = detect_placeholder(frame)

        log_event(detections, frame_count)
        annotated = draw_detections(frame.copy(), detections, frame_count)
        cv2.imshow("FutureVet Vision", annotated)

        if frame_count % 30 == 0:
            cv2.imwrite(args.output, annotated)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    log_path = "vision_events.json"
    with open(log_path, "w") as f:
        json.dump(EVENT_LOG, f, indent=2, ensure_ascii=False)
    print(f"\n📄  Event log salvo → {log_path}")


if __name__ == "__main__":
    main()
