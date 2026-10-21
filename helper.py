# helper.py
import settings

def format_results(results):
    detections = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls)
            raw_label = settings.CLASSES[cls_id] if cls_id < len(settings.CLASSES) else "Unknown"
            label = settings.NORMALIZATION_MAP.get(raw_label, raw_label)
            confidence = float(box.conf)

            if label in settings.RECYCLABLE:
                category = "Recyclable"
            elif label in settings.HAZARDOUS:
                category = "Hazardous"
            elif label in settings.NON_RECYCLABLE:
                category = "Non-Recyclable"
            else:
                category = "Unknown"

            detections.append({
                "label": label,
                "confidence": round(confidence, 2),
                "category": category
            })
    return detections
