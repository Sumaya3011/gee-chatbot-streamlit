# config.py
"""
Basic configuration values for the app.
Change these to match your study area and settings.
"""

# Years you support for Dynamic World
YEARS = [2020, 2021, 2022, 2023, 2024]

# 🔒 Fixed study location (the location does not change)
# TODO: change these to your actual study area coordinates
LOCATION_LAT = 25.2048   # example: Dubai
LOCATION_LON = 55.2708   # example: Dubai
LOCATION_NAME = "My Study Area"  # label in the UI

# OpenAI model to use
OPENAI_MODEL = "gpt-4.1-mini"   # you can change later if you want

# Size of the thumbnails (pixels)
THUMB_SIZE = 512

# Dynamic World palette colors (same order as classes 0–8)
CLASS_PALETTE = [
    "419bdf",  # 0 Water
    "397d49",  # 1 Trees
    "88b053",  # 2 Grass
    "7a87c6",  # 3 Flooded Vegetation
    "e49635",  # 4 Crops
    "dfc35a",  # 5 Shrub & Scrub
    "c4281b",  # 6 Built Area
    "a59b8f",  # 7 Bare Ground
    "b39fe1",  # 8 Snow & Ice
]

CLASS_LABELS = [
    "Water",
    "Trees",
    "Grass",
    "Flooded Vegetation",
    "Crops",
    "Shrub & Scrub",
    "Built Area",
    "Bare Ground",
    "Snow & Ice",
]
