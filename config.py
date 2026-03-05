# config.py
"""
Basic configuration for the app.
Change values here if you want to update years, location, etc.
"""

# Years you support for Dynamic World
YEARS = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

# 🔒 Fixed study location (the location does not change)
# TODO: change to your actual study area coordinates
LOCATION_LAT = 24.4539    # example: Abu Dhabi lat
LOCATION_LON = 54.3773    # example: Abu Dhabi lon
LOCATION_NAME = "Abu Dhabi AOI"

# OpenAI model to use
OPENAI_MODEL = "gpt-4.1-mini"   # you can change later if needed

# Dynamic World palette (classes 0–8)
# Using standard DW palette from the docs.:contentReference[oaicite:2]{index=2}
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
