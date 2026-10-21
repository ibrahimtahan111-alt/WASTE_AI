# scripts/seed_facilities.py
import os, requests
from app import app, db
from models import Facility

API_KEY = os.getenv("GOOGLE_MAPS_KEY")

# --- Geocoding ---
def geocode_address(address):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": API_KEY}
    res = requests.get(url, params=params).json()
    if res["status"] == "OK":
        loc = res["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    else:
        print(f"⚠️ Geocode failed for {address}: {res.get('status')}")
    return None, None

# --- Facility data ---
FACILITIES = [
    {
        "name":"Live Love Recycle (Eco-centers & App)",
        "address":"Beirut, Lebanon",
        "city":"Beirut",
        "phone":"+961 3 113 141",
        "website":"https://livelove.org/",
        "pickup":True,
        "accepts":"plastic,paper,metal,glass,medicines,appliances,textiles,oil",
        "notes":"Use the app for pickup or drop at partner points"
    },
    {
        "name":"Recycle Beirut - Bir Hassan Warehouse",
        "address":"Embassies Street, Bir Hassan (Jnah), Beirut, Lebanon",
        "city":"Beirut",
        "phone":"",
        "website":"https://recyclebeirut.com/",
        "pickup":True,
        "accepts":"plastic,paper,metal,glass",
        "notes":"Drop-off or paid pickup within Beirut"
    },
    {
        "name":"arcenciel - Jisr el Wati Center",
        "address":"Emile Lahoud Ave, Jisr el Wati, Sin El Fil, Beirut, Lebanon",
        "city":"Beirut",
        "phone":"+961 1 565 655",
        "website":"https://arcenciel.org/",
        "pickup":False,
        "accepts":"plastic,metal,paper,glass,hazardous",
        "notes":"Also handles medical waste (institutional workflows)"
    },
    {
        "name":"Lebanon Waste Management - Sad El Bouchrieh",
        "address":"Sad El Bouchrieh, Mount Lebanon, Lebanon",
        "city":"Metn",
        "phone":"+961 81 312 186",
        "website":"https://lebanonwastemanagement.com",
        "pickup":False,
        "accepts":"plastic,paper,metal",
        "notes":"Drive-through drop-off; cash-back/donation model"
    },
    {
        "name":"Lebanon Waste Management - Mirna Chalouhi",
        "address":"Mirna Chalouhi, Dekwaneh, Mount Lebanon, Lebanon",
        "city":"Metn",
        "phone":"+961 81 312 186",
        "website":"https://lebanonwastemanagement.com",
        "pickup":False,
        "accepts":"plastic,paper,metal",
        "notes":"Drive-through drop-off"
    },
    {
        "name":"Ecoserv - Zouk Mosbeh Hub",
        "address":"Zouk Mosbeh, Keserwan, Lebanon",
        "city":"Keserwan",
        "phone":"+961 9 220 094",
        "website":"https://ecoservlb.org/",
        "pickup":False,
        "accepts":"e-waste,batteries",
        "notes":"E-waste dropzones countrywide; see map on site"
    },
    {
        "name":"L’Écoute - Ain Saade Industrial Zone",
        "address":"Ain Saade Industrial Zone, Metn, Lebanon",
        "city":"Metn",
        "phone":"+961 76 176 234",
        "website":"https://www.lecoute-lb.org/",
        "pickup":False,
        "accepts":"plastic,metal,paper,glass,e-waste",
        "notes":"Call for availability/collection; social mission"
    },
    {
        "name":"Recycle Lebanon - Fassouh Hub",
        "address":"Saint Louise Street, Kehdy Building, Fassouh, Beirut, Lebanon",
        "city":"Beirut",
        "phone":"",
        "website":"https://recyclelebanon.org/",
        "pickup":False,
        "accepts":"textiles,oil,plastic,paper,metal,glass",
        "notes":"Community hub; check availability before drop-off"
    }
]

# --- Main seeding function ---
def main():
    with app.app_context():
        print("⚠️ Clearing old facilities...")
        db.session.query(Facility).delete()
        db.session.commit()

        for fac in FACILITIES:
            lat, lng = geocode_address(fac["address"])
            facility = Facility(
                name=fac["name"],
                address=fac["address"],
                city=fac["city"],
                phone=fac["phone"],
                website=fac["website"],
                accepts=fac["accepts"],
                pickup=fac["pickup"],
                notes=fac["notes"],
                lat=lat,
                lng=lng
            )
            db.session.add(facility)
            print(f"✅ Inserted: {fac['name']} ({lat}, {lng})")

        db.session.commit()
        print("🎉 Facilities seeded successfully!")

if __name__ == "__main__":
    main()
