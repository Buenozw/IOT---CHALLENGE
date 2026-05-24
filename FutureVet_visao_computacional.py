import cv2
import numpy as np
import time
import json
import os
import argparse
import math
from datetime import datetime
from collections import defaultdict
from typing import Optional

CFG = {
    "classes_de_interesse": ["dog", "cat"],
    "confianca_minima": 0.45,
    "iou_threshold": 0.5,
    "max_desaparecimento": 40,
    "resolucao": (1280, 720),
    "pasta_snapshots": "snapshots_FutureVet",
    "snapshot_intervalo_frames": 150,
}

COR = {
    "dog":     (0, 229, 160),
    "cat":     (91, 156, 246),
    "default": (255, 201, 71),
    "bg":      (10, 14, 26),
    "surface": (17, 24, 39),
    "muted":   (107, 122, 153),
    "white":   (232, 237, 245),
}

RACAS = {
    "dog": {
        "pequeno":  ["Chihuahua","Poodle Toy","Yorkshire","MaltÃªs","Pinscher"],
        "medio":    ["Beagle","Cocker Spaniel","Border Collie","Shiba Inu","Bulldog"],
        "grande":   ["Labrador","Golden Retriever","Husky","Pastor AlemÃ£o","DÃ¡lmata"],
        "gigante":  ["SÃ£o Bernardo","Rottweiler","Great Dane","Doberman"],
    },
    "cat": {
        "pequeno":  ["SiamÃªs","Devon Rex","Singapura","AbissÃ­nio"],
        "medio":    ["Persa","Ragdoll","Bengala","AngorÃ¡"],
        "grande":   ["Maine Coon","NorueguÃªs da Floresta","Ragamuffin"],
        "gigante":  ["Maine Coon adulto"],
    },
}

class PetTracker:
    def __init__(self, max_miss: int = 40):
        self.next_id = 0
        self.objects: dict[int, np.ndarray] = {}
        self.missed: dict[int, int] = {}
        self.history: dict[int, list] = defaultdict(list)
        self.labels: dict[int, str] = {}
        self.max_miss = max_miss

    def update(self, rects: list, labels: list) -> dict[int, np.ndarray]:
        if not rects:
            for pid in list(self.missed):
                self.missed[pid] += 1
                if self.missed[pid] > self.max_miss:
                    del self.objects[pid]
                    del self.missed[pid]
            return self.objects

        centroids = np.array([[(x1+x2)//2, (y1+y2)//2] for x1,y1,x2,y2 in rects], dtype=float)

        if not self.objects:
            for i, c in enumerate(centroids):
                self._register(c, labels[i] if i < len(labels) else "unknown")
        else:
            ids = list(self.objects.keys())
            existing = np.array(list(self.objects.values()))
            D = np.linalg.norm(existing[:,None] - centroids[None,:], axis=2)
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]
            used_r, used_c = set(), set()
            for r, c in zip(rows, cols):
                if r in used_r or c in used_c:
                    continue
                pid = ids[r]
                self.objects[pid] = centroids[c]
                self.missed[pid] = 0
                self._add_history(pid, centroids[c])
                if c < len(labels):
                    self.labels[pid] = labels[c]
                used_r.add(r); used_c.add(c)
            for r in set(range(len(ids))) - used_r:
                pid = ids[r]
                self.missed[pid] += 1
                if self.missed[pid] > self.max_miss:
                    del self.objects[pid]; del self.missed[pid]
            for c in set(range(len(centroids))) - used_c:
                self._register(centroids[c], labels[c] if c < len(labels) else "unknown")

        return self.objects

    def _register(self, c, label):
        pid = self.next_id
        self.objects[pid] = c
        self.missed[pid] = 0
        self.labels[pid] = label
        self._add_history(pid, c)
        self.next_id += 1

    def _add_history(self, pid, c):
        self.history[pid].append(c.tolist())
        if len(self.history[pid]) > 80:
            self.history[pid].pop(0)

def encontrar_camera() -> Optional[int]:
    for idx in range(5):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None and frame.size > 0:
                print(f"âœ… CÃ¢mera encontrada no Ã­ndice {idx}")
                return idx
    return None

class DemoScene:
    def __init__(self, w: int, h: int):
        self.w = w
        self.h = h
        self.t = 0.0
        self.pets = [
            {"tipo": "dog", "fase_x": 0.0,   "fase_y": 0.3,  "vel": 0.032, "cor_pelo": (80,110,70),  "cx": w*0.35, "cy": h*0.5, "escala": 1.0},
            {"tipo": "cat", "fase_x": 2.1,   "fase_y": 1.4,  "vel": 0.018, "cor_pelo": (55, 80,130), "cx": w*0.72, "cy": h*0.48,"escala": 0.75},
        ]

    def _desenhar_fundo(self, frame: np.ndarray):
        for y in range(self.h):
            v = int(10 + (y / self.h) * 12)
            frame[y, :] = [v+6, v+9, v+15]

        for x in range(0, self.w, 40):
            cv2.line(frame, (x, 0), (x, self.h), (25, 35, 50), 1)

        for y in range(0, self.h, 40):
            cv2.line(frame, (0, y), (self.w, y), (25, 35, 50), 1)

        cv2.rectangle(frame, (0, int(self.h*0.75)), (self.w, self.h), (20, 30, 42), -1)
        cv2.line(frame, (0, int(self.h*0.75)), (self.w, int(self.h*0.75)), (35, 50, 70), 1)
        cv2.putText(frame, "FutureVet Clinic Cam", (int(self.w*0.35), int(self.h*0.95)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 42, 58), 1, cv2.LINE_AA)

    def _desenhar_cachorro(self, frame: np.ndarray, cx: int, cy: int, escala: float, cor: tuple):
        s = escala
    
        cv2.ellipse(frame, (cx, cy), (int(70*s), int(45*s)), 0, 0, 360, cor, -1)
        
        hx, hy = cx - int(55*s), cy - int(28*s)
        cv2.ellipse(frame, (hx, hy), (int(30*s), int(26*s)), 0, 0, 360, cor, -1)
        
        cv2.ellipse(frame, (hx - int(22*s), hy + int(6*s)), (int(14*s), int(10*s)), 0, 0, 360,
                    tuple(max(0, c-20) for c in cor), -1)
       
        cv2.circle(frame, (hx - int(10*s), hy - int(6*s)), int(4*s), (230,230,230), -1)
        cv2.circle(frame, (hx - int(10*s), hy - int(6*s)), int(2*s), (20,20,20), -1)
      
        pts = np.array([[hx-int(5*s),hy-int(22*s)],[hx+int(10*s),hy-int(38*s)],[hx+int(20*s),hy-int(18*s)]], np.int32)
        cv2.fillPoly(frame, [pts], tuple(max(0,c-15) for c in cor))
        pts2 = np.array([[hx-int(20*s),hy-int(20*s)],[hx-int(35*s),hy-int(36*s)],[hx-int(18*s),hy-int(8*s)]], np.int32)
        cv2.fillPoly(frame, [pts2], tuple(max(0,c-15) for c in cor))
     
        for dx in [-int(40*s), -int(20*s), int(20*s), int(45*s)]:
            lx = cx + dx
            cv2.rectangle(frame, (lx-int(6*s), cy+int(32*s)), (lx+int(6*s), cy+int(55*s)), cor, -1)
   
        tail_pts = np.array([[cx+int(65*s), cy-int(5*s)],
                              [cx+int(85*s), cy-int(28*s)],
                              [cx+int(90*s), cy-int(10*s)]], np.int32)
        cv2.polylines(frame, [tail_pts], False, cor, int(6*s), cv2.LINE_AA)
    
        cv2.ellipse(frame, (cx, cy+int(48*s)), (int(55*s), int(8*s)), 0, 0, 360, (15,22,32), -1)

    def _desenhar_gato(self, frame: np.ndarray, cx: int, cy: int, escala: float, cor: tuple):
        s = escala
      
        cv2.ellipse(frame, (cx, cy), (int(55*s), int(38*s)), 0, 0, 360, cor, -1)
      
        hx, hy = cx - int(48*s), cy - int(25*s)
        cv2.circle(frame, (hx, hy), int(26*s), cor, -1)
   
        cv2.ellipse(frame, (hx - int(16*s), hy + int(8*s)), (int(10*s), int(7*s)), 0, 0, 360,
                    tuple(min(255, c+30) for c in cor), -1)
  
        for ox in [-int(8*s), int(8*s)]:
            cv2.ellipse(frame, (hx+ox, hy-int(4*s)), (int(7*s), int(4*s)), 0, 0, 360, (200,230,200), -1)
            cv2.ellipse(frame, (hx+ox, hy-int(4*s)), (int(3*s), int(4*s)), 0, 0, 360, (15,15,15), -1)

        pts1 = np.array([[hx-int(8*s),hy-int(22*s)],[hx-int(22*s),hy-int(44*s)],[hx+int(8*s),hy-int(22*s)]], np.int32)
        pts2 = np.array([[hx+int(6*s),hy-int(22*s)],[hx+int(20*s),hy-int(44*s)],[hx+int(24*s),hy-int(18*s)]], np.int32)
        cv2.fillPoly(frame, [pts1, pts2], tuple(max(0,c-20) for c in cor))

        for i in range(20):
            angle = math.pi * i / 20
            rx = cx + int(50*s) + int(30*s * math.cos(angle))
            ry = cy - int(5*s) - int(25*s * math.sin(angle))
            cv2.circle(frame, (rx, ry), int(4*s), cor, -1)
 
        for dx in [-int(32*s), -int(15*s), int(15*s), int(35*s)]:
            lx = cx + dx
            cv2.rectangle(frame, (lx-int(5*s), cy+int(28*s)), (lx+int(5*s), cy+int(48*s)), cor, -1)

        cv2.ellipse(frame, (cx, cy+int(42*s)), (int(45*s), int(7*s)), 0, 0, 360, (15,22,32), -1)

    def get_frame(self) -> tuple[np.ndarray, list[dict]]:
        self.t += 1
        frame = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        self._desenhar_fundo(frame)

        deteccoes = []
        for pet in self.pets:
            pet["fase_x"] += pet["vel"]
            pet["fase_y"] += pet["vel"] * 0.7
            cx = int(pet["cx"] + math.sin(pet["fase_x"]) * self.w * 0.18)
            cy = int(pet["cy"] + math.cos(pet["fase_y"]) * self.h * 0.10)
            s = pet["escala"]

            if pet["tipo"] == "dog":
                self._desenhar_cachorro(frame, cx, cy, s, pet["cor_pelo"])
                bw, bh = int(160*s), int(130*s)
            else:
                self._desenhar_gato(frame, cx, cy, s, pet["cor_pelo"])
                bw, bh = int(130*s), int(110*s)

            x1 = max(0, cx - bw//2)
            y1 = max(0, cy - bh//2)
            x2 = min(self.w, cx + bw//2)
            y2 = min(self.h, cy + bh//2)

            conf = 0.88 + math.sin(self.t * 0.05 + cx) * 0.06
            deteccoes.append({
                "classe": pet["tipo"],
                "confianca": round(conf, 2),
                "box": (x1, y1, x2, y2),
            })

        return frame, deteccoes

class FutureVetVision:
    def __init__(self, cfg: dict, forcar_demo: bool = False):
        self.cfg = cfg
        self.tracker = PetTracker(cfg["max_desaparecimento"])
        self.frame_count = 0
        self.fps = 0.0
        self._t0 = time.time()
        self._fc = 0
        self.snapshots = 0
        self.info_por_id: dict[int, dict] = {}
        self.forcar_demo = forcar_demo
        os.makedirs(cfg["pasta_snapshots"], exist_ok=True)

        self.model = None
        self.modo_detector = "simulado"
        if not forcar_demo:
            try:
                from ultralytics import YOLO
                self.model = YOLO("yolov8n.pt")
                self.modo_detector = "yolo"
                print("âœ… YOLOv8n carregado.")
            except Exception:
                print("â„¹ï¸  YOLOv8 nÃ£o disponÃ­vel â€” usando detector de simulaÃ§Ã£o.")

    def _detectar(self, frame: np.ndarray) -> list[dict]:
        if self.model:
            res = self.model(frame, conf=self.cfg["confianca_minima"],
                             iou=self.cfg["iou_threshold"], verbose=False)
            out = []
            for r in res:
                for box in r.boxes:
                    nome = self.model.names[int(box.cls[0])]
                    if nome not in self.cfg["classes_de_interesse"]:
                        continue
                    x1,y1,x2,y2 = map(int, box.xyxy[0])
                    out.append({"classe": nome, "confianca": float(box.conf[0]),
                                "box": (x1,y1,x2,y2)})
            return out
        return [] 

    def _raca(self, classe: str, box_area: float, frame_area: float) -> str:
        prop = box_area / max(frame_area, 1)
        porte = "pequeno" if prop < 0.02 else "medio" if prop < 0.08 else "grande" if prop < 0.18 else "gigante"
        opcoes = RACAS.get(classe, {}).get(porte, ["Indefinido"])
        return opcoes[self.frame_count % len(opcoes)]

    def _draw(self, frame: np.ndarray, deteccoes: list[dict]) -> np.ndarray:
        h, w = frame.shape[:2]
        frame_area = h * w

        rects = [d["box"] for d in deteccoes]
        labels = [d["classe"] for d in deteccoes]
        ids_map = self.tracker.update(rects, labels)

        c2id = {(int(v[0]), int(v[1])): k for k,v in ids_map.items()}

        for det in deteccoes:
            x1,y1,x2,y2 = det["box"]
            cls = det["classe"]
            conf = det["confianca"]
            cor = COR.get(cls, COR["default"])
            cx, cy = (x1+x2)//2, (y1+y2)//2

            pid = min(c2id, key=lambda k: (k[0]-cx)**2+(k[1]-cy)**2, default=None)
            pid = c2id.get(pid)
            raca = self._raca(cls, (x2-x1)*(y2-y1), frame_area)

            if pid is not None:
                self.info_por_id[pid] = {"classe": cls, "raca": raca,
                    "confianca": conf, "ts": datetime.now().isoformat()}

            L = 22
            for px, py, dx, dy in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
                cv2.line(frame, (px, py), (px+dx*L, py), cor, 2)
                cv2.line(frame, (px, py), (px, py+dy*L), cor, 2)


            ov = frame.copy()
            cv2.rectangle(ov, (x1,y1), (x2,y2), cor, 1)
            cv2.addWeighted(ov, 0.25, frame, 0.75, 0, frame)

            if pid is not None and pid in self.tracker.history:
                traj = self.tracker.history[pid]
                for i in range(1, len(traj)):
                    alpha = i / len(traj)
                    c_fade = tuple(int(v*alpha) for v in cor)
                    cv2.line(frame, tuple(map(int,traj[i-1])), tuple(map(int,traj[i])),
                             c_fade, 1, cv2.LINE_AA)

            cv2.circle(frame, (cx,cy), 5, cor, -1)
            cv2.circle(frame, (cx,cy), 9, cor, 1)

            id_txt = f"ID#{pid}" if pid is not None else "ID#?"
            l1 = f"{id_txt} Â· {cls.upper()} Â· {conf:.0%}"
            l2 = f"RaÃ§a estimada: {raca}"
            fs = 0.42
            tw = max(cv2.getTextSize(l1,cv2.FONT_HERSHEY_SIMPLEX,fs,1)[0][0],
                     cv2.getTextSize(l2,cv2.FONT_HERSHEY_SIMPLEX,0.36,1)[0][0]) + 14
            ly = y1 - 40 if y1 > 44 else y2 + 4
            bg = frame.copy()
            cv2.rectangle(bg, (x1, ly), (x1+tw, ly+38), COR["bg"], -1)
            cv2.rectangle(bg, (x1, ly), (x1+tw, ly+38), cor, 1)
            cv2.addWeighted(bg, 0.88, frame, 0.12, 0, frame)
            cv2.putText(frame, l1, (x1+6, ly+15), cv2.FONT_HERSHEY_SIMPLEX,
                        fs, cor, 1, cv2.LINE_AA)
            cv2.putText(frame, l2, (x1+6, ly+31), cv2.FONT_HERSHEY_SIMPLEX,
                        0.36, COR["white"], 1, cv2.LINE_AA)

            bx, by = x1, y2 + (4 if y2 + 14 < h else -14)
            bw_total = x2 - x1
            cv2.rectangle(frame, (bx, by), (bx+bw_total, by+6), COR["surface"], -1)
            cv2.rectangle(frame, (bx, by), (bx+int(bw_total*conf), by+6), cor, -1)

        ov2 = frame.copy()
        cv2.rectangle(ov2, (0,0), (w,38), COR["bg"], -1)
        cv2.addWeighted(ov2, 0.88, frame, 0.12, 0, frame)
        cv2.line(frame, (0,38), (w,38), COR["surface"], 1)

        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        modo_str = f"YOLO v8n" if self.modo_detector == "yolo" else "SIMULADO"
        cv2.putText(frame, "FutureVet", (10, 26),
                    cv2.FONT_HERSHEY_DUPLEX, 0.75, COR["dog"], 1, cv2.LINE_AA)
        cv2.putText(frame, "Vision", (88, 26),
                    cv2.FONT_HERSHEY_DUPLEX, 0.75, COR["white"], 1, cv2.LINE_AA)
        cv2.putText(frame, f"FPS {self.fps:.1f}  |  Pets: {len(deteccoes)}  |  {ts}  |  Detector: {modo_str}",
                    (185, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    COR["muted"], 1, cv2.LINE_AA)
        cv2.putText(frame, "FIAP Â· Disruptive Architectures Â· 1Â°Sprint 2025  [Q=sair  S=snapshot]",
                    (w - 505, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                    (50,60,80), 1, cv2.LINE_AA)

        if deteccoes:
                px = w - 195
                ph = 52 * len(deteccoes) + 12
                pov = frame.copy()
                cv2.rectangle(pov, (px-4, 44), (w-4, 44+ph), COR["surface"], -1)
                cv2.addWeighted(pov, 0.82, frame, 0.18, 0, frame)
                cv2.rectangle(frame, (px-4, 44), (w-4, 44+ph), COR["surface"], 1)
                for i, d in enumerate(deteccoes):
                    cor2 = COR.get(d["classe"], COR["default"])
                    yy = 68 + i * 52
                    cv2.circle(frame, (px+8, yy-8), 5, cor2, -1)
                    cv2.putText(frame, d["classe"].upper(), (px+20, yy-2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, cor2, 1, cv2.LINE_AA)
                    # barra conf
                    blen = int(170 * d["confianca"])
                    cv2.rectangle(frame, (px+4, yy+4), (px+174, yy+14), (30,40,55), -1)
                    cv2.rectangle(frame, (px+4, yy+4), (px+4+blen, yy+14), cor2, -1)
                    cv2.putText(frame, f"{d['confianca']:.0%}",
                                (px+4+blen+4, yy+13), cv2.FONT_HERSHEY_SIMPLEX,
                                0.32, cor2, 1)
                    cv2.putText(frame, self._raca(d["classe"],
                        (d["box"][2]-d["box"][0])*(d["box"][3]-d["box"][1]), w*h),
                        (px+4, yy+28), cv2.FONT_HERSHEY_SIMPLEX, 0.32,
                        COR["muted"], 1, cv2.LINE_AA)

        return frame
    
    def _snapshot(self, frame, deteccoes):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome = f"{self.cfg['pasta_snapshots']}/FutureVet_{ts}_f{self.frame_count}"
        cv2.imwrite(f"{nome}.png", frame)
        meta = {"timestamp": datetime.now().isoformat(), "frame": self.frame_count,
                "pets": len(deteccoes),
                "deteccoes": [{k:v if k!="box" else list(v) for k,v in d.items()} for d in deteccoes]}
        with open(f"{nome}.json","w",encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        self.snapshots += 1
        print(f"ðŸ“¸ Snapshot: {nome}.png ({len(deteccoes)} pet(s))")

    def _upd_fps(self):
        self._fc += 1
        e = time.time() - self._t0
        if e >= 1.0:
            self.fps = self._fc / e
            self._fc = 0; self._t0 = time.time()

    def processar(self, frame: np.ndarray,
                  deteccoes_externas: Optional[list] = None) -> tuple[np.ndarray, list]:
        self.frame_count += 1
        self._upd_fps()
        dets = deteccoes_externas if deteccoes_externas is not None else self._detectar(frame)
        out = self._draw(frame.copy(), dets)
        if self.cfg["salvar_snapshots"] if "salvar_snapshots" in self.cfg else True:
            if dets and self.frame_count % self.cfg["snapshot_intervalo_frames"] == 0:
                self._snapshot(out, dets)
        return out, dets

    def rodar_camera(self, source, salvar: Optional[str] = None):
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print("âŒ NÃ£o foi possÃ­vel abrir a cÃ¢mera. Iniciando modo demo...")
            self.rodar_demo()
            return

        w, h = self.cfg["resolucao"]
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, 30)

        writer = None
        if salvar:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(salvar, fourcc, 30, (w, h))

        print(f"ðŸ“· CÃ¢mera aberta. Q=sair, S=snapshot")
        try:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None or frame.size == 0:
                    print("âš ï¸  Frame vazio â€” cÃ¢mera desconectada?")
                    break
                out, dets = self.processar(frame)
                if writer: writer.write(out)
                cv2.imshow("FutureVet Vision", out)
                k = cv2.waitKey(1) & 0xFF
                if k == ord("q"): break
                if k == ord("s") and dets: self._snapshot(out, dets)
        finally:
            cap.release()
            if writer: writer.release()
            cv2.destroyAllWindows()
            self._relatorio()

    def rodar_demo(self):
        w, h = self.cfg["resolucao"]
        scene = DemoScene(w, h)
        print(f"\nðŸŽ­ Modo DEMO ativo â€” cena sintÃ©tica de clÃ­nica veterinÃ¡ria")
        print(f"   Q=sair  S=snapshot manual\n")
        try:
            while True:
                frame_raw, dets_demo = scene.get_frame()
                if self.model:
                    dets_yolo = self._detectar(frame_raw)
                    dets = dets_yolo if dets_yolo else dets_demo
                else:
                    dets = dets_demo
                out, _ = self.processar(frame_raw, dets)
                cv2.imshow("FutureVet Vision â€” DEMO", out)
                k = cv2.waitKey(33) & 0xFF
                if k == ord("q"): break
                if k == ord("s"): self._snapshot(out, dets)
        finally:
            cv2.destroyAllWindows()
            self._relatorio()

    def rodar_imagem(self, path: str):
        frame = cv2.imread(path)
        if frame is None:
            print(f"âŒ Imagem nÃ£o encontrada: {path}")
            return
        out, dets = self.processar(frame)
        print(f"\nðŸ“Š {len(dets)} pet(s) detectado(s)")
        for i, d in enumerate(dets):
            print(f"   Pet {i+1}: {d['classe']} Â· {d['confianca']:.0%} Â· box={d['box']}")
        self._snapshot(out, dets)
        cv2.imshow("FutureVet Vision â€” Imagem", out)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def _relatorio(self):
        print(f"\n{'â•'*55}")
        print(f"  FutureVet Vision â€” SessÃ£o encerrada")
        print(f"  Frames processados : {self.frame_count}")
        print(f"  Snapshots salvos   : {self.snapshots}")
        print(f"  Pets rastreados    : {len(self.info_por_id)}")
        for pid, info in self.info_por_id.items():
            print(f"    #{pid}: {info['classe']} Â· {info['raca']} Â· {info['confianca']:.0%}")
        print(f"{'â•'*55}\n")

def main():
    parser = argparse.ArgumentParser(description="FutureVet â€” VisÃ£o Computacional")
    parser.add_argument("--source", default=None, help="0=webcam, caminho de vÃ­deo/imagem")
    parser.add_argument("--demo",   action="store_true", help="ForÃ§ar modo demo sem cÃ¢mera")
    parser.add_argument("--image",  action="store_true", help="Processar imagem estÃ¡tica")
    parser.add_argument("--save",   default=None,        help="Salvar saÃ­da em .mp4")
    parser.add_argument("--conf",   type=float, default=0.45, help="ConfianÃ§a mÃ­nima YOLO")
    args = parser.parse_args()

    CFG["confianca_minima"] = args.conf
    vision = FutureVetVision(CFG, forcar_demo=args.demo)

    if args.demo:
        vision.rodar_demo()
        return

    if args.image and args.source:
        vision.rodar_imagem(args.source)
        return

    if args.source is not None:
        src = int(args.source) if args.source.isdigit() else args.source
    else:
        print("ðŸ” Procurando cÃ¢mera disponÃ­vel...")
        src = encontrar_camera()
        if src is None:
            print("ðŸ“· Nenhuma cÃ¢mera encontrada. Iniciando modo DEMO automÃ¡tico.\n")
            vision.rodar_demo()
            return

    vision.rodar_camera(src, salvar=args.save)


if __name__ == "__main__":
    main()

