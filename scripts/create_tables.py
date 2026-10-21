"""Create all database tables without starting the web server."""
from app import app, db

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("Database tables created successfully.")
