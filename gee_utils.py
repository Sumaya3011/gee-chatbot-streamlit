# gee_utils.py
"""
Google Earth Engine / Dynamic World logic.

This file:
- Builds Dynamic World images for given years.
- Returns XYZ tile URLs that we can show in a Folium map.
"""

import ee

from config import CLASS_PALETTE


def build_dynamic_world_image(point_geom: ee.Geometry, year: int):
    """
    Create a Dynamic World land cover ee.Image for a single year.

    Returns:
      (image, vis_params)
    """
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    # Dynamic World collection (GOOGLE/DYNAMICWORLD/V1)
    dw_collection = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(start, end)
        .filterBounds(point_geom)
    )

    # 'label' band is the most likely class (0–8)
    dw_image = dw_collection.select("label").mode()

    vis_params = {
        "min": 0,
        "max": 8,
        "palette": CLASS_PALETTE,
    }

    return dw_image, vis_params


def _image_to_tile_url(image: ee.Image, vis_params: dict) -> str | None:
    """
    Convert an ee.Image + vis_params into an XYZ tile URL.

    Returns:
      A URL string like:
        https://earthengine.googleapis.com/v1/projects/.../tiles/{z}/{x}/{y}
      or None if something fails.
    """
    try:
        # getMapId returns a dict with a TileFetcher under 'tile_fetcher'
        map_id = image.getMapId(vis_params)
        tile_url = map_id["tile_fetcher"].url_format
        return tile_url
    except Exception as e:
        print("Error creating tile URL:", e)
        return None


def get_dw_tile_urls(point_geom: ee.Geometry, year_a: int, year_b: int) -> dict:
    """
    Build tile URLs for:
      - Dynamic World year A
      - Dynamic World year B
      - Change layer (A != B)

    Returns:
      {
        "a": <url or None>,
        "b": <url or None>,
        "change": <url or None>,
      }
    """

    # Year A
    img_a, vis = build_dynamic_world_image(point_geom, year_a)
    url_a = _image_to_tile_url(img_a, vis)

    # Year B
    img_b, _ = build_dynamic_world_image(point_geom, year_b)
    url_b = _image_to_tile_url(img_b, vis)  # same vis as A

    # Change: where class changed between A and B
    change_img = img_a.neq(img_b)  # 1 where changed, 0 where same
    change_vis = {"min": 0, "max": 1, "palette": ["000000", "ff0000"]}
    url_change = _image_to_tile_url(change_img, change_vis)

    return {
        "a": url_a,
        "b": url_b,
        "change": url_change,
    }
