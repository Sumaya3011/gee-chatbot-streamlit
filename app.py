# app.py
import json
import re
from datetime import datetime

import streamlit as st
import ee
import folium
from folium.plugins import DualMap
from streamlit_folium import st_folium

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable, GeocoderTimedOut

from config import (
    YEARS,
    LOCATION_LAT,
    LOCATION_LON,
    LOCATION_NAME,
    CLASS_LABELS,
    CLASS_PALETTE,
)
from gee_utils import get_dw_tile_urls
from chat_utils import ask_chatbot


# -------------------------
# 0. HELPERS (LOGIC UNCHANGED)
# -------------------------
def get_initial_chat_history():
    return [
        {
            "role": "assistant",
            "content": (
                "Hi! I’m your Dynamic World assistant.\n\n"
                "Choose the function and years on the left, then ask me to explain "
                "the land cover and the main changes for the selected region."
            ),
        }
    ]


# -------------------------
# 1. PAGE CONFIG & CSS (EARTHMONITOR-STYLE)
# -------------------------
st.set_page_config(
    page_title="EarthMonitor – Dynamic World Change Detection",
    page_icon="🌍",
    layout="wide",
)

st.markdown(
    """
    <style>
    /* Global layout */
    .stApp {
        background-color: #020617;
        color: #e5e7eb;
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }

    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
        max-width: 1350px;
    }

    /* Top navbar */
    .em-topbar {
        width: 100%;
        background-color: #020617;
        border-bottom: 1px solid #111827;
        padding: 10px 4px 8px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .em-title {
        font-size: 18px;
        font-weight: 600;
        color: #f9fafb;
    }

    .em-subtitle {
        font-size: 11px;
        color: #6b7280;
        margin-top: 2px;
    }

    .em-brand-right {
        font-size: 11px;
        color: #6b7280;
    }

    /* Cards */
    .em-card {
        background-color: #020617;
        border-radius: 16px;
        border: 1px solid #111827;
        box-shadow: 0 20px 40px rgba(3, 7, 18, 0.8);
        padding: 14px 14px 12px;
    }

    .em-card-soft {
        background-color: #020617;
        border-radius: 16px;
        border: 1px solid #111827;
        box-shadow: 0 14px 30px rgba(3, 7, 18, 0.7);
        padding: 14px 14px 12px;
    }

    .em-section-title {
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #e5e7eb;
        margin-bottom: 4px;
    }

    .em-section-subtext {
        font-size: 11px;
        color: #9ca3af;
        margin-bottom: 6px;
    }

    .em-divider {
        border-top: 1px solid #111827;
        margin: 10px 0;
    }

    /* Radio buttons styled like the screenshot */
    .stRadio > label {
        font-size: 11px;
        color: #9ca3af;
    }
    .stRadio div[role="radiogroup"] > label {
        display: block;
        padding: 6px 10px;
        border-radius: 10px;
        border: 1px solid #1f2937;
        background: #020617;
        margin-bottom: 4px;
        font-size: 12px;
        color: #e5e7eb;
        cursor: pointer;
    }
    .stRadio div[role="radiogroup"] > label:hover {
        border-color: #374151;
    }

    /* Inputs */
    .stTextInput input, .stNumberInput input {
        background-color: #020617 !important;
        border-radius: 10px !important;
        border: 1px solid #1f2937 !important;
        color: #e5e7eb !important;
        font-size: 12px !important;
        padding: 6px 10px !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: #2563eb !important;
        box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.4) !important;
    }
    .stSelectbox div[data-baseweb="select"] > div {
        background-color: #020617 !important;
        border-radius: 10px !important;
        border: 1px solid #1f2937 !important;
        font-size: 12px !important;
        color: #e5e7eb !important;
    }

    /* Buttons */
    .stButton > button {
        border-radius: 999px;
        padding: 0.35rem 0.9rem;
        font-size: 12px;
        font-weight: 500;
        background: linear-gradient(135deg, #2563eb, #4f46e5);
        border: none;
        color: white;
        box-shadow: 0 10px 22px rgba(37, 99, 235, 0.6);
    }
    .stButton > button:hover {
        box-shadow: 0 14px 30px rgba(37, 99, 235, 0.85);
        transform: translateY(-0.5px);
    }

    /* Chat */
    .em-chat-container {
        border-radius: 12px;
        border: 1px solid #111827;
        background-color: #020617;
        padding: 10px;
        height: 200px;
        overflow-y: auto;
    }
    .em-chat-row {
        display: flex;
        margin-bottom: 6px;
    }
    .em-chat-user {
        justify-content: flex-end;
    }
    .em-chat-assistant {
        justify-content: flex-start;
    }
    .em-chat-meta {
        font-size: 10px;
        color: #6b7280;
        margin-bottom: 2px;
    }
    .em-chat-bubble {
        max-width: 90%;
        padding: 6px 10px;
        border-radius: 12px;
        font-size: 12px;
        line-height: 1.4;
        white-space: pre-wrap;
    }
    .em-chat-bubble-user {
        background-color: #1d4ed8;
        color: #e5e7eb;
    }
    .em-chat-bubble-assistant {
        background-color: #111827;
        color: #e5e7eb;
    }

    /* Map */
    button[title="View fullscreen"] {
        display: none;
    }

    /* Report bar */
    .em-report-bar {
        margin-top: 10px;
        padding-top: 8px;
        border-top: 1px solid #111827;
        font-size: 12px;
        color: #e5e7eb;
        display: grid;
        grid-template-columns: 0.2fr 0.32fr 0.2fr 1fr;
        column-gap: 18px;
        align-items: baseline;
    }
    .em-report-label {
        font-size: 11px;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 2px;
    }
    .em-report-value {
        font-size: 12px;
        font-weight: 500;
        color: #e5e7eb;
    }

    @media (max-width: 1000px) {
        .em-report-bar {
            grid-template-columns: 1fr;
            row-gap: 6px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# 2. SESSION STATE (LOGIC SAME)
# -------------------------
if "analysis_function" not in st.session_state:
    st.session_state["analysis_function"] = "change_detection"

if "year_a" not in st.session_state:
    st.session_state["year_a"] = YEARS[max(0, len(YEARS) - 2)]

if "year_b" not in st.session_state:
    st.session_state["year_b"] = YEARS[max(0, len(YEARS) - 1)]

# Chat: fresh per new browser session
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = get_initial_chat_history()

# Location defaults (from config)
if "location_name" not in st.session_state:
    st.session_state["location_name"] = LOCATION_NAME
if "location_lat" not in st.session_state:
    st.session_state["location_lat"] = LOCATION_LAT
if "location_lon" not in st.session_state:
    st.session_state["location_lon"] = LOCATION_LON
if "location_city" not in st.session_state:
    st.session_state["location_city"] = LOCATION_NAME


# -------------------------
# 3. INIT EARTH ENGINE (UNCHANGED)
# -------------------------
def init_ee():
    if getattr(st.session_state, "ee_initialized", False):
        return

    service_account_json = st.secrets.get("EE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        st.error(
            "EE_SERVICE_ACCOUNT_JSON is missing.\n\n"
            "In Streamlit Cloud: Settings → Secrets → add EE_SERVICE_ACCOUNT_JSON."
        )
        st.stop()

    info = json.loads(service_account_json)
    email = info["client_email"]
    project_id = info.get("project_id")

    credentials = ee.ServiceAccountCredentials(email, key_data=service_account_json)
    if project_id:
        ee.Initialize(credentials, project=project_id)
    else:
        ee.Initialize(credentials)

    st.session_state.ee_initialized = True


init_ee()


# -------------------------
# 4. MAP LEGEND (LOGIC SAME)
# -------------------------
def add_dw_legend_to_map(m):
    items_html = ""
    for label, color in zip(CLASS_LABELS, CLASS_PALETTE):
        items_html += (
            f"<div style='display:flex;align-items:center;margin-bottom:3px;'>"
            f"<span style='display:inline-block;width:12px;height:12px;"
            f"border-radius:3px;border:1px solid #374151;"
            f"background:#{color};margin-right:6px;'></span>"
            f"<span style='font-size:11px;color:#e5e7eb;'>{label}</span>"
            f"</div>"
        )

    legend_html = f"""
    <div style="
        position: absolute;
        bottom: 12px;
        right: 12px;
        z-index: 9999;
        background-color: rgba(15,23,42,0.96);
        padding: 8px 10px;
        border-radius: 10px;
        border: 1px solid #111827;
        box-shadow: 0 10px 24px rgba(0,0,0,0.7);
    ">
      <div style="font-size:11px;font-weight:600;color:#e5e7eb;margin-bottom:4px;">
        Dynamic World
      </div>
      {items_html}
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))


# -------------------------
# 5. CHAT → MAP CONTROL (LOGIC SAME)
# -------------------------
def update_controls_from_text(text: str):
    t = text.lower().strip()

    # reset
    if "reset" in t and ("map" in t or "settings" in t or "all" in t):
        st.session_state["analysis_function"] = "change_detection"
        st.session_state["year_a"] = YEARS[max(0, len(YEARS) - 2)]
        st.session_state["year_b"] = YEARS[max(0, len(YEARS) - 1)]
        return

    # swap years
    if ("swap" in t or "switch" in t or "reverse" in t or "flip" in t) and "year" in t:
        ya = st.session_state["year_a"]
        yb = st.session_state["year_b"]
        st.session_state["year_a"], st.session_state["year_b"] = yb, ya

    # next year
    if "next year" in t:
        cur_b = st.session_state["year_b"]
        if cur_b in YEARS:
            idx = YEARS.index(cur_b)
            if idx < len(YEARS) - 1:
                st.session_state["year_b"] = YEARS[idx + 1]

    # previous / last year
    if "previous year" in t or "last year" in t:
        cur_a = st.session_state["year_a"]
        if cur_a in YEARS:
            idx = YEARS.index(cur_a)
            if idx > 0:
                st.session_state["year_a"] = YEARS[idx - 1]

    # function detection
    if "change detection" in t or "change analysis" in t or "difference" in t:
        st.session_state["analysis_function"] = "change_detection"
    elif "time series" in t or "timeseries" in t or "timeline" in t:
        st.session_state["analysis_function"] = "timeseries"
    elif "single year" in t or "only" in t:
        st.session_state["analysis_function"] = "single_year"

    # detect explicit years
    found = re.findall(r"\b(19[0-9]{2}|20[0-9]{2})\b", t)
    years_found = sorted({int(y) for y in found if int(y) in YEARS})
    if not years_found:
        return

    if len(years_found) == 1:
        st.session_state["year_a"] = years_found[0]
        st.session_state["year_b"] = years_found[0]
        if st.session_state["analysis_function"] != "timeseries":
            st.session_state["analysis_function"] = "single_year"
    else:
        st.session_state["year_a"] = years_found[0]
        st.session_state["year_b"] = years_found[-1]
        if st.session_state["analysis_function"] == "single_year":
            st.session_state["analysis_function"] = "change_detection"


# -------------------------
# 6. TOP BAR (MATCH SCREENSHOT)
# -------------------------
st.markdown(
    """
    <div class="em-topbar">
      <div>
        <div class="em-title">EarthMonitor</div>
        <div class="em-subtitle">Real-time environmental monitoring</div>
      </div>
      <div class="em-brand-right">Dynamic World · Google Earth Engine</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# 7. MAIN LAYOUT: LEFT MONITOR + RIGHT MAP/REPORT
# -------------------------
left_col, right_col = st.columns([0.26, 0.74], gap="small")

# ===== LEFT: MONITOR FUNCTIONS + ASSISTANT =====
with left_col:
    # ---- Monitor Functions card ----
    st.markdown("<div class='em-card'>", unsafe_allow_html=True)

    st.markdown(
        "<div class='em-section-title'>Monitor Functions</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='em-section-subtext'>Choose analysis mode, years, and location.</div>",
        unsafe_allow_html=True,
    )

    # Analysis mode radio (same logic)
    func_options = ["change_detection", "single_year", "timeseries"]
    func_labels = {
        "change_detection": "Change detection",
        "single_year": "Single year map",
        "timeseries": "Time series",
    }
    func_index = func_options.index(st.session_state["analysis_function"])
    selected_func = st.radio(
        "Mode",
        options=func_options,
        index=func_index,
        label_visibility="collapsed",
        format_func=lambda v: func_labels[v],
    )
    st.session_state["analysis_function"] = selected_func

    # Years
    if selected_func == "single_year":
        st.caption("Year")
        idx = YEARS.index(st.session_state["year_a"])
        year_single = st.selectbox(
            "",
            options=YEARS,
            index=idx,
            key="year_single_select",
        )
        st.session_state["year_a"] = year_single
        st.session_state["year_b"] = year_single
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            label = "Year A (Before)" if selected_func != "timeseries" else "Start year (A)"
            st.caption(label)
            idx_a = YEARS.index(st.session_state["year_a"])
            year_a = st.selectbox(
                "",
                options=YEARS,
                index=idx_a,
                key="year_a_select",
            )
            st.session_state["year_a"] = year_a
        with col_b:
            label = "Year B (After)" if selected_func != "timeseries" else "End year (B)"
            st.caption(label)
            idx_b = YEARS.index(st.session_state["year_b"])
            year_b = st.selectbox(
                "",
                options=YEARS,
                index=idx_b,
                key="year_b_select",
            )
            st.session_state["year_b"] = year_b

    st.markdown(
        "<div class='em-section-subtext' style='margin-top:4px;'>"
        "Use the EarthMonitor assistant below to change settings via text, e.g. "
        "<span style='color:#93c5fd;'>“swap years”</span> or "
        "<span style='color:#93c5fd;'>“reset map”</span>."
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='em-divider'></div>", unsafe_allow_html=True)

    # Location selection (city-based)
    st.markdown(
        "<div class='em-section-title'>Location</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='em-section-subtext'>Type a city and the map will center on it.</div>",
        unsafe_allow_html=True,
    )

    city_input = st.text_input(
        "City",
        value=st.session_state["location_city"],
        placeholder="Abu Dhabi, Dubai, Berlin...",
    )

    col_loc_btn, col_loc_info = st.columns([0.6, 0.4])
    with col_loc_btn:
        use_city = st.button("📍 Use city", key="use_city_button")
    with col_loc_info:
        st.markdown(
            f"<div style='font-size:11px;color:#9ca3af;'>"
            f"Lat {st.session_state['location_lat']:.3f}<br>"
            f"Lon {st.session_state['location_lon']:.3f}</div>",
            unsafe_allow_html=True,
        )

    if use_city and city_input.strip():
        try:
            geolocator = Nominatim(user_agent="dw-change-app")
            loc = geolocator.geocode(city_input.strip())
            if loc:
                st.session_state["location_lat"] = loc.latitude
                st.session_state["location_lon"] = loc.longitude
                st.session_state["location_name"] = city_input.strip()
                st.session_state["location_city"] = city_input.strip()
                st.success(
                    f"Location set to {city_input.strip()} "
                    f"({loc.latitude:.3f}, {loc.longitude:.3f})."
                )
            else:
                st.warning("City not found. Please check the spelling.")
        except (GeocoderUnavailable, GeocoderTimedOut):
            st.warning("Geocoding service unavailable. Try again later.")
        except Exception:
            st.warning("Something went wrong while looking up the city.")

    st.markdown("</div>", unsafe_allow_html=True)  # end Monitor card

    st.markdown("")  # small spacer

    # ---- Assistant card (chat) ----
    st.markdown("<div class='em-card-soft'>", unsafe_allow_html=True)
    st.markdown(
        "<div class='em-section-title'>Assistant</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='em-section-subtext'>"
        "Ask about the map or current changes in the selected region."
        "</div>",
        unsafe_allow_html=True,
    )

    # Chat history (display only; logic unchanged)
    st.markdown("<div class='em-chat-container'>", unsafe_allow_html=True)
    for msg in st.session_state["chat_history"]:
        if msg["role"] == "user":
            row_class = "em-chat-user"
            bubble_class = "em-chat-bubble em-chat-bubble-user"
            name = "You"
            align = "right"
        else:
            row_class = "em-chat-assistant"
            bubble_class = "em-chat-bubble em-chat-bubble-assistant"
            name = "Assistant"
            align = "left"

        st.markdown(
            f"""
            <div class="em-chat-row {row_class}">
              <div>
                <div class="em-chat-meta" style="text-align:{align};">{name}</div>
                <div class="{bubble_class}">
                  {msg["content"]}
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # Chat input
    with st.form("chat_form", clear_on_submit=True):
        placeholder = (
            "Ask about the map or changes, e.g. "
            "\"Explain the main changes\" or \"swap years\"..."
        )
        user_text = st.text_input("", placeholder=placeholder)
        run_clicked = st.form_submit_button("Send")

    if run_clicked:
        if user_text.strip():
            user_msg = user_text.strip()
        else:
            af = st.session_state["analysis_function"]
            ya = st.session_state["year_a"]
            yb = st.session_state["year_b"]
            user_msg = (
                f"Run {af} for {st.session_state['location_name']} ({ya} → {yb})."
            )

        st.session_state["chat_history"].append({"role": "user", "content": user_msg})
        update_controls_from_text(user_msg)

        af = st.session_state["analysis_function"]
        ya = st.session_state["year_a"]
        yb = st.session_state["year_b"]

        system_msg = {
            "role": "system",
            "content": (
                "You are a helpful assistant that explains Dynamic World land cover "
                "maps and changes over time in SIMPLE language. "
                "The app has three analysis modes: change_detection, single_year, timeseries. "
                f"Current mode: {af}, years: {ya}–{yb}. "
                f"The current location is {st.session_state['location_name']} "
                "centered on the provided latitude/longitude. "
                "Explain clearly what the map likely shows and any key patterns."
            ),
        }
        messages_for_api = [system_msg] + st.session_state["chat_history"]

        with st.spinner("Thinking..."):
            reply = ask_chatbot(messages_for_api)

        st.session_state["chat_history"].append(
            {"role": "assistant", "content": reply}
        )

    st.markdown("</div>", unsafe_allow_html=True)  # end Assistant card


# ===== RIGHT: MAP + REPORT & ANALYSIS =====
with right_col:
    st.markdown("<div class='em-card'>", unsafe_allow_html=True)

    af = st.session_state["analysis_function"]
    ya = st.session_state["year_a"]
    yb = st.session_state["year_b"]
    current_name = st.session_state["location_name"]
    current_lat = st.session_state["location_lat"]
    current_lon = st.session_state["location_lon"]

    # Header above map (similar to screenshot)
    c1, c2, c3 = st.columns([0.25, 0.5, 0.25])
    with c1:
        if af == "change_detection":
            st.markdown(
                "<div style='font-size:13px;font-weight:600;'>Before</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='font-size:11px;color:#9ca3af;'>{ya}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:13px;font-weight:600;'>Map view</div>",
                unsafe_allow_html=True,
            )
    with c2:
        st.markdown(
            f"<div style='text-align:center;font-size:11px;color:#9ca3af;'>{current_name}</div>",
            unsafe_allow_html=True,
        )
    with c3:
        if af == "change_detection":
            st.markdown(
                "<div style='text-align:right;font-size:13px;font-weight:600;'>After</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='text-align:right;font-size:11px;color:#9ca3af;'>{yb}</div>",
                unsafe_allow_html=True,
            )

    # Map itself (logic same as before)
    with st.spinner("Loading Dynamic World layers from Earth Engine..."):
        location_point = ee.Geometry.Point([current_lon, current_lat])

        if af == "single_year":
            tile_urls = get_dw_tile_urls(location_point, ya, ya)
        else:
            tile_urls = get_dw_tile_urls(location_point, ya, yb)

        if af == "change_detection":
            m = DualMap(
                location=[current_lat, current_lon],
                zoom_start=11,
                tiles=None,
            )

            # left (before)
            folium.TileLayer(
                tiles=(
                    "https://server.arcgisonline.com/ArcGIS/rest/services/"
                    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
                ),
                attr="Esri World Imagery",
                name="Satellite (A)",
                overlay=False,
                control=True,
            ).add_to(m.m1)
            if tile_urls.get("a"):
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["a"],
                    attr="Google Earth Engine – Dynamic World",
                    name=f"DW · Year A ({ya})",
                    overlay=True,
                    control=True,
                    opacity=0.9,
                ).add_to(m.m1)

            # right (after)
            folium.TileLayer(
                tiles=(
                    "https://server.arcgisonline.com/ArcGIS/rest/services/"
                    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
                ),
                attr="Esri World Imagery",
                name="Satellite (B)",
                overlay=False,
                control=True,
            ).add_to(m.m2)
            if tile_urls.get("b"):
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["b"],
                    attr="Google Earth Engine – Dynamic World",
                    name=f"DW · Year B ({yb})",
                    overlay=True,
                    control=True,
                    opacity=0.9,
                ).add_to(m.m2)

            if tile_urls.get("change"):
                for submap in (m.m1, m.m2):
                    folium.raster_layers.TileLayer(
                        tiles=tile_urls["change"],
                        attr="Google Earth Engine – Dynamic World Change",
                        name=f"DW · Change ({ya} → {yb})",
                        overlay=True,
                        control=True,
                        opacity=0.7,
                    ).add_to(submap)

            folium.LayerControl(collapsed=False).add_to(m.m1)
            folium.LayerControl(collapsed=False).add_to(m.m2)
            add_dw_legend_to_map(m)

        else:
            m = folium.Map(
                location=[current_lat, current_lon],
                zoom_start=11,
                tiles=None,
                control_scale=True,
            )
            folium.TileLayer(
                tiles=(
                    "https://server.arcgisonline.com/ArcGIS/rest/services/"
                    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
                ),
                attr="Esri World Imagery",
                name="Satellite",
                overlay=False,
                control=True,
            ).add_to(m)

            if af == "single_year":
                if tile_urls.get("a"):
                    folium.raster_layers.TileLayer(
                        tiles=tile_urls["a"],
                        attr="Google Earth Engine – Dynamic World",
                        name=f"DW · {ya}",
                        overlay=True,
                        control=True,
                        opacity=0.85,
                    ).add_to(m)
            else:
                if tile_urls.get("a"):
                    folium.raster_layers.TileLayer(
                        tiles=tile_urls["a"],
                        attr="Google Earth Engine – Dynamic World",
                        name=f"DW · Start ({ya})",
                        overlay=True,
                        control=True,
                        opacity=0.8,
                    ).add_to(m)
                if tile_urls.get("b"):
                    folium.raster_layers.TileLayer(
                        tiles=tile_urls["b"],
                        attr="Google Earth Engine – Dynamic World",
                        name=f"DW · End ({yb})",
                        overlay=True,
                        control=True,
                        opacity=0.8,
                    ).add_to(m)
                if tile_urls.get("change"):
                    folium.raster_layers.TileLayer(
                        tiles=tile_urls["change"],
                        attr="Google Earth Engine – Dynamic World Change",
                        name=f"DW · Change ({ya} → {yb})",
                        overlay=True,
                        control=True,
                        opacity=0.7,
                    ).add_to(m)

            folium.LayerControl(collapsed=False).add_to(m)
            add_dw_legend_to_map(m)

    st_folium(m, height=520, use_container_width=True)

    # Report & Analysis bar (like screenshot bottom)
    mode_name = {
        "change_detection": "Change detection",
        "single_year": "Single year map",
        "timeseries": "Time series",
    }[af]
    time_span = (
        "Single year"
        if af == "single_year"
        else ("Same year" if ya == yb else f"{abs(yb - ya)} years")
    )
    now_str = datetime.utcnow().strftime("%H:%M:%S")

    st.markdown(
        f"""
        <div class="em-report-bar">
          <div>
            <div class="em-report-label">Current Layer</div>
            <div class="em-report-value">{mode_name}</div>
          </div>
          <div>
            <div class="em-report-label">Selected Region</div>
            <div class="em-report-value">
              {current_lat:.2f}°, {current_lon:.2f}°
            </div>
          </div>
          <div>
            <div class="em-report-label">Last Update</div>
            <div class="em-report-value">{now_str} UTC</div>
          </div>
          <div>
            <div class="em-report-label">Report &amp; Analysis</div>
            <div class="em-report-value" style="font-weight:400;">
              {mode_name} for <span style="color:#93c5fd;">{current_name}</span>
              over <span style="color:#93c5fd;">{time_span}</span>.
              Detailed numeric change statistics require Phase-1 outputs,
              but the assistant on the left will describe key patterns.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)  # end right card
