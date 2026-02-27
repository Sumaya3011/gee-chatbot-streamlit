# gee_utils.py
"""
All Google Earth Engine logic for Dynamic World.

IMPORTANT:
- We assume Earth Engine is already initialized in app.py
  using a service account.
"""

import io
import requests
import ee

from config import CLASS_PALETTE, THUMB_SIZE


def get_dynamic_world_image(point_geom, year: int):
    """
    Create a Dynamic World land cover PNG for a given year and point.

    Inputs:
      - point_geom: ee.Geometry.Point (center of your study area)
      - year: int (e.g., 2021)

    Returns:
      - BytesIO object containing PNG image (for Streamlit st.image)
    """

    # 1) Define date range for the given year
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    # 2) Build Dynamic World image
    # TODO: Replace this block with your own logic if you already had one.
    # This is a simple starting point using GOOGLE/DYNAMICWORLD/V1:
    dw_collection = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")  # Dynamic World dataset
        .filterDate(start, end)
        .filterBounds(point_geom)
    )

    # Use the 'label' band (most likely class 0-8) and take the mode over the year
    dw_image = dw_collection.select("label").mode()

    vis_params = {
        "min": 0,
        "max": 8,
        "palette": CLASS_PALETTE,
    }

    # 3) Region around the point (buffer of 2000 meters)
    region = point_geom.buffer(2000).bounds()

    # 4) Get thumbnail URL from Earth Engine
    url = dw_image.getThumbURL(
        {
            "region": region,
            "dimensions": THUMB_SIZE,
            "format": "png",
            "min": vis_params["min"],
            "max": vis_params["max"],
            "palette": vis_params["palette"],
        }
    )

    # 5) Download the PNG from that URL
    response = requests.get(url)
    response.raise_for_status()

    # Return an in-memory file for Streamlit
    return io.BytesIO(response.content)


def get_comparison_images(point_geom, year_a: int, year_b: int):
    """
    Get two images: one for year_a and one for year_b.
    """
    img_a = get_dynamic_world_image(point_geom, year_a)
    img_b = get_dynamic_world_image(point_geom, year_b)
    return img_a, img_b
