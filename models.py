# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=True)  # 🔹 New column
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    detections = db.relationship("Detection", backref="user", lazy=True)

class Detection(db.Model):
    __tablename__ = "detections"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    label = db.Column(db.String(100), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    snapshot_path = db.Column(db.String(200), nullable=True)

class Facility(db.Model):
    __tablename__ = "facilities"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    city = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    website = db.Column(db.String(255))
    accepts = db.Column(db.String(255))
    pickup = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)

    # 🟢 Add these two
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)


class DetectionAction(db.Model):
    __tablename__ = "detection_actions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    detection_id = db.Column(db.Integer, db.ForeignKey("detections.id"), nullable=False)
    facility_id = db.Column(db.Integer, db.ForeignKey("facilities.id"), nullable=True)
    action_type = db.Column(db.String(50), nullable=False)  # "dropoff", "pickup", "learn_more"
    user_lat = db.Column(db.Float, nullable=True)
    user_lng = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FavoriteFacility(db.Model):
    __tablename__ = "favorite_facilities"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    facility_id = db.Column(db.Integer, db.ForeignKey("facilities.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="favorite_facilities", lazy=True)
    facility = db.relationship("Facility", backref="favorited_by", lazy=True)

class UserBadge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    name = db.Column(db.String(80))
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)

class SuggestionCache(db.Model):
    __tablename__ = "suggestions_cache"
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(120), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    locale = db.Column(db.String(10), nullable=True, default="en")
    suggestions_json = db.Column(db.Text, nullable=False)  # JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("label", "category", "locale", name="uix_suggest_key"),
    )

