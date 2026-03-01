# gee_utils.py
"""
Google Earth Engine / Dynamic World logic.
- No Streamlit UI here.
- Uses geemap to build an interactive map object.
"""

import ee
import geemap.foliumap as geemap

from config import CLASS_PALETTE, LOCATION_LAT, LOCATION_LON


def build_dynamic_world_image(point_geom: ee.Geometry, year: int):
    """
    Create a Dynamic World land cover ee.Image for a single year.

    Returns:
      (image, vis_params)
    """

    start = f"{year}-01-01"
    end = f"{year}-12-31"

    # Dynamic World collection (GOOGLE/DYNAMICWORLD/V1):contentReference[oaicite:3]{index=3}
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


def create_dynamic_world_map(location_point: ee.Geometry, year_a: int, year_b: int):
    """
    Build a geemap.Map with:
      - Satellite basemap
      - Dynamic World for year A
      - Dynamic World for year B
      - Change layer (A != B)

    Returns:
      geemap.Map object (ready for .to_streamlit()).
    """

    # 1) Create the map centered on your AOI
    m = geemap.Map(
        center=(LOCATION_LAT, LOCATION_LON),
        zoom=11,
        lite_mode=True,   # cleaner UI
    )
    m.add_basemap("SATELLITE")

    # 2) Year A and Year B images
    img_a, vis = build_dynamic_world_image(location_point, year_a)
    img_b, _ = build_dynamic_world_image(location_point, year_b)

    # 3) Change layer: where classes are different between years
    change = img_a.neq(img_b)  # 1 where changed, 0 where same
    change_vis = {"min": 0, "max": 1, "palette": ["000000", "ff0000"]}

    # 4) Add layers to map (DW style like JS Map.addLayer):contentReference[oaicite:4]{index=4}
    m.addLayer(img_a, vis, f"Dynamic World {year_a}", True, 0.9)
    m.addLayer(img_b, vis, f"Dynamic World {year_b}", False, 0.9)
    m.addLayer(change, change_vis, f"Change {year_a}→{year_b}", False, 0.9)

    # Optional: show layer control automatically (geemap does this by default)
    m.add_layer_control()

    return m
