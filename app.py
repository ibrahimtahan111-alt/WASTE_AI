from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy import or_
from flask import request
from twilio.rest import Client
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from ultralytics import YOLO
from pathlib import Path
import cv2, base64, atexit
from datetime import datetime
import openai
import settings, helper
from models import db, User, Detection, FavoriteFacility
import math, os
from settings import SMART_SUGGESTIONS, SMART_DEFAULT
from werkzeug.utils import secure_filename
import base64, json
import secrets
from pathlib import Path
import uuid
# app.py (append near top)
from sqlalchemy import func
import json

# ========= Scheduled WhatsApp Digest (APScheduler) =========
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

import os, tempfile, requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import timedelta
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv
load_dotenv()

import requests  # only used if OLLAMA provider selected
# Map label -> needed tags for matching facilities
LABEL_TAGS = {
    # plastics
    "Clear plastic bottle": ["plastic"], "Plastic bottle cap": ["plastic"],
    "Plastic lid": ["plastic"], "Plastic film": ["plastic"],
    "Single-use carrier bag": ["plastic"],
    # paper/cardboard
    "Paper": ["paper"], "Paper bag": ["paper"], "Paper cup": ["paper"],
    "Corrugated carton": ["paper"], "Pizza box": ["paper"],
    # metal
    "Drink can": ["metal"], "Metal": ["metal"], "Metal lid": ["metal"],
    "Metal bottle cap": ["metal"],
    # glass
    "Glass bottle": ["glass"], "Glass jar": ["glass"], "Glass": ["glass"],
    # e-waste & batteries
    "Battery": ["e-waste","batteries"], "Light bulb": ["e-waste"],
    # medicines / textiles / oil
    "Tissues": [], "Food waste": [],  # examples with no dedicated drop-offs
}

from models import SuggestionCache
from settings import (
    USE_LLM_SUGGESTIONS, LLM_PROVIDER, OPENAI_MODEL, OLLAMA_MODEL,
    SUGGESTION_RULES
)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

# globals at top of app.py
USER_LANG = {}  # phone -> lang
SUPPORTED_LANGS = {"en": "English", "ar": "العربية", "fr": "Français"}
USER_LANG = {}          # e.g. {"+96176726381": "en"}
PENDING_SIGNUPS = {}    # e.g. {"+96176726381": {"step": "ask_name"}}
def _t(msgs: dict, locale: str) -> str:
    return msgs.get(locale, msgs["en"])

def _suggestion_key(label: str, category: str, locale: str = "en"):
    return (label.strip().lower(), category.strip().lower(), locale)

def _fallback_suggestions(label, category, locale="en"):
    # Pick rule by label; if not found, emit a generic template:
    base = SUGGESTION_RULES.get(label, {
        "summary": f"{label} detected.",
        "recycle": [],
        "reuse": [],
        "hazard": [],
        "disposal": []
    })
    return base

def _cache_get(label, category, locale="en"):
    key = _suggestion_key(label, category, locale)
    hit = SuggestionCache.query.filter_by(
        label=key[0], category=key[1], locale=key[2]
    ).first()
    if hit:
        try:
            return json.loads(hit.suggestions_json)
        except Exception:
            return None
    return None

def _cache_put(label, category, locale, payload: dict):
    try:
        rec = SuggestionCache(
            label=label.strip().lower(),
            category=category.strip().lower(),
            locale=locale,
            suggestions_json=json.dumps(payload)
        )
        db.session.add(rec)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    except Exception:
        db.session.rollback()

LLM_SYSTEM = (
    "You are a recycling assistant for Lebanon & MENA context. "
    "Return JSON ONLY (no markdown) with keys: summary (string), recycle (list of strings), "
    "reuse (list of strings), hazard (list of strings), disposal (list of strings). "
    "Keep it short, practical, locally relevant, and safe."
)

def _ollama_generate(prompt: str, model: str) -> str:
    # Minimal Ollama client (local). Expects Ollama running at http://localhost:11434
    resp = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=60
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "").strip()

@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
)
def _llm_json(label: str, category: str, locale="en") -> dict:
    """
    Calls the configured LLM and returns a dict { summary, recycle[], reuse[], hazard[], disposal[] }.
    Falls back to rule-based if the LLM output isn't valid JSON or errors occur.
    """
    prompt = (
        f"Item label: {label}\n"
        f"Category: {category}\n"
        f"Locale: {locale}\n"
        "Return strictly JSON with keys: summary, recycle, reuse, hazard, disposal."
        " No commentary. Keep each list 2-4 bullets, concise."
    )

    try:
        if LLM_PROVIDER.lower() == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": LLM_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                response_format={"type": "json_object"}
            )
            text = resp.choices[0].message.content.strip()

        elif LLM_PROVIDER.lower() == "ollama":
            # Local model via Ollama
            sys = f"<<SYSTEM>>{LLM_SYSTEM}<<END>>\n"
            text = _ollama_generate(sys + prompt, model=OLLAMA_MODEL)

        else:
            return _fallback_suggestions(label, category, locale)

        data = json.loads(text)
        # basic shape guard
        for k in ["summary", "recycle", "reuse", "hazard", "disposal"]:
            if k not in data:
                raise ValueError("Missing key in LLM JSON")
        return data

    except Exception:
        return _fallback_suggestions(label, category, locale)

def generate_suggestions(label: str, category: str, locale: str = "en") -> dict:
    """
    Cached smart suggestions. Reads from DB cache; if miss and LLM enabled, queries LLM; else fallback rules.
    """
    cached = _cache_get(label, category, locale)
    if cached:
        return cached

    if USE_LLM_SUGGESTIONS:
        data = _llm_json(label, category, locale)
    else:
        data = _fallback_suggestions(label, category, locale)

    # Cache & return
    _cache_put(label, category, locale, data)
    return data


def _haversine_km(lat1, lng1, lat2, lng2):
    if None in (lat1, lng1, lat2, lng2):
        return None
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

# ----------------------------
# App Config
# ----------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///wasteai.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB uploads

db.init_app(app)
# Login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_globals():
    return {
        "google_maps_key": os.getenv("GOOGLE_MAPS_KEY", ""),
    }


# ----------------------------
# Globals
# ----------------------------
paused = False
pause_threshold = 0.6
cap = None  # opened lazily via ensure_camera_open()

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

UPLOAD_FOLDER = Path("static/uploads")
RESULTS_FOLDER = UPLOAD_FOLDER / "results"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)

model = YOLO(str(settings.DETECTION_MODEL))
history = []


# ----------------------------
# Camera Helpers
# ----------------------------
def release_camera():
    global cap
    if cap is not None:
        try:
            if cap.isOpened():
                cap.release()
        except Exception:
            pass
        cap = None


def ensure_camera_open():
    """Open webcam reliably (DirectShow on Windows)."""
    global cap
    if cap is not None and cap.isOpened():
        return cap

    release_camera()

    # On Windows, CAP_DSHOW is far more reliable than the default MSMF backend.
    backends = []
    if os.name == "nt":
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    else:
        backends = [cv2.CAP_ANY]

    last_err = None
    for backend in backends:
        try:
            candidate = cv2.VideoCapture(0, backend)
            if candidate is not None and candidate.isOpened():
                # Warm up a few frames — first reads often fail right after open.
                ok = False
                for _ in range(8):
                    ok, _frame = candidate.read()
                    if ok:
                        break
                if ok:
                    cap = candidate
                    app.logger.info(f"Webcam opened with backend={backend}")
                    return cap
                candidate.release()
        except Exception as e:
            last_err = e
            app.logger.warning(f"Webcam backend {backend} failed: {e}")

    app.logger.error(f"Could not open webcam. last_err={last_err}")
    cap = None
    return cap


atexit.register(release_camera)


# ----------------------------
# Auth Routes
# ----------------------------
# ----------------------------
# Auth Helpers
# ----------------------------
def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    cleaned = phone.strip().replace(" ", "")
    return cleaned or None


def format_dt(dt) -> str:
    """Display datetime as dd/mm/yyyy HH:MM:SS."""
    if not dt:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def format_date(dt) -> str:
    """Display date as dd/mm/yyyy."""
    if not dt:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%d/%m/%Y")


def _is_whatsapp_placeholder_email(email: str | None) -> bool:
    if not email:
        return False
    email = email.lower()
    return email.endswith("@wasteai.local") or email.startswith("wa_")


# ----------------------------
# Signup
# ----------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            name = (request.form.get("name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            phone = _normalize_phone(request.form.get("phone"))
            password = request.form.get("password") or ""
            confirm = request.form.get("confirm") or ""

            app.logger.debug(f"Signup attempt: name={name}, email={email}, phone={phone}")

            if not name or not email or not password:
                flash("Please fill in name, email, and password.", "danger")
                return redirect(url_for("signup"))

            if len(password) < 6:
                flash("Password must be at least 6 characters.", "danger")
                return redirect(url_for("signup"))

            if password != confirm:
                flash("Passwords do not match!", "danger")
                return redirect(url_for("signup"))

            existing_email = User.query.filter_by(email=email).first()
            existing_phone = User.query.filter_by(phone=phone).first() if phone else None
            hashed_pw = generate_password_hash(password, method="pbkdf2:sha256")

            # Phone already used by a WhatsApp-created account → link/upgrade it
            if existing_phone and _is_whatsapp_placeholder_email(existing_phone.email):
                if existing_email and existing_email.id != existing_phone.id:
                    flash("Email already registered! Try logging in instead.", "danger")
                    return redirect(url_for("signup"))

                existing_phone.name = name
                existing_phone.email = email
                existing_phone.password_hash = hashed_pw
                db.session.commit()
                app.logger.info(f"✅ Linked WhatsApp account to web login: {email} ({phone})")
                flash("Account linked successfully! You can now log in with your email and password.", "success")
                return redirect(url_for("login"))

            if existing_email:
                flash("Email already registered! Try logging in instead.", "danger")
                return redirect(url_for("signup"))

            if existing_phone:
                flash("This phone number is already registered. Try logging in with that account, or use a different phone.", "danger")
                return redirect(url_for("signup"))

            new_user = User(
                name=name,
                email=email,
                phone=phone,
                password_hash=hashed_pw
            )

            db.session.add(new_user)
            db.session.commit()

            app.logger.info(f"✅ User created: {email} ({phone})")
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            db.session.rollback()
            app.logger.exception("🔥 Signup failed")
            flash(f"Error during signup: {str(e)}", "danger")
            return redirect(url_for("signup"))

    return render_template("signup.html")


# ----------------------------
# Login
# ----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_input = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""

        # ✅ Detect if it's an email or phone
        if "@" in login_input:
            user = User.query.filter_by(email=login_input.lower()).first()
        else:
            user = User.query.filter_by(phone=_normalize_phone(login_input)).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email/phone or password.", "danger")
            return redirect(url_for("login"))

        login_user(user)
        flash("Logged in successfully!", "success")
        return redirect(url_for("index"))

    return render_template("login.html")

# ----------------------------
# Logout
# ----------------------------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("✅ Logged out successfully!", "success")
    return redirect(url_for("login"))
# ----------------------------
# Main + Detection Routes
# ----------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/detect", methods=["POST"])
@login_required
def detect():
    try:
        # ----------------------------
        # Validate file
        # ----------------------------
        if "image" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["image"]
        if not file or not file.filename:
            return jsonify({"error": "Empty filename. Please choose an image."}), 400

        original_name = secure_filename(file.filename)
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return jsonify({
                "error": f"Unsupported file type '{ext or 'unknown'}'. Use JPG, PNG, WEBP, or BMP."
            }), 400

        # Unique name avoids overwriting previous uploads
        filename = f"{uuid.uuid4().hex}{ext}"
        file_path = UPLOAD_FOLDER / filename
        file.save(file_path)

        # ----------------------------
        # Run YOLO model
        # ----------------------------
        results = model.predict(
            str(file_path),
            conf=0.25,
            save=True,
            project=str(RESULTS_FOLDER),
            name="",
            exist_ok=True,
        )

        boxes = results[0].boxes
        detections = []
        CONF_THRESHOLD = 0.70

        # ----------------------------
        # YOLO → structured detections
        # ----------------------------
        if len(boxes) == 0:
            # 🟢 No detections → fallback to OpenAI Vision
            ai_item = _openai_classify_image(str(file_path), locale="en")
            if ai_item["category"] not in ["Recyclable", "Hazardous", "Organic", "Non-recyclable"]:
                ai_item["category"] = _rough_bucket(ai_item["label"].lower())
            detections = [ai_item]

        else:
            for b in boxes:
                try:
                    cls_id = int(b.cls.item())
                    label = model.names[cls_id]
                    conf = float(b.conf.item())
                except Exception:
                    label, conf = "unknown", 0.0

                if conf >= CONF_THRESHOLD:
                    detections.append({
                        "label": label,
                        "category": _rough_bucket(label.lower()),
                        "confidence": conf,
                        "advice": f"Detected with {round(conf*100,1)}% confidence."
                    })
                else:
                    # 🟢 Low confidence → fallback to OpenAI
                    ai_item = _openai_classify_image(str(file_path), locale="en")
                    if ai_item["category"] not in ["Recyclable", "Hazardous", "Organic", "Non-recyclable"]:
                        ai_item["category"] = _rough_bucket(ai_item["label"].lower())
                    detections.append(ai_item)

        # ----------------------------
        # Attach smart suggestions
        # ----------------------------
        uniq = {}
        for d in detections:
            key = (d["label"], d["category"])
            if key not in uniq:
                uniq[key] = generate_suggestions(d["label"], d["category"], locale="en")
            d["suggestions"] = uniq[key]

        # ----------------------------
        # Save to DB
        # ----------------------------
        for d in detections:
            db.session.add(Detection(
                user_id=current_user.id,
                label=d.get("label", "unknown"),
                confidence=d.get("confidence", 0.0),
                category=d.get("category", "Non-recyclable"),  # ✅ never "Unknown"
                snapshot_path=str(file_path)
            ))
        db.session.commit()

        # ----------------------------
        # Get annotated file
        # ----------------------------
        annotated_file = Path(results[0].save_dir) / filename
        if not annotated_file.exists():
            stem = Path(filename).stem
            for f in Path(results[0].save_dir).glob(f"{stem}*"):
                annotated_file = f
                break

        original_url = f"/static/uploads/{filename}"
        annotated_url = f"/{annotated_file.as_posix()}"

        # ----------------------------
        # Maintain last 3 results
        # ----------------------------
        history.append({
            "detections": detections,
            "image": original_url,
            "annotated": annotated_url
        })
        if len(history) > 3:
            history.pop(0)

        # ----------------------------
        # Response
        # ----------------------------
        return jsonify({
            "detections": detections,
            "image": original_url,
            "annotated": annotated_url,
            "history": history
        })

    except Exception as e:
        app.logger.exception("🔥 Error in /detect route")
        return jsonify({"error": str(e)}), 500

@app.route("/webcam_frame")
@login_required
def webcam_frame():
    global paused, cap, pause_threshold
    if paused:
        return jsonify({"paused": True})

    cap = ensure_camera_open()
    if cap is None or not cap.isOpened():
        return jsonify({
            "error": "Could not open webcam. Close other apps using the camera, then try again."
        }), 503

    success, frame = cap.read()
    if not success:
        release_camera()
        cap = ensure_camera_open()
        if cap is None or not cap.isOpened():
            return jsonify({
                "error": "Could not open webcam. Close other apps using the camera, then try again."
            }), 503
        success, frame = cap.read()
        if not success:
            return jsonify({"error": "Failed to read frame from webcam."}), 500

    results = model.predict(frame, conf=0.25, verbose=False)
    detections = helper.format_results(results)

    timestamp = format_dt(datetime.now())
    for d in detections:
        d["timestamp"] = timestamp

    for d in detections:
        new_det = Detection(
            user_id=current_user.id,
            label=d["label"],
            confidence=d["confidence"],
            category=d["category"],
            snapshot_path=None,
        )
        db.session.add(new_det)
    db.session.commit()

    annotated = results[0].plot()
    _, buffer = cv2.imencode(".jpg", annotated)
    img_b64 = base64.b64encode(buffer).decode("utf-8")

    if any(d["confidence"] >= pause_threshold for d in detections):
        paused = True

    return jsonify({"image": img_b64, "detections": detections, "paused": paused})


@app.route("/resume_webcam", methods=["POST"])
@login_required
def resume_webcam():
    """Unpause live detection and ensure the camera is ready."""
    global paused
    paused = False
    cam = ensure_camera_open()
    if cam is None or not cam.isOpened():
        return jsonify({
            "status": "error",
            "error": "Could not open webcam. Close other apps using the camera, then try again."
        }), 503
    return jsonify({"status": "resumed"})


@app.route("/stop_webcam", methods=["POST"])
@login_required
def stop_webcam():
    """Pause and release the camera device."""
    global paused
    paused = True
    release_camera()
    return jsonify({"status": "stopped"})

@app.route("/set_threshold", methods=["POST"])
@login_required
def set_threshold():
    global pause_threshold
    try:
        data = request.get_json()
        pause_threshold = float(data.get("threshold", 0.6))
        return jsonify({"status": "ok", "threshold": pause_threshold})
    except Exception:
        return jsonify({"error": "Invalid threshold"}), 400

# app.py (new routes)

@app.route("/history")
@login_required
def history_page():
    detections = Detection.query.filter_by(user_id=current_user.id).order_by(Detection.timestamp.desc()).all()
    return render_template("history.html", detections=detections)

@app.route("/api/history")
@login_required
def api_history():
    q = Detection.query.filter_by(user_id=current_user.id)
    category = request.args.get("category")
    label = request.args.get("label")
    start = request.args.get("start")  # ISO date
    end = request.args.get("end")
    if category and category != "All":
        q = q.filter(Detection.category == category)
    if label:
        q = q.filter(Detection.label == label)
    if start:
        q = q.filter(Detection.timestamp >= start)
    if end:
        q = q.filter(Detection.timestamp <= end)
    q = q.order_by(Detection.timestamp.desc()).limit(500)

    rows = q.all()
    return jsonify([{
        "id": d.id,
        "timestamp": format_dt(d.timestamp),
        "timestamp_iso": d.timestamp.isoformat(timespec="seconds") if d.timestamp else None,
        "label": d.label,
        "confidence": round(d.confidence*100, 1),
        "category": d.category,
        "snapshot": d.snapshot_path
    } for d in rows])


@app.route("/api/detection/<int:det_id>")
@login_required
def get_detection(det_id):
    d = Detection.query.get_or_404(det_id)
    if d.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({
        "id": d.id,
        "label": d.label,
        "confidence": round(d.confidence, 2),
        "category": d.category,
        "snapshot_path": d.snapshot_path,
        "timestamp": format_dt(d.timestamp),
        "timestamp_iso": d.timestamp.isoformat(timespec="seconds") if d.timestamp else None,
    })

@app.route("/api/facilities")
@login_required
def api_facilities():
    from models import Facility
    label = request.args.get("label", "")
    category = request.args.get("category", "")
    tags = set(LABEL_TAGS.get(label, []))
    if category == "Hazardous":
        tags.update(["e-waste","batteries","hazardous"])
    if category == "Recyclable" and not tags:
        tags.update(["plastic","paper","metal","glass"])

    q = Facility.query
    if tags:
        expr = db.or_(*[Facility.accepts.ilike(f"%{t}%") for t in tags])
        q = q.filter(expr)

    items = q.all()
    return jsonify([{
        "id": f.id, "name": f.name, "address": f.address, "city": f.city,
        "phone": f.phone, "website": f.website, "accepts": f.accepts,
        "pickup": f.pickup, "notes": f.notes,
        "lat": f.lat, "lng": f.lng
    } for f in items])

@app.route("/api/actions/log", methods=["POST"])
@login_required
def api_actions_log():
    from models import DetectionAction
    data = request.get_json() or {}
    action = DetectionAction(
        user_id=current_user.id,
        detection_id=int(data["detection_id"]),
        facility_id=int(data["facility_id"]) if data.get("facility_id") else None,
        action_type=data.get("action_type", "dropoff"),
        user_lat=data.get("user_lat"),
        user_lng=data.get("user_lng"),
    )
    db.session.add(action)
    db.session.commit()
    return jsonify({"status":"ok"})


def seed_facilities():
    from models import Facility
    if Facility.query.count() > 0:
        return

    facilities = [
        {
            "name":"Live Love Recycle (Eco-centers & App)",
            "address":"Beirut, Lebanon",
            "city":"Beirut",
            "phone":"+961 3 113 141",
            "website":"https://livelove.org/",
            "pickup":True,
            "accepts":"plastic,paper,metal,glass,medicines,appliances,textiles,oil",
            "notes":"Use the app for pickup or drop at partner points",
            "lat":33.8886, "lng":35.4955
        },
        {
            "name":"Recycle Beirut - Bir Hassan Warehouse",
            "address":"Embassies Street, Bir Hassan (Jnah), Beirut, Lebanon",
            "city":"Beirut",
            "phone":"",
            "website":"https://recyclebeirut.com/",
            "pickup":True,
            "accepts":"plastic,paper,metal,glass",
            "notes":"Drop-off or paid pickup within Beirut",
            "lat":33.8689, "lng":35.4857
        },
        {
            "name":"arcenciel - Jisr el Wati Center",
            "address":"Emile Lahoud Ave, Jisr el Wati, Sin El Fil, Beirut, Lebanon",
            "city":"Beirut",
            "phone":"+961 1 565 655",
            "website":"https://arcenciel.org/",
            "pickup":False,
            "accepts":"plastic,metal,paper,glass,hazardous",
            "notes":"Also handles medical waste (institutional workflows)",
            "lat":33.8804, "lng":35.5255
        },
        {
            "name":"Lebanon Waste Management - Sad El Bouchrieh",
            "address":"Sad El Bouchrieh, Mount Lebanon, Lebanon",
            "city":"Metn",
            "phone":"+961 81 312 186",
            "website":"https://lebanonwastemanagement.com",
            "pickup":False,
            "accepts":"plastic,paper,metal",
            "notes":"Drive-through drop-off; cash-back/donation model",
            "lat":33.8882, "lng":35.5430
        },
        {
            "name":"Lebanon Waste Management - Mirna Chalouhi",
            "address":"Mirna Chalouhi, Dekwaneh, Mount Lebanon, Lebanon",
            "city":"Metn",
            "phone":"+961 81 312 186",
            "website":"https://lebanonwastemanagement.com",
            "pickup":False,
            "accepts":"plastic,paper,metal",
            "notes":"Drive-through drop-off",
            "lat":33.8868, "lng":35.5423
        },
        {
            "name":"Ecoserv - Zouk Mosbeh Hub",
            "address":"Zouk Mosbeh, Keserwan, Lebanon",
            "city":"Keserwan",
            "phone":"+961 9 220 094",
            "website":"https://ecoservlb.org/",
            "pickup":False,
            "accepts":"e-waste,batteries",
            "notes":"E-waste dropzones countrywide; see map on site",
            "lat":33.9725, "lng":35.5976
        },
        {
            "name":"L’Écoute - Ain Saade Industrial Zone",
            "address":"Ain Saade Industrial Zone, Metn, Lebanon",
            "city":"Metn",
            "phone":"+961 76 176 234",
            "website":"https://www.lecoute-lb.org/",
            "pickup":False,
            "accepts":"plastic,metal,paper,glass,e-waste",
            "notes":"Call for availability/collection; social mission",
            "lat":33.9003, "lng":35.5901
        },
        {
            "name":"Recycle Lebanon - Fassouh Hub",
            "address":"Saint Louise Street, Kehdy Building, Fassouh, Beirut, Lebanon",
            "city":"Beirut",
            "phone":"",
            "website":"https://recyclelebanon.org/",
            "pickup":False,
            "accepts":"textiles,oil,plastic,paper,metal,glass",
            "notes":"Community hub; check availability before drop-off",
            "lat":33.8963, "lng":35.4972
        }
    ]
    db.session.bulk_insert_mappings(Facility, facilities)
    db.session.commit()
    from models import Facility
    if Facility.query.count() > 0:
        return

    # Curated Beirut+area entries (addresses geocoded client-side in Maps)
    facilities = [
        # Live Love Recycle (app + drop-offs + sorting partners)
        {"name":"Live Love Recycle (Eco-centers & App)",
         "address":"Beirut, Lebanon",
         "city":"Beirut","phone":"+961 3 113 141",
         "website":"https://livelove.org/","pickup":True,
         "accepts":"plastic,paper,metal,glass,medicines,appliances,textiles,oil",
         "notes":"Use the app for pickup or drop at partner points"},

        # Recycle Beirut — Bir Hassan/Jnah warehouse drop-off + pickups
        {"name":"Recycle Beirut - Bir Hassan Warehouse",
         "address":"Embassies Street, Bir Hassan (Jnah), Beirut, Lebanon",
         "city":"Beirut","phone":"","website":"https://recyclebeirut.com/","pickup":True,
         "accepts":"plastic,paper,metal,glass",
         "notes":"Drop-off or paid pickup within Beirut"},

        # Arcenciel — Jisr el Wati center (collects plastic, aluminium, paper; medical waste)
        {"name":"arcenciel - Jisr el Wati Center",
         "address":"Emile Lahoud Ave, Jisr el Wati, Sin El Fil, Beirut, Lebanon",
         "city":"Beirut","phone":"+961 1 565 655",
         "website":"https://arcenciel.org/","pickup":False,
         "accepts":"plastic,metal,paper,glass,hazardous",
         "notes":"Also handles medical waste (institutional workflows)"},

        # Lebanon Waste Management — Drive Throw drop-offs + sorting
        {"name":"Lebanon Waste Management - Sad El Bouchrieh",
         "address":"Sad El Bouchrieh, Mount Lebanon, Lebanon",
         "city":"Metn","phone":"+961 81 312 186",
         "website":"https://lebanonwastemanagement.com","pickup":False,
         "accepts":"plastic,paper,metal",
         "notes":"Drive-through drop-off; cash-back/donation model"},

        {"name":"Lebanon Waste Management - Mirna Chalouhi",
         "address":"Mirna Chalouhi, Dekwaneh, Mount Lebanon, Lebanon",
         "city":"Metn","phone":"+961 81 312 186",
         "website":"https://lebanonwastemanagement.com","pickup":False,
         "accepts":"plastic,paper,metal",
         "notes":"Drive-through drop-off"},

        # Ecoserv — e-waste & batteries
        {"name":"Ecoserv - Zouk Mosbeh Hub",
         "address":"Zouk Mosbeh, Keserwan, Lebanon",
         "city":"Keserwan","phone":"+961 9 220 094",
         "website":"https://ecoservlb.org/","pickup":False,
         "accepts":"e-waste,batteries",
         "notes":"E-waste dropzones countrywide; see map on site"},

        # L'Écoute — multi-material + e-waste; large center Ain Saade
        {"name":"L’Écoute - Ain Saade Industrial Zone",
         "address":"Ain Saade Industrial Zone, Metn, Lebanon",
         "city":"Metn","phone":"+961 76 176 234",
         "website":"https://www.lecoute-lb.org/","pickup":False,
         "accepts":"plastic,metal,paper,glass,e-waste",
         "notes":"Call for availability/collection; social mission"},

        # Recycle Lebanon — awareness & zero-waste shop (acceptance varies)
        {"name":"Recycle Lebanon - Fassouh Hub",
         "address":"Saint Louise Street, Kehdy Building, Fassouh, Beirut, Lebanon",
         "city":"Beirut","phone":"","website":"https://recyclelebanon.org/","pickup":False,
         "accepts":"textiles,oil,plastic,paper,metal,glass",
         "notes":"Community hub; check availability before drop-off"},
    ]
    db.session.bulk_insert_mappings(Facility, facilities)
    db.session.commit()

    # app.py extra
# app.py
from settings import IMPACT_FACTORS, DEFAULT_FACTORS


@app.route("/api/suggest")
@login_required
def api_suggest():
    """
    Smart suggestions for a detected item.
    Query params:
      label, category, confidence, lat, lng
    """
    from models import Facility
    label = request.args.get("label", "").strip()
    category = request.args.get("category", "").strip()
    confidence = float(request.args.get("confidence", "0") or 0)
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)

    # 1) Knowledge base
    kb = SMART_SUGGESTIONS.get(label) or SMART_DEFAULT

    # 2) Tag-based facility matching (reuse your LABEL_TAGS)
    tags = set(LABEL_TAGS.get(label, []))
    if category == "Hazardous":
        tags.update(["e-waste", "batteries", "hazardous"])
    if category == "Recyclable" and not tags:
        tags.update(["plastic", "paper", "metal", "glass"])

    q = Facility.query
    if tags:
        expr = db.or_(*[Facility.accepts.ilike(f"%{t}%") for t in tags])
        q = q.filter(expr)

    candidates = q.all()

    # 3) Compute nearest (if user position is provided)
    nearest = None
    if user_lat is not None and user_lng is not None and candidates:
        best = None
        for f in candidates:
            d = _haversine_km(user_lat, user_lng, f.lat, f.lng) if f.lat and f.lng else None
            if d is not None:
                if best is None or d < best[0]:
                    best = (d, f)
        if best:
            dist_km, f = best
            nearest = {
                "id": f.id,
                "name": f.name,
                "address": f.address,
                "lat": f.lat,
                "lng": f.lng,
                "distance_km": round(dist_km, 2),
                "pickup": f.pickup,
                "website": f.website,
                "notes": f.notes
            }

    # 4) Compose checklist dynamically
    checklist = list(kb.get("prep", []))
    if category == "Recyclable":
        checklist.append("Keep it clean & dry to prevent contamination.")
    if category == "Hazardous":
        checklist.append("Use an approved drop-off—never curbside.")
    if confidence < 0.5:
        checklist.append("Low confidence—double-check the item label/symbol.")

    # 5) Response
    return jsonify({
        "label": label,
        "category": category,
        "confidence": round(confidence, 2),
        "risk": kb.get("risk", "low"),
        "prep": kb.get("prep", []),
        "reuse": kb.get("reuse", []),
        "warnings": kb.get("warnings", []),
        "notes": kb.get("notes", ""),
        "checklist": checklist,
        "nearest": nearest
    })


@app.route("/api/impact")
@login_required
def api_impact():
    rows = Detection.query.filter_by(user_id=current_user.id).all()

    stats = {
        "total": len(rows),
        "recyclable": 0,
        "hazardous": 0,
        "non": 0,
        "kg": 0.0,
        "co2": 0.0,
        "energy": 0.0,
        "water": 0.0,
        "trees": 0
    }

    efficiency = 0.6  # assume 60% of recyclable waste is actually processed

    for r in rows:
        if r.category == "Recyclable":
            stats["recyclable"] += 1
        elif r.category == "Hazardous":
            stats["hazardous"] += 1
        elif r.category == "Non-Recyclable":
            stats["non"] += 1

        # Only count impact for recyclable materials
        if r.category == "Recyclable":
            factors = IMPACT_FACTORS.get(r.label, DEFAULT_FACTORS)
            kg = factors["weight"]
            stats["kg"] += kg
            stats["co2"] += kg * factors["co2_perkg"] * efficiency
            stats["energy"] += kg * factors["energy"] * efficiency
            stats["water"] += kg * factors["water"] * efficiency

    # Trees saved: 1 tree ≈ 40kg of recycled paper/cardboard
    stats["trees"] = int(stats["kg"] / 40)

    # Round for UI
    stats["kg"] = round(stats["kg"], 2)
    stats["co2"] = round(stats["co2"], 2)
    stats["energy"] = round(stats["energy"], 1)
    stats["water"] = round(stats["water"], 1)

    return jsonify(stats)

@app.route("/api/badges")
@login_required
def api_badges():
    # Simplified demo: static rules
    rec = Detection.query.filter_by(user_id=current_user.id, category="Recyclable").count()
    haz = Detection.query.filter_by(user_id=current_user.id, category="Hazardous").count()
    badges=[]
    if rec>=10: badges.append({"name":"Plastic Hero","icon":"♻️"})
    if haz>=5: badges.append({"name":"Hazard Tamer","icon":"☣️"})
    if rec+haz>=50: badges.append({"name":"Eco Champion","icon":"🌍"})
    return jsonify(badges)

@app.route("/api/leaderboard")
@login_required
def api_leaderboard():
    q = db.session.query(User.name, func.count(Detection.id).label("count")) \
        .join(Detection, User.id==Detection.user_id) \
        .group_by(User.id).order_by(func.count(Detection.id).desc()).limit(10)
    return jsonify([{"user":u, "detections":c, "points":c*10} for u,c in q])

from sqlalchemy import extract

@app.route("/api/favorites", methods=["GET"])
@login_required
def get_favorites():
    favorites = FavoriteFacility.query.filter_by(user_id=current_user.id).all()
    return jsonify([
        {
            "id": fav.facility.id,
            "name": fav.facility.name,
            "address": fav.facility.address,
            "lat": fav.facility.lat,
            "lng": fav.facility.lng
        }
        for fav in favorites
    ])


@app.route("/api/favorites/<int:facility_id>", methods=["POST"])
@login_required
def add_favorite(facility_id):
    exists = FavoriteFacility.query.filter_by(user_id=current_user.id, facility_id=facility_id).first()
    if not exists:
        fav = FavoriteFacility(user_id=current_user.id, facility_id=facility_id)
        db.session.add(fav)
        db.session.commit()
    return jsonify({"status": "ok"})


@app.route("/api/favorites/<int:facility_id>", methods=["DELETE"])
@login_required
def remove_favorite(facility_id):
    fav = FavoriteFacility.query.filter_by(user_id=current_user.id, facility_id=facility_id).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
    return jsonify({"status": "ok"})

def _format_eco_digest(user, since_dt):
    """Builds a short digest message in the user's locale (fallback en)."""
    locale = getattr(user, "locale", "en")

    # Query stats for time window
    rows = Detection.query.filter(
        Detection.user_id == user.id,
        Detection.timestamp >= since_dt
    ).all()

    if not rows:
        if locale == "ar":
            return "لا توجد عناصر هذا الأسبوع حتى الآن. استمر! 💪"
        elif locale == "fr":
            return "Aucun élément pour l’instant. Continuez ! 💪"
        return "No items yet in this period. Keep it up! 💪"

    total = len(rows)
    rec = sum(1 for r in rows if r.category == "Recyclable")
    haz = sum(1 for r in rows if r.category == "Hazardous")
    non = sum(1 for r in rows if r.category == "Non-Recyclable")

    # Simple impact (reuse your /api/impact factors if you want)
    # Here we just estimate CO2 saved from recyclable count
    co2_saved = round(rec * 0.12, 2)  # ~0.12 kg per recyclable item (toy estimate)
    water_saved = round(rec * 0.5, 1) # ~0.5 L per recyclable item (toy estimate)

    # Badges (same logic as your /api/badges)
    badges = []
    lifetime_rec = Detection.query.filter_by(user_id=user.id, category="Recyclable").count()
    lifetime_haz = Detection.query.filter_by(user_id=user.id, category="Hazardous").count()
    if lifetime_rec >= 10: badges.append("🏅 Plastic Hero")
    if lifetime_haz >= 5: badges.append("☣️ Hazard Tamer")
    if (lifetime_rec + lifetime_haz) >= 50: badges.append("🌍 Eco Champion")

    badges_line = (" \n🏆 " + ", ".join(badges)) if badges else ""

    # Multi-language message
    if locale == "ar":
        return (
            "📊 ملخصك البيئي\n"
            f"- العناصر هذا الفترة: {total}\n"
            f"♻️ قابلة لإعادة التدوير: {rec}\n"
            f"☣️ خطرة: {haz}\n"
            f"🗑️ أخرى: {non}\n"
            f"🌍 ثاني أكسيد الكربون المُوفَّر: ~{co2_saved} كغ\n"
            f"💧 الماء المُوفَّر: ~{water_saved} لتر"
            f"{badges_line}\n\n#Recycle #WasteAI"
        )
    elif locale == "fr":
        return (
            "📊 Récap éco\n"
            f"- Éléments sur la période : {total}\n"
            f"♻️ Recyclable : {rec}\n"
            f"☣️ Dangereux : {haz}\n"
            f"🗑️ Autres : {non}\n"
            f"🌍 CO₂ économisé : ~{co2_saved} kg\n"
            f"💧 Eau économisée : ~{water_saved} L"
            f"{badges_line}\n\n#Recycle #WasteAI"
        )
    else:
        return (
            "📊 Your Eco Digest\n"
            f"- Items this period: {total}\n"
            f"♻️ Recyclable: {rec}\n"
            f"☣️ Hazardous: {haz}\n"
            f"🗑️ Other: {non}\n"
            f"🌍 CO₂ saved: ~{co2_saved} kg\n"
            f"💧 Water saved: ~{water_saved} L"
            f"{badges_line}\n\n#Recycle #WasteAI"
        )

def send_whatsapp_message(to_number: str, body: str):
    """Send a WhatsApp message via Twilio."""
    if not to_number:
        return
    account = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_whatsapp = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    client = Client(account, token)
    client.messages.create(
        from_=from_whatsapp,
        to=f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number,
        body=body
    )

def run_digest_job(period_minutes: int = 3):
    """Find users with phone numbers and send a digest for the last N minutes."""
    since_dt = datetime.utcnow() - timedelta(minutes=period_minutes)
    users = User.query.filter(User.phone.isnot(None)).all()
    for u in users:
        # Twilio Sandbox requires users to have joined your sandbox session
        # (they already did if you tested earlier)
        body = _format_eco_digest(u, since_dt)
        send_whatsapp_message(u.phone, body)

# Create scheduler and start it when app boots (avoid double-start in reloader)
scheduler = BackgroundScheduler(daemon=True)
# Every 3 minutes (testing). Change to cron-like for daily/weekly later.
scheduler.add_job(
    lambda: app.app_context().push() or run_digest_job(3),
    "interval", minutes=300,
    id="whatsapp_digest_every_3min",
    replace_existing=True
)

# We'll start this in __main__ guarded block to avoid duplicate jobs.

@app.route("/api/impact/trend")
@login_required
def api_impact_trend():
    period = request.args.get("period", "week")  # week | month
    q = Detection.query.filter_by(user_id=current_user.id)

    if period == "week":
        # group by day of week
        rows = db.session.query(
            extract("dow", Detection.timestamp).label("dow"),
            func.count(Detection.id)
        ).filter(Detection.user_id==current_user.id) \
         .group_by("dow").all()

        data = [{"day":int(dow), "count":count} for dow,count in rows]

    else:  # month
        rows = db.session.query(
            extract("month", Detection.timestamp).label("month"),
            func.count(Detection.id)
        ).filter(Detection.user_id==current_user.id) \
         .group_by("month").all()

        data = [{"month":int(m), "count":count} for m,count in rows]

    return jsonify(data)


# =========================
# Twilio WhatsApp Route
# =========================
from twilio.rest import Client
import openai, json

# OpenAI credentials (YOLO model already loaded above from weights/best.pt)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Twilio credentials
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
twilio_client = Client(account_sid, auth_token) if account_sid and auth_token else None

# --- Helpers ---

# --- DIY Idea Generator ---
def _generate_diy_idea(item_label, locale="en"):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = f"""
    The user detected a waste item: {item_label}.
    Suggest 1–2 creative DIY reuse ideas for this item.
    Keep it short, practical, and localized for {locale}.
    Format:
    - Idea title
    - 1–2 step instructions
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a creative recycling assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        app.logger.warning(f"⚠️ DIY idea failed: {e}")
        return None

def _generate_diy_image(item_label, idea_text):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        prompt = f"A DIY project idea: {idea_text}. Made from {item_label}. Minimalist photo-style mockup."
        img = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024"  # ✅ valid size
        )

        return img.data[0].url
    except Exception as e:
        app.logger.warning(f"⚠️ DIY image gen failed: {e}")
        return None

def _send_whatsapp(to_number: str, body: str, media_url: str = None):
    """Send WhatsApp text (and optional media) via Twilio REST"""
    if twilio_client is None:
        app.logger.warning("Twilio client not configured; skipping WhatsApp send.")
        return
    msg = twilio_client.messages.create(
        from_=os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"),
        to=f"whatsapp:{to_number}" if not str(to_number).startswith("whatsapp:") else to_number,
        body=body,
        media_url=[media_url] if media_url else None,
    )
    app.logger.info(f"📤 Sent WA msg to {to_number}, SID={msg.sid}, status={msg.status}")

def _send_loading(to_number: str):
    """Send temporary loading message so user knows it's analyzing."""
    _send_whatsapp(to_number, "⏳ Analyzing your image... please wait a few seconds.")

def _classify_items(boxes, locale="en", conf_threshold=0.6):
    """Convert YOLO boxes into structured items, with OpenAI fallback."""
    parsed = []

    def rough_bucket(label_lower: str) -> str:
        if any(k in label_lower for k in ["plastic", "paper", "cardboard", "glass", "can", "aluminum", "metal"]):
            return "Recyclable"
        if any(k in label_lower for k in ["battery", "bulb", "light", "chem", "acid"]):
            return "Hazardous"
        if any(k in label_lower for k in ["food", "organic", "banana", "peel"]):
            return "Organic"
        return "Non-recyclable"

    for b in boxes:
        try:
            cls_id = int(b.cls.item())
            label  = model.names[cls_id]
            conf   = float(b.conf.item())
        except Exception:
            label, conf = "unknown", 0.0

        if conf >= conf_threshold:
            parsed.append({
                "label": label,
                "category": rough_bucket(label.lower()),
                "advice": f"Detected with {round(conf*100,1)}% confidence. Handle accordingly."
            })
        else:
            try:
                resp = openai.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": f"You are a waste management assistant. Reply ONLY in JSON in {locale}."},
                        {"role": "user", "content": (
                            f"Item label: {label} (confidence={conf:.2f}). "
                            "Classify as one of: Recyclable, Hazardous, Organic, Non-recyclable. "
                            "Return JSON: {\"label\":\"...\",\"category\":\"...\",\"advice\":\"1–2 short lines\"}"
                        )}
                    ],
                    response_format={"type": "json_object"}
                )
                ai_item = json.loads(resp.choices[0].message.content)
                ai_item.setdefault("label", label)
                parsed.append(ai_item)
                app.logger.info(f"🤖 OpenAI fallback for {label}: {ai_item}")
            except Exception:
                parsed.append({"label": label, "category": "Unknown", "advice": "Low confidence—please double-check."})

    return parsed

def _rough_bucket(label_lower: str) -> str:
    if any(k in label_lower for k in ["plastic", "paper", "cardboard", "glass", "can", "aluminum", "metal"]):
        return "Recyclable"
    if any(k in label_lower for k in ["battery", "bulb", "light", "chem", "acid"]):
        return "Hazardous"
    if any(k in label_lower for k in ["food", "organic", "banana", "peel"]):
        return "Organic"
    return "Non-recyclable"


def _lookup_facility(parsed_items):
    """Local DB facility lookup (first category), fallback to OpenAI if none found."""
    from models import Facility

    if not parsed_items:
        return None

    first_cat = parsed_items[0].get("category", "").lower()
    if not first_cat:
        return None

    fac = Facility.query.filter(Facility.accepts.ilike(f"%{first_cat}%")).first()
    if fac:
        return {
            "name": fac.name,
            "address": fac.address,
            "phone": fac.phone,
            "lat": fac.lat,
            "lng": fac.lng
        }

    try:
        resp = openai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are a Lebanese recycling assistant. Reply ONLY in JSON."},
                {"role": "user", "content": f"Suggest a public facility in Lebanon for category '{first_cat}'. Return JSON with keys: name, address, advice."}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        app.logger.warning(f"⚠️ Facility lookup failed: {e}")
        return None

def build_whatsapp_body(parsed_items, facility=None, impact=None):
    parts = []
    parts.append("♻️ *WasteAI Detection Report*")

    # Items
    parts.append("\n🔎 *Items Detected:*")
    for it in parsed_items:
        icon = {"Recyclable":"♻️","Hazardous":"☣️","Organic":"🍃","Non-recyclable":"🗑️"}.get(it["category"], "❓")
        parts.append(f"• {icon} {it['label']} → *{it['category']}*\n  _{it['advice']}_")

    # Facility
    if facility:
        fac_line = f"\n📍 *Facility Recommendation:*\n{facility['name']}\n{facility['address']}"
        if facility.get("phone"):
            fac_line += f"\n☎️ {facility['phone']}"
        if facility.get("lat") and facility.get("lng"):
            maps_url = f"https://www.google.com/maps/search/?api=1&query={facility['lat']},{facility['lng']}"
            fac_line += f"\n👉 {maps_url}"
        parts.append(fac_line)

    # Impact
    if impact:
        impact_txt = (
            f"\n🌍 *Eco Impact:*\n"
            f"• Total items: {impact['total']}\n"
            f"• ♻️ Recyclable: {impact['recyclable']}\n"
            f"• ☣️ Hazardous: {impact['hazardous']}\n"
            f"• 🗑️ Other: {impact['non']}"
        )
        parts.append(impact_txt)

    parts.append("\n🔗 Learn more: wasteai.org\n#Recycle #WasteAI")
    return "\n".join(parts)


def _openai_classify_image(image_path, locale="en"):
    """Send image to OpenAI Vision (gpt-4o-mini) and classify waste."""
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        resp = openai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": f"You are a waste classification assistant. Reply ONLY in JSON in {locale}."},
                {"role": "user", "content": "Classify this image of waste into one of: Recyclable, Hazardous, Organic, Non-recyclable. "
                                            "Return JSON: {\"label\":\"...\",\"category\":\"...\",\"advice\":\"...\"}"},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}
            ],
            response_format={"type": "json_object"}
        )

        data = json.loads(resp.choices[0].message.content)
        label = data.get("label", "unknown")
        category = data.get("category", "").strip() or _rough_bucket(label.lower())
        advice = data.get("advice", "Handle responsibly.")

        return {
            "label": label,
            "category": category,
            "advice": advice,
            "confidence": 0.5  # fallback confidence
        }

    except Exception as e:
        app.logger.exception("🔥 OpenAI Vision classification failed")
        return {
            "label": "unknown",
            "category": "Unknown",
            "advice": "Confidence low — please double-check manually.",
            "confidence": 0.0
        }
    
@app.route("/twilio/whatsapp", methods=["POST"])
def whatsapp_webhook():
    from_number = request.values.get("From", "").replace("whatsapp:", "")
    media_url   = request.values.get("MediaUrl0")
    msg_body    = request.values.get("Body", "").strip()
    lower_body  = msg_body.lower()
    app.logger.info(f"📩 WhatsApp msg from {from_number}, media_url={media_url}, body={msg_body}")

    # -----------------
    # 0) Check if user exists
    # -----------------
    user = User.query.filter_by(phone=from_number).first()
    if not user:
        # Signup flow (shortened for brevity, keep your existing code here)
        _send_whatsapp(from_number, "👋 Welcome to WasteAI! Please reply with your *name* so we can create your account.")
        PENDING_SIGNUPS[from_number] = {"step": "ask_name"}
        return ("", 204)

    locale = USER_LANG.get(from_number, "en")

    # -----------------
    # Commands
    # -----------------
    if lower_body == "sendstat":
        total = Detection.query.filter_by(user_id=user.id).count()
        rec   = Detection.query.filter_by(user_id=user.id, category="Recyclable").count()
        haz   = Detection.query.filter_by(user_id=user.id, category="Hazardous").count()
        non   = total - rec - haz
        stat_msg = _t({
            "en": f"📊 *Your Recycling Stats*\n\n• Total: {total}\n• ♻️ Recyclable: {rec}\n• ☣️ Hazardous: {haz}\n• 🗑️ Other: {non}",
            "ar": f"📊 *إحصاءاتك*\n\n• المجموع: {total}\n• ♻️ قابلة للتدوير: {rec}\n• ☣️ خطرة: {haz}\n• 🗑️ أخرى: {non}",
            "fr": f"📊 *Vos Statistiques*\n\n• Total: {total}\n• ♻️ Recyclable: {rec}\n• ☣️ Dangereux: {haz}\n• 🗑️ Autres: {non}"
        }, locale)
        _send_whatsapp(from_number, stat_msg)
        return ("", 204)

    if lower_body == "senddiy":
        last_det = Detection.query.filter_by(user_id=user.id).order_by(Detection.id.desc()).first()
        if not last_det:
            _send_whatsapp(from_number, _t({
                "en": "⚠️ No past detections found. Send an image first!",
                "ar": "⚠️ لا توجد اكتشافات سابقة. أرسل صورة أولاً!",
                "fr": "⚠️ Aucune détection trouvée. Envoyez une image d’abord!"
            }, locale))
            return ("", 204)
        try:
            resp = openai.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": f"You are a creative eco-designer. Reply ONLY in {locale}."},
                    {"role": "user", "content": f"Suggest a short, creative DIY reuse project for '{last_det.label}' (category: {last_det.category})."}
                ],
                temperature=0.8,
                max_tokens=120
            )
            idea_text = resp.choices[0].message.content.strip()
        except Exception:
            idea_text = _t({
                "en": "Could not generate a DIY idea right now. Try again later.",
                "ar": "تعذر إنشاء فكرة DIY الآن. حاول لاحقاً.",
                "fr": "Impossible de générer une idée DIY pour l’instant. Réessayez plus tard."
            }, locale)
        diy_msg = _t({
            "en": f"✨ *DIY Idea for {last_det.label}*\n\n{idea_text}",
            "ar": f"✨ *فكرة DIY لـ {last_det.label}*\n\n{idea_text}",
            "fr": f"✨ *Idée DIY pour {last_det.label}*\n\n{idea_text}"
        }, locale)
        _send_whatsapp(from_number, diy_msg)
        return ("", 204)

    if lower_body == "sendhistory":
        last5 = Detection.query.filter_by(user_id=user.id).order_by(Detection.id.desc()).limit(5).all()
        if last5:
            history_lines = [f"{d.label} → {d.category}" for d in last5]
            history_msg = _t({
                "en": "📜 *Your Last 5 Detections:*\n" + "\n".join(history_lines),
                "ar": "📜 *آخر 5 اكتشافات:*\n" + "\n".join(history_lines),
                "fr": "📜 *Vos 5 dernières détections:*\n" + "\n".join(history_lines)
            }, locale)
        else:
            history_msg = _t({
                "en": "No history found.",
                "ar": "لا يوجد سجل.",
                "fr": "Aucun historique."
            }, locale)
        _send_whatsapp(from_number, history_msg)
        return ("", 204)

    if lower_body == "sendhelp":
        help_msg = _t({
            "en": "🤖 *WasteAI Commands*\n\n• sendStat → 📊 Stats\n• sendHistory → 📜 History\n• sendDIY → ✨ DIY Idea\n• sendHelp → ℹ️ Help\n\n🌐 Change language: lang:en | lang:ar | lang:fr",
            "ar": "🤖 *أوامر WasteAI*\n\n• sendStat → 📊 إحصاءاتك\n• sendHistory → 📜 السجل\n• sendDIY → ✨ فكرة DIY\n• sendHelp → ℹ️ المساعدة\n\n🌐 تغيير اللغة: lang:en | lang:ar | lang:fr",
            "fr": "🤖 *Commandes WasteAI*\n\n• sendStat → 📊 Stats\n• sendHistory → 📜 Historique\n• sendDIY → ✨ Idée DIY\n• sendHelp → ℹ️ Aide\n\n🌐 Langue: lang:en | lang:ar | lang:fr"
        }, locale)
        _send_whatsapp(from_number, help_msg)
        return ("", 204)

    # -----------------
    # Require image
    # -----------------
    if not media_url:
        _send_whatsapp(from_number, _t({
            "en": "⚠️ Please send an image of waste material.",
            "ar": "⚠️ الرجاء إرسال صورة للنفايات.",
            "fr": "⚠️ Veuillez envoyer une image de déchet."
        }, locale))
        return ("", 204)

    _send_loading(from_number)

    # -----------------
    # Download image
    # -----------------
    filename = f"wa_{secrets.token_hex(8)}.jpg"
    temp_path = os.path.join("static", "uploads", filename)
    try:
        r = requests.get(media_url, auth=(account_sid, auth_token), timeout=30)
        if r.status_code != 200:
            _send_whatsapp(from_number, "⚠️ Could not download your image. Try again.")
            return ("", 204)
        with open(temp_path, "wb") as f:
            f.write(r.content)
    except Exception:
        _send_whatsapp(from_number, "⚠️ Could not download your image, try again.")
        return ("", 204)

    # -----------------
    # YOLO Detection
    # -----------------
    try:
        results = model(temp_path)
        boxes = results[0].boxes
        app.logger.info(f"🔍 YOLO detected {len(boxes)} objects")
    except Exception:
        _send_whatsapp(from_number, "⚠️ Detection failed, please try again later.")
        return ("", 204)

    # -----------------
    # Classification
    # -----------------
    parsed_items = []
    CONF_THRESHOLD = 0.70

    if len(boxes) == 0:
        ai_item = _openai_classify_image(temp_path, locale=locale)
        parsed_items = [ai_item]
    else:
        for b in boxes:
            try:
                cls_id = int(b.cls.item())
                label = model.names[cls_id]
                conf  = float(b.conf.item())
            except Exception:
                label, conf = "unknown", 0.0

            if conf >= CONF_THRESHOLD:
                parsed_items.append({
                    "label": label,
                    "category": _rough_bucket(label.lower()),
                    "confidence": conf
                })
            else:
                ai_item = _openai_classify_image(temp_path, locale=locale)
                parsed_items.append(ai_item)

    # -----------------
    # 🔥 Attach Suggestions
    # -----------------
    uniq = {}
    for it in parsed_items:
        key = (it["label"], it["category"])
        if key not in uniq:
            uniq[key] = generate_suggestions(it["label"], it["category"], locale=locale)
        it["suggestions"] = uniq[key]

    # -----------------
    # Save to DB
    # -----------------
    try:
        for it in parsed_items:
            db.session.add(Detection(
                user_id=user.id,
                label=it.get("label", "unknown"),
                category=it.get("category", "Unknown"),
                confidence=it.get("confidence", 0.0),
                snapshot_path=temp_path
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()

    # -----------------
    # Facility + Impact
    # -----------------
    fac = _lookup_facility(parsed_items)
    total_dets = Detection.query.filter_by(user_id=user.id).count()
    rec = Detection.query.filter_by(user_id=user.id, category="Recyclable").count()
    haz = Detection.query.filter_by(user_id=user.id, category="Hazardous").count()
    impact = {"total": total_dets, "recyclable": rec, "hazardous": haz, "non": total_dets - rec - haz}

    # -----------------
    # Build WhatsApp Body (with suggestions + map link)
    # -----------------
    body = build_whatsapp_body(parsed_items, facility=fac, impact=impact, locale=locale)
    _send_whatsapp(from_number, body)
    return ("", 204)


# -----------------
# Format WhatsApp reply nicely
# -----------------
def build_whatsapp_body(detections, facility=None, impact=None, locale="en"):
    lines = []

    # ----------------------------
    # Title
    # ----------------------------
    lines.append("🔎 *WasteAI Detection Report*")
    lines.append("")

    # ----------------------------
    # Detections
    # ----------------------------
    if not detections:
        lines.append("⚠️ No objects detected.")
    else:
        for i, d in enumerate(detections, 1):
            badge = "♻️" if d["category"] == "Recyclable" else "☣️" if d["category"] == "Hazardous" else "🚮"
            lines.append(f"{i}. *{d['label']}* {badge} ({d['category']})")

            # Suggestions if available
            s = d.get("suggestions", {})
            if s:
                if s.get("prep"):
                    lines.append("   🧹 *Prep:* " + ", ".join(s["prep"]))
                if s.get("checklist"):
                    lines.append("   ✅ *Checklist:* " + ", ".join(s["checklist"]))
                if s.get("reuse"):
                    lines.append("   ♻️ *Reuse Ideas:* " + ", ".join(s["reuse"]))
                if s.get("warnings"):
                    lines.append("   ⚠️ *Warnings:* " + ", ".join(s["warnings"]))
            lines.append("")

    # ----------------------------
    # Nearest Facility
    # ----------------------------
    if facility:
        lines.append("🏭 *Nearest Recycling Facility*")
        lines.append(f"• *{facility.get('name', 'Unknown')}*")
        if facility.get("address"):
            lines.append(f"• {facility['address']}")
        if facility.get("distance_km"):
            lines.append(f"• 📏 {facility['distance_km']} km away")
        if facility.get("lat") and facility.get("lng"):
            lines.append(
                f"➡️ [Open in Google Maps](https://www.google.com/maps/dir/?api=1&destination={facility['lat']},{facility['lng']})"
            )
        lines.append("")

    # ----------------------------
    # Impact Stats (Gamified)
    # ----------------------------
    if impact:
        total = max(impact["total"], 1)  # avoid division by zero

        # Small emoji progress bars
        def bar(count):
            filled = "🟩" * min(count, 5)
            empty = "⬜" * max(0, 5 - min(count, 5))
            return filled + empty

        lines.append("🌍 *Your Recycling Impact*")
        lines.append(f"• Total items: {impact['total']}")
        lines.append(f"• ♻️ Recyclable: {impact['recyclable']} {bar(impact['recyclable'])}")
        lines.append(f"• ☣️ Hazardous: {impact['hazardous']} {bar(impact['hazardous'])}")
        lines.append(f"• 🗑️ Other: {impact['non']} {bar(impact['non'])}")

        # Achievement
        recycle_rate = int((impact["recyclable"] / total) * 100)
        if recycle_rate >= 70:
            lines.append("🏅 Eco Hero! You’re doing amazing at recycling!")
        elif recycle_rate >= 40:
            lines.append("🌱 Good job! Keep improving your recycling rate.")
        else:
            lines.append("♻️ Let’s try to recycle more items next time!")

        lines.append("")

    # ----------------------------
    # Footer with commands
    # ----------------------------
    lines.append(_t({
        "en": (
            "───\n💡 *Next Commands:*\n"
            "• `sendStat` → 📊 Your statistics\n"
            "• `sendHistory` → 📜 Your last detections\n"
            "• `sendDIY` → ✨ Creative reuse ideas\n"
            "• `sendHelp` → ℹ️ Help menu"
        ),
        "ar": (
            "───\n💡 *الأوامر التالية:*\n"
            "• `sendStat` → 📊 إحصاءاتك\n"
            "• `sendHistory` → 📜 آخر اكتشافاتك\n"
            "• `sendDIY` → ✨ فكرة مبتكرة لإعادة الاستخدام\n"
            "• `sendHelp` → ℹ️ قائمة المساعدة"
        ),
        "fr": (
            "───\n💡 *Commandes suivantes:*\n"
            "• `sendStat` → 📊 Vos statistiques\n"
            "• `sendHistory` → 📜 Vos dernières détections\n"
            "• `sendDIY` → ✨ Idée créative de réutilisation\n"
            "• `sendHelp` → ℹ️ Menu d’aide"
        )
    }, locale))

    return "\n".join(lines)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    if not scheduler.running:
        scheduler.start()
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
