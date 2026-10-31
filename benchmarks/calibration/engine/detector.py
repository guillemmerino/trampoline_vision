"""Adaptador experimental de YOLO; exporta el CSV canònic que ja consumeix track.

La inferència és per fotograma, en ordre, amb paràmetres explícits i pesos
locals. No reutilitza els scripts de TFM ni altera el tracking de producció.
"""

import csv
import math
import time


def original_boxes(rows, original_shape, inference_shape, area_cap=None):
    """Inverteix el resize real, conserva floats i retalla al domini del vídeo."""
    height, width = original_shape
    input_height, input_width = inference_shape
    boxes = []
    for x0, y0, x1, y1, score, category in rows:
        if not all(math.isfinite(float(value)) for value in (x0, y0, x1, y1, score, category)):
            raise ValueError("Non-finite detector output")
        if category != 0 or not 0 <= score <= 1:
            raise ValueError("Expected person detections with scores in [0,1]")
        box = [max(0., min(float(width), float(x0) * width / input_width)),
               max(0., min(float(height), float(y0) * height / input_height)),
               max(0., min(float(width), float(x1) * width / input_width)),
               max(0., min(float(height), float(y1) * height / input_height))]
        if box[0] < box[2] and box[1] < box[3]:
            boxes.append((*box, float(score)))
    if area_cap is not None:
        boxes.sort(key=lambda box: -(box[2] - box[0]) * (box[3] - box[1]))
        boxes = boxes[:area_cap]
    return boxes


def detect(video, settings, weights, destination, device, progress=None):
    import cv2
    import torch
    from ultralytics import YOLO
    from trampoline_vision.ingestion.video_frames import VideoFrameReader

    started = time.perf_counter()
    model = YOLO(str(weights), task="detect")
    reader = VideoFrameReader(video)
    timers = {"decode_s": 0., "resize_s": 0., "predict_s": 0., "csv_s": 0.}
    total = empty = 0
    try:
        with destination.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["frame", "det_id", "x1", "y1", "x2", "y2", "conf", "class_id"])
            for index in range(video.frame_count):
                mark = time.perf_counter()
                image = reader.get(index).to_ndarray(format="bgr24")
                timers["decode_s"] += time.perf_counter() - mark
                mark = time.perf_counter()
                scale = settings["resize_factor"]
                enlarged = cv2.resize(image, (round(video.width_px * scale), round(video.height_px * scale)), interpolation=cv2.INTER_LINEAR) if scale != 1 else image
                timers["resize_s"] += time.perf_counter() - mark
                mark = time.perf_counter()
                with torch.inference_mode():
                    result = model.predict(source=enlarged, conf=settings["confidence"], iou=settings["nms_iou"],
                                           imgsz=settings["imgsz"], classes=[0], max_det=settings["max_det"],
                                           device=device, half=False, rect=True, augment=False, agnostic_nms=False,
                                           save=False, save_txt=False, save_conf=False, verbose=False, stream=False)[0]
                rows = result.boxes.data.detach().cpu().tolist() if result.boxes is not None else []
                timers["predict_s"] += time.perf_counter() - mark
                mark = time.perf_counter()
                boxes = original_boxes(rows, image.shape[:2], enlarged.shape[:2], settings["post_area_cap"])
                for ordinal, box in enumerate(boxes):
                    writer.writerow([index, ordinal, *box, 0])
                total += len(boxes)
                empty += not boxes
                timers["csv_s"] += time.perf_counter() - mark
                if progress and (index % 100 == 0 or index == video.frame_count - 1):
                    progress(index + 1, video.frame_count)
    finally:
        reader.close()
        del model
    return {"frame_count": video.frame_count, "boxes": total, "empty_detection_frames": empty,
            "elapsed_s": time.perf_counter() - started, "timings": timers,
            "timing_scope": "cold_model_load_decode_predict_postprocess_csv; no_overlay",
            "settings": settings, "precision": "float32", "coordinate_policy": "float_original_pixels_clipped_v1"}
