"""Stage 9 frame detection: object detection on frames with OpenCV DNN (YOLO ONNX).

Oct 7 task (M2 AI & Evidence). Finds objects in the extracted video frames
with a YOLO model run through ``cv2.dnn`` and fuses them with the 3D
geometric anomalies: an anomaly whose projected pixel lands inside a
detection bounding box in one of its supporting frames gets its confidence
boosted. This is the frame side of the Oct 10 fusion work; the confidence
update is additive so the v2 report schema stays backward compatible
(only new fields are added, all v1/v2 fields keep working for Hamza's
anomaly panel).

Rules respected
---------------
- OpenCV only (``cv2.dnn.readNetFromONNX``): works on OpenCV 4.8+ and 5.x,
  no torch/ultralytics dependency, no new entries in requirements.txt.
- OFF by default: model weights are not in the repo. Enable with::

      {"stage9": {"use_frame_detection": true, "yolo_model_path": "models/yolov8n.onnx"}}

  or ``--detect --yolo-model models/yolov8n.onnx`` on the CLI.
- Any YOLOv5 / YOLOv8 ONNX export with 80 COCO classes works; both output
  layouts (``(1, N, 85)`` and transposed ``(1, 84, N)``) are handled.

Sampling / cost caps (all configurable under the ``stage9`` config):
``yolo_frame_stride`` (default 2), ``yolo_max_frames`` (default 40),
``max_detections_per_frame`` (default 50).
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import numpy as np

# COCO-80 class names, in model output order.
COCO_LABELS = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
)

# Classes most relevant for drone damage/obstruction surveys. Detections of
# other classes are still recorded, but only these boost anomaly confidence.
RELEVANT_LABELS = frozenset({
    "person", "car", "truck", "bus", "motorcycle", "bicycle", "boat",
    "airplane", "bench", "chair", "couch", "tv", "refrigerator",
})

DETECTION_CONFIG_DEFAULTS = {
    "use_frame_detection": False,
    "yolo_model_path": os.environ.get("YOLO_MODEL_PATH", ""),
    "yolo_conf_threshold": 0.4,
    "yolo_nms_threshold": 0.45,
    "yolo_input_size": 640,
    "yolo_max_frames": 40,
    "yolo_frame_stride": 2,
    "yolo_target": "cpu",               # "cpu" or "cuda"
    "detection_weight": 0.15,           # confidence blend for fused anomalies
    "max_detections_per_frame": 50,
    "max_report_detections_per_frame": 10,
}


def _use_detection_env_flag() -> bool | None:
    for name in ("FLIGHTPRINT_USE_DETECTION", "USE_DETECTION"):
        val = os.environ.get(name)
        if val is not None:
            return val.strip().lower() in ("1", "true", "yes", "on")
    return None


def resolve_detection_config(cfg: dict, explicit: dict | None = None) -> dict:
    """Apply defaults + environment overrides for frame detection (in place).

    Precedence: explicit per-run config > environment > default.
    """
    explicit = explicit or {}
    for key, default in DETECTION_CONFIG_DEFAULTS.items():
        cfg.setdefault(key, default)
    if "use_frame_detection" not in explicit:
        flag = _use_detection_env_flag()
        if flag is not None:
            cfg["use_frame_detection"] = flag
    if "yolo_model_path" not in explicit and os.environ.get("YOLO_MODEL_PATH"):
        cfg["yolo_model_path"] = os.environ["YOLO_MODEL_PATH"]
    return cfg


def download_model(url: str, dest: str | Path) -> Path:
    """Download YOLO ONNX weights to *dest*. The URL must be given explicitly
    (e.g. a YOLOv5/YOLOv8 ``.onnx`` export); there is no default mirror."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, str(dest))
    return dest


# ---------------------------------------------------------------- parsing

def _flatten_nms_indices(indices) -> list[int]:
    if indices is None:
        return []
    try:
        arr = np.asarray(indices).reshape(-1)
        return [int(i) for i in arr if int(i) >= 0]
    except (TypeError, ValueError):
        return []


def parse_detections(outputs: list[np.ndarray], img_w: int, img_h: int,
                      input_size: int, conf_threshold: float,
                      nms_threshold: float,
                      labels: tuple = COCO_LABELS) -> list[dict]:
    """Decode raw YOLO ONNX output(s) into detection dicts.

    Handles both layouts: YOLOv5 ``(1, N, 85)`` rows of
    ``[cx, cy, w, h, obj, cls...]`` and YOLOv8 transposed ``(1, 84, N)``
    rows of ``[cx, cy, w, h, cls...]`` (no objectness score).
    Coordinates are mapped back to the original image size; note the model
    input is a plain resize (no letterbox), so boxes are approximate.
    """
    import cv2

    n_classes = len(labels)
    rows: list[np.ndarray] = []
    has_objectness = False
    for out in outputs:
        arr = np.asarray(out)
        if arr.ndim == 3 and arr.shape[0] == 1:
            arr = arr[0]                      # (N, D) or (D, N)
        if arr.ndim != 2:
            continue
        d0, d1 = arr.shape
        if d1 in (n_classes + 4, n_classes + 5) and d0 not in (n_classes + 4, n_classes + 5):
            pass                              # already (N, D)
        elif d0 in (n_classes + 4, n_classes + 5):
            arr = arr.T                       # transposed (D, N) -> (N, D)
        else:
            continue
        has_objectness = arr.shape[1] == n_classes + 5
        rows.append(arr)
    if not rows:
        return []

    boxes, scores, class_ids = [], [], []
    sx, sy = img_w / input_size, img_h / input_size
    for arr in rows:
        for r in arr:
            cx, cy, w, h = float(r[0]), float(r[1]), float(r[2]), float(r[3])
            if has_objectness:
                obj = float(r[4])
                cls_scores = r[5:5 + n_classes]
            else:
                obj = 1.0
                cls_scores = r[4:4 + n_classes]
            cid = int(np.argmax(cls_scores))
            conf = obj * float(cls_scores[cid])
            if conf < conf_threshold:
                continue
            x = (cx - w / 2) * sx
            y = (cy - h / 2) * sy
            boxes.append([x, y, w * sx, h * sy])
            scores.append(conf)
            class_ids.append(cid)

    keep = _flatten_nms_indices(
        cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, nms_threshold) if boxes else None
    )
    dets = []
    for i in keep:
        x, y, w, h = boxes[i]
        dets.append({
            "bbox": [round(float(x), 1), round(float(y), 1),
                     round(float(w), 1), round(float(h), 1)],
            "class_id": class_ids[i],
            "class_name": labels[class_ids[i]],
            "confidence": round(float(scores[i]), 3),
        })
    dets.sort(key=lambda d: d["confidence"], reverse=True)
    return dets


# ---------------------------------------------------------------- detector

class FrameDetector:
    """YOLO ONNX object detector backed by ``cv2.dnn`` (CPU or CUDA)."""

    def __init__(self, model_path: str | Path, input_size: int = 640,
                 target: str = "cpu"):
        import cv2

        self.model_path = str(model_path)
        self.input_size = int(input_size)
        net = cv2.dnn.readNetFromONNX(self.model_path)
        if target == "cuda":
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        else:
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.net = net

    def detect_image(self, image: np.ndarray, conf_threshold: float = 0.4,
                     nms_threshold: float = 0.45) -> list[dict]:
        import cv2

        h, w = image.shape[:2]
        blob = cv2.dnn.blobFromImage(image, 1.0 / 255.0,
                                     (self.input_size, self.input_size),
                                     swapRB=True, crop=False)
        self.net.setInput(blob)
        outputs = self.net.forward(self.net.getUnconnectedOutLayersNames())
        if isinstance(outputs, np.ndarray):
            outputs = [outputs]
        return parse_detections(list(outputs), w, h, self.input_size,
                                conf_threshold, nms_threshold)

    def detect_frame(self, frame_path: str | Path, conf_threshold: float = 0.4,
                     nms_threshold: float = 0.45) -> list[dict] | None:
        """Detect objects in an image file. Returns None if unreadable."""
        import cv2

        img = cv2.imread(str(frame_path))
        if img is None:
            return None
        return self.detect_image(img, conf_threshold, nms_threshold)


# ---------------------------------------------------------------- running + fusion

def run_frame_detection(frame_paths: list, config: dict,
                        detector: "FrameDetector | None" = None,
                        log=None) -> dict[int, list[dict]]:
    """Run detection over sampled frames. Returns {frame_index: detections}.

    *detector* may be injected (tests, custom models); otherwise a
    :class:`FrameDetector` is built from ``yolo_model_path``. Frames are
    sampled with ``yolo_frame_stride`` and capped at ``yolo_max_frames``.
    """
    cfg = {**DETECTION_CONFIG_DEFAULTS, **(config or {})}
    paths = list(frame_paths or [])
    stride = max(1, int(cfg["yolo_frame_stride"]))
    max_frames = max(1, int(cfg["yolo_max_frames"]))
    sampled = list(range(0, len(paths), stride))[:max_frames]

    if detector is None:
        model = str(cfg["yolo_model_path"] or "")
        if not model or not Path(model).exists():
            raise FileNotFoundError(
                f"YOLO model not found: {model!r}. Set stage9.yolo_model_path "
                "to a YOLOv5/YOLOv8 .onnx file (see download_model).")
        detector = FrameDetector(model, cfg["yolo_input_size"], cfg["yolo_target"])

    conf_thr = float(cfg["yolo_conf_threshold"])
    nms_thr = float(cfg["yolo_nms_threshold"])
    per_frame_cap = max(1, int(cfg["max_detections_per_frame"]))
    out: dict[int, list[dict]] = {}
    for i in sampled:
        try:
            dets = detector.detect_frame(paths[i], conf_thr, nms_thr) \
                if hasattr(detector, "detect_frame") else detector(str(paths[i]))
        except Exception as e:
            if log:
                log.warning(f"Detection failed on frame {i}: {e}")
            continue
        if dets:
            out[i] = list(dets)[:per_frame_cap]
    return out


def point_in_bbox(pixel: list[float], bbox: list[float]) -> bool:
    x, y, w, h = bbox
    return x <= pixel[0] <= x + w and y <= pixel[1] <= y + h


def fuse_detections(anomalies: list[dict], frame_detections: dict[int, list[dict]],
                    weight: float = 0.15,
                    relevant: frozenset = RELEVANT_LABELS) -> int:
    """Fuse frame detections with 3D anomalies (in place).

    For each anomaly, every supporting frame's detections are checked: a
    detection whose bbox contains the anomaly's projected pixel becomes an
    entry of ``anomaly["overlapping_detections"]``. When at least one
    *relevant*-class detection overlaps, confidence is blended upward::

        confidence = (1 - w) * confidence + w * best_detection_confidence

    Anomalies without overlaps are left untouched (the detector only knows
    80 COCO classes, so absence of a detection is not evidence of absence).
    Returns the number of anomalies with at least one overlap.
    """
    fused = 0
    for a in anomalies:
        overlaps = []
        for f in a.get("supporting_frames", []) or []:
            for d in frame_detections.get(f["frame_index"], []) or []:
                if point_in_bbox(f["pixel"], d["bbox"]):
                    overlaps.append({
                        "frame_index": f["frame_index"],
                        "class_name": d["class_name"],
                        "confidence": d["confidence"],
                        "bbox": d["bbox"],
                    })
        a["overlapping_detections"] = overlaps
        support = max(
            (o["confidence"] for o in overlaps if o["class_name"] in relevant),
            default=0.0,
        )
        a["confidence_factors"]["detections"] = round(float(support), 3)
        if support > 0:
            a["confidence"] = round(float(np.clip(
                (1 - weight) * a["confidence"] + weight * support, 0.01, 0.99)), 3)
            fused += 1
    return fused


def detection_summary(frame_detections: dict[int, list[dict]],
                      anomalies: list[dict], per_frame_cap: int = 10) -> dict:
    """Compact, JSON-safe summary of a detection run for the report."""
    return {
        "frames_checked": len(frame_detections),
        "total_detections": sum(len(v) for v in frame_detections.values()),
        "anomalies_with_overlaps": sum(
            1 for a in anomalies if a.get("overlapping_detections")),
        "frame_detections": {
            str(k): v[:per_frame_cap] for k, v in frame_detections.items()
        },
    }
