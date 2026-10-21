# seed_dummy.py
from app import app, db
from models import User, Detection, Facility, DetectionAction, FavoriteFacility, UserBadge, SuggestionCache
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random, json

with app.app_context():
    db.create_all()

    # --------------------------
    # Create Users
    # --------------------------
    users = []
    for i in range(5):
        user = User(
            name=f"User {i+1}",
            email=f"user{i+1}@test.com",
            phone=f"+961700000{i}",
            password_hash=generate_password_hash("password123")
        )
        users.append(user)
        db.session.add(user)
    db.session.commit()

    # --------------------------
    # Create Facilities
    # --------------------------
    facilities = [
        Facility(
            name="Green Earth Center",
            address="Main Street, Beirut",
            city="Beirut",
            phone="+9611123456",
            website="https://greenearth.org",
            accepts="Plastic, Metal, E-waste",
            pickup=True,
            notes="Open Mon-Fri, 9am-5pm",
            lat=33.8938 + random.uniform(-0.05, 0.05),
            lng=35.5018 + random.uniform(-0.05, 0.05),
        ),
        Facility(
            name="EcoRecycle NGO",
            address="Hamra Street, Beirut",
            city="Beirut",
            phone="+9611987654",
            website="https://ecorecycle.org",
            accepts="Plastic, Paper, Glass",
            pickup=False,
            notes="Community-driven recycling center",
            lat=33.8890,
            lng=35.4800,
        )
    ]
    db.session.add_all(facilities)
    db.session.commit()

    # --------------------------
    # Create Detections
    # --------------------------
    categories = ["Recyclable", "Hazardous", "Non-Recyclable"]
    labels = ["Plastic Bottle", "Battery", "Food Waste", "Glass Jar", "E-Waste"]

    for user in users:
        for i in range(10):
            det = Detection(
                user_id=user.id,
                label=random.choice(labels),
                confidence=round(random.uniform(0.5, 1.0), 2),
                category=random.choice(categories),
                snapshot_path="static/uploads/dummy.jpg",
                timestamp=datetime.utcnow() - timedelta(days=random.randint(0, 30))
            )
            db.session.add(det)
    db.session.commit()

    # --------------------------
    # Detection Actions
    # --------------------------
    for i in range(10):
        action = DetectionAction(
            user_id=random.choice(users).id,
            detection_id=random.randint(1, 20),
            facility_id=random.choice(facilities).id,
            action_type=random.choice(["dropoff", "pickup", "learn_more"]),
            user_lat=33.89 + random.uniform(-0.01, 0.01),
            user_lng=35.50 + random.uniform(-0.01, 0.01),
        )
        db.session.add(action)
    db.session.commit()

    # --------------------------
    # Favorite Facilities
    # --------------------------
    fav = FavoriteFacility(
        user_id=users[0].id,
        facility_id=facilities[0].id,
    )
    db.session.add(fav)
    db.session.commit()

    # --------------------------
    # User Badges
    # --------------------------
    badges = ["Eco Starter", "Recycler Pro", "Hazard Handler"]
    for user in users:
        badge = UserBadge(
            user_id=user.id,
            name=random.choice(badges)
        )
        db.session.add(badge)
    db.session.commit()

    # --------------------------
    # Suggestion Cache
    # --------------------------
    sugg = SuggestionCache(
        label="Plastic Bottle",
        category="Recyclable",
        locale="en",
        suggestions_json=json.dumps({
            "prep": ["Rinse with water", "Remove label"],
            "checklist": ["Cap removed", "Dry bottle"],
            "reuse": ["Planter", "Storage container"],
            "warnings": ["Don’t burn plastic"]
        })
    )
    db.session.add(sugg)
    db.session.commit()

    print("✅ Dummy data seeded successfully!")
