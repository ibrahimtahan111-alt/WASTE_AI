from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# Path to your trained model
BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "weights"
DETECTION_MODEL = MODEL_DIR /  "best.pt"

# All 64 classes
CLASSES = [
    "Aerosol", "Aluminium blister pack", "Aluminium foil", "Battery",
    "Broken glass", "Carded blister pack", "Cigarette", "Clear plastic bottle",
    "Corrugated carton", "Crisp packet", "Disposable food container",
    "Disposable plastic cup", "Drink can", "Drink carton", "Egg carton",
    "Foam cup", "Foam food container", "Food Can", "Food waste", "Garbage bag",
    "Glass", "Glass bottle", "Glass cup", "Glass jar", "Magazine paper",
    "Meal carton", "Metal", "Metal bottle cap", "Metal lid", "Normal paper",
    "Other carton", "Other plastic", "Other plastic bottle",
    "Other plastic container", "Other plastic cup", "Other plastic wrapper",
    "Paper", "Paper bag", "Paper cup", "Paper straw", "Pizza box", "Plastic",
    "Plastic bottle cap", "Plastic film", "Plastic glooves", "Plastic lid",
    "Plastic straw", "Plastic utensils", "Polypropylene bag", "Pop tab",
    "Rope - strings", "Scrap metal", "Shoe", "Single-use carrier bag",
    "Six pack rings", "Spread tub", "Squeezable tube", "Styrofoam piece",
    "Tissues", "Toilet tube", "Tupperware", "Unlabeled litter", "Waste",
    "Wrapping paper"
]

RECYCLABLE = {
    "Plastic",   # 👈 add this
    "Clear plastic bottle", "Corrugated carton", "Drink can", "Drink carton",
    "Glass bottle", "Glass jar", "Metal", "Paper", "Paper bag", "Paper cup",
    "Pizza box", "Plastic bottle cap"
}


NON_RECYCLABLE = {
    "Crisp packet", "Disposable plastic cup", "Foam cup", "Snack bag",
    "Plastic utensils", "Plastic straw", "Other plastic", "Other plastic wrapper",
    "Single-use carrier bag", "Tissues", "Wrapping paper", "Unlabeled litter"
}

HAZARDOUS = {
    "Aerosol", "Battery", "Broken glass", "Chemical spray can",
    "Paint bucket", "Aluminium blister pack"
}

# Normalization map: raw YOLO labels → clean consistent labels
NORMALIZATION_MAP = {
    # Plastic-related
    "Plastic": "Clear plastic bottle",
    "Clear plastic bottle": "Clear plastic bottle",
    "Plastic bottle cap": "Plastic bottle cap",
    "Plastic film": "Plastic film",
    "Plastic glooves": "Plastic gloves",
    "Plastic lid": "Plastic lid",
    "Plastic straw": "Plastic straw",
    "Plastic utensils": "Plastic utensils",
    "Polypropylene bag": "Single-use carrier bag",
    "Other plastic": "Other plastic",
    "Other plastic bottle": "Clear plastic bottle",
    "Other plastic container": "Other plastic",
    "Other plastic cup": "Disposable plastic cup",
    "Other plastic wrapper": "Snack bag",
    "Disposable plastic cup": "Disposable plastic cup",
    "Disposable food container": "Foam food container",
    "Foam cup": "Foam cup",
    "Foam food container": "Foam food container",
    "Styrofoam piece": "Foam cup",

    # Paper & cardboard
    "Normal paper": "Paper",
    "Magazine paper": "Paper",
    "Paper": "Paper",
    "Paper bag": "Paper bag",
    "Paper cup": "Paper cup",
    "Paper straw": "Paper straw",
    "Carded blister pack": "Other carton",
    "Corrugated carton": "Corrugated carton",
    "Meal carton": "Other carton",
    "Other carton": "Other carton",
    "Pizza box": "Pizza box",
    "Toilet tube": "Paper",
    "Egg carton": "Other carton",

    # Metals
    "Drink can": "Drink can",
    "Food Can": "Drink can",
    "Metal": "Metal",
    "Metal bottle cap": "Metal bottle cap",
    "Metal lid": "Metal lid",
    "Aluminium blister pack": "Aluminium blister pack",
    "Aluminium foil": "Aluminium foil",
    "Pop tab": "Metal",
    "Scrap metal": "Metal",

    # Glass
    "Glass": "Glass",
    "Glass bottle": "Glass bottle",
    "Glass cup": "Glass",
    "Glass jar": "Glass jar",
    "Broken glass": "Broken glass",

    # Hazardous
    "Aerosol": "Aerosol",
    "Battery": "Battery",
    "Chemical spray can": "Aerosol",
    "Squeezable tube": "Chemical plastic bottle",
    "Spread tub": "Chemical plastic bottle",
    "Paint bucket": "Paint bucket",
    "Light bulb": "Light bulb",

    # Misc
    "Cigarette": "Cigarette",
    "Food waste": "Food waste",
    "Garbage bag": "Garbage bag",
    "Rope - strings": "Rope - strings",
    "Shoe": "Shoe",
    "Single-use carrier bag": "Single-use carrier bag",
    "Six pack rings": "Six pack rings",
    "Tissues": "Tissues",
    "Tupperware": "Tupperware",
    "Unlabeled litter": "Unlabeled litter",
    "Waste": "Waste",
    "Wrapping paper": "Wrapping paper",
}

# ===============================
# Environmental Impact Factors
# ===============================
# Approximate average item weights (kg) + LCA multipliers per kg
# Source: US EPA WARM, Zero Waste Europe, UN reports
# Adjust with efficiency factor in app.py (Lebanon context ~0.6)

IMPACT_FACTORS = {
    # Plastics
    "Clear plastic bottle": {"weight":0.025, "co2_perkg":1.8, "energy":2.0, "water":5},
    "Plastic bottle cap": {"weight":0.002, "co2_perkg":1.8, "energy":2.0, "water":5},
    "Plastic bag": {"weight":0.01, "co2_perkg":1.8, "energy":2.0, "water":5},

    # Metals
    "Drink can": {"weight":0.015, "co2_perkg":9.16, "energy":14, "water":0},
    "Metal": {"weight":0.05, "co2_perkg":4.5, "energy":6, "water":0},

    # Glass
    "Glass bottle": {"weight":0.2, "co2_perkg":0.3, "energy":0.7, "water":0},
    "Glass jar": {"weight":0.25, "co2_perkg":0.3, "energy":0.7, "water":0},

    # Paper & cardboard
    "Paper": {"weight":0.005, "co2_perkg":3.6, "energy":4.0, "water":26},
    "Pizza box": {"weight":0.1, "co2_perkg":3.6, "energy":4.0, "water":26},
    "Corrugated carton": {"weight":0.15, "co2_perkg":3.6, "energy":4.0, "water":26},

    # Hazardous / E-waste
    "Battery": {"weight":0.05, "co2_perkg":1.5, "energy":0, "water":0},
    "Light bulb": {"weight":0.03, "co2_perkg":0.8, "energy":0.2, "water":0},
}

DEFAULT_FACTORS = {"weight":0.02, "co2_perkg":1.0, "energy":1.0, "water":1}


# ---------- SMART SUGGESTION KNOWLEDGE BASE ----------
SMART_SUGGESTIONS = {
    # Plastics
    "Clear plastic bottle": {
        "risk": "low",
        "prep": [
            "Empty and quick-rinse the bottle.",
            "Remove cap and ring (many places recycle caps separately).",
            "Squash to save space."
        ],
        "reuse": [
            "Cut into a small planter or seed starter.",
            "DIY bird feeder with sticks and twine.",
            "Dry storage for rice/pasta."
        ],
        "warnings": [],
        "notes": "Most facilities take PET (#1). Labels can usually stay on."
    },
    "Plastic bottle cap": {
        "risk": "low",
        "prep": [
            "Collect caps in a larger container so they don’t fall through sorting.",
            "Check local rules: some places allow caps back on."
        ],
        "reuse": [
            "Color sorting game for kids.",
            "Craft mosaics / counters."
        ],
        "warnings": [],
        "notes": "Small items can be lost in MRFs; bundle whenever possible."
    },
    "Plastic film": {
        "risk": "low",
        "prep": [
            "Keep film/bags clean and dry.",
            "Do NOT put loose film in curbside unless your city allows it.",
            "Use store-drop bins for films where available."
        ],
        "reuse": ["Small trash liners", "Packing filler"],
        "warnings": ["Film tangles sorting machinery—avoid curbside bins."],
        "notes": "Look for store collection programs."
    },

    # Paper & cardboard
    "Paper": {
        "risk": "low",
        "prep": ["Keep dry and clean.", "Remove tapes/staples if easy."],
        "reuse": ["Note paper", "Compost browns (if non-glossy)"],
        "warnings": [],
        "notes": "Wet/soiled paper goes to trash or compost (if allowed)."
    },
    "Corrugated carton": {
        "risk": "low",
        "prep": ["Flatten boxes.", "Remove plastic tape if possible."],
        "reuse": ["Moving/organizing boxes", "Weed barrier in gardens"],
        "warnings": [],
        "notes": "Greasy boxes reduce fiber quality."
    },
    "Pizza box": {
        "risk": "low",
        "prep": ["Tear off clean lid to recycle.", "Greasy bottom → trash/compost."],
        "reuse": ["Drop cloth for crafts/painting"],
        "warnings": [],
        "notes": "Facilities reject heavy food contamination."
    },

    # Metals
    "Drink can": {
        "risk": "low",
        "prep": ["Quick-rinse.", "Crush (if allowed) to save space."],
        "reuse": ["Pen holder (sand sharp edges first)"],
        "warnings": ["Sharp edges after opening—handle carefully."],
        "notes": "Aluminum has high recycling value; keep it clean."
    },
    "Metal": {
        "risk": "low",
        "prep": ["Remove food residue.", "Bundle small metal together."],
        "reuse": ["DIY hooks/brackets (if safe)"],
        "warnings": ["Sharp edges."],
        "notes": "Most scrap yards accept mixed metal."
    },

    # Glass
    "Glass bottle": {
        "risk": "medium",
        "prep": ["Empty and quick-rinse.", "Keep caps separate."],
        "reuse": ["Storage jars", "Vases/candle holders"],
        "warnings": ["Breakage risk—use sturdy box for drop-off."],
        "notes": "Color-sort if your facility asks for it."
    },
    "Glass jar": {
        "risk": "medium",
        "prep": ["Rinse thoroughly.", "Remove metal lid (recycle separately)."],
        "reuse": ["Food storage", "Hardware jar for screws/nails"],
        "warnings": ["Breakage risk."],
        "notes": "Labels are usually okay."
    },
    "Broken glass": {
        "risk": "high",
        "prep": ["Wrap in thick paper/cardboard and tape before trash."],
        "reuse": [],
        "warnings": ["Do NOT put broken glass in recycling—safety hazard."],
        "notes": "Check local rules; some depots accept in special bins."
    },

    # Hazardous / e-waste
    "Battery": {
        "risk": "high",
        "prep": [
            "Tape terminals (esp. lithium) to prevent short circuits.",
            "Store in a non-metal container."
        ],
        "reuse": [],
        "warnings": [
            "Do NOT trash or curbside—fire risk.",
            "Drop at e-waste/battery collection points."
        ],
        "notes": "Look for specialized e-waste centers."
    },
    "Light bulb": {
        "risk": "high",
        "prep": [
            "Keep intact; place in original box if possible.",
            "Fluorescents contain mercury—handle carefully."
        ],
        "reuse": [],
        "warnings": [
            "Do NOT recycle with glass.",
            "Use hazardous waste/e-waste channels."
        ],
        "notes": "LEDs often accepted at e-waste depots."
    },
    "Aerosol": {
        "risk": "high",
        "prep": ["Completely empty only; otherwise treat as hazardous."],
        "reuse": [],
        "warnings": [
            "Pressurized can—fire/explosion hazard.",
            "Follow hazardous waste guidance."
        ],
        "notes": "Check local rules for puncturing/empty status."
    },
}

# Fallback if label not listed
SMART_DEFAULT = {
    "risk": "low",
    "prep": ["Keep items clean and dry.", "Remove obvious contaminants."],
    "reuse": ["Consider storage, crafts, or donation."],
    "warnings": [],
    "notes": "If unsure, check local guidance or use dedicated drop-off."
}

# ===============================
# Smart Suggestion System Config
# ===============================
USE_LLM_SUGGESTIONS = os.getenv("USE_LLM_SUGGESTIONS", "true").strip().lower() in ("1", "true", "yes")

# Provider options: "openai" or "ollama"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()

# Fallback, rule-based suggestion seeds (used if LLM fails or disabled)
SUGGESTION_RULES = {
    "Clear plastic bottle": {
        "summary": "PET bottle detected. Rinse, remove cap/label, and compress to save space.",
        "recycle": [
            "Rinse and dry to avoid contamination.",
            "Remove cap & label if your facility requests it.",
            "Crush bottle to reduce volume."
        ],
        "reuse": [
            "Refill with filtered water (short-term).",
            "Cut into planters or bird feeders.",
            "Use for drip irrigation in pots."
        ],
        "hazard": [],
        "disposal": ["If recycling is unavailable, compress and dispose in general waste."]
    },
    "Drink can": {
        "summary": "Aluminium can detected. High recycling value; keep it clean and dry.",
        "recycle": [
            "Rinse quickly to remove residue.",
            "Crush to save space.",
            "Group cans in a separate bag for metal."
        ],
        "reuse": [
            "DIY pencil holder (smooth edges).",
            "Seed starter pots (pierce drainage holes)."
        ],
        "hazard": [],
        "disposal": ["If no recycling, compress safely and dispose."]
    },
    "Battery": {
        "summary": "Battery detected (hazardous). Avoid general waste; use e-waste drop-off.",
        "recycle": [],
        "reuse": [],
        "hazard": [
            "Store in a cool, dry place; tape terminals to avoid short circuit.",
            "Do not incinerate; do not crush."
        ],
        "disposal": [
            "Use certified e-waste or battery collection points.",
            "Check municipal hazardous waste days."
        ]
    },
    # …add more labels as needed
}
