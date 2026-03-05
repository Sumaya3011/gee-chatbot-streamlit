# app.py
import json
import re

import streamlit as st
import ee
import folium
from folium.plugins import DualMap
from streamlit_folium import st_folium

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
# 1. PAGE CONFIG & GLOBAL CSS (DARK DASHBOARD STYLE)
# -------------------------
st.set_page_config(
    page_title="Change Detection Analysis – Dynamic World Explorer",
    page_icon="🌍",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at top left, #020617, #020617);
        color: #e5e7eb;
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }

    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
        max-width: 1300px;
    }

    /* Generic card */
    .panel-card {
        background: #020617;
        border-radius: 18px;
        box-shadow: 0 22px 45px rgba(15, 23, 42, 0.75);
        padding: 18px 18px 16px;
        border: 1px solid #1e293b;
    }

    /* Left sidebar look */
    .sidebar-card {
        background: #020617;
        border-radius: 18px;
        box-shadow: 0 22px 45px rgba(15, 23, 42, 0.9);
        padding: 18px 16px 16px;
        border: 1px solid #1f2937;
    }

    .sidebar-section-title {
        font-size: 12px;
        font-weight: 600;
        color: #e5e7eb;
        margin-bottom: 4px;
    }

    .sidebar-subtext {
        font-size: 11px;
        color: #9ca3af;
    }

    /* Buttons */
    .stButton > button {
        border-radius: 999px;
        padding: 0.4rem 0.9rem;
        font-size: 13px;
        font-weight: 500;
        background: linear-gradient(135deg, #2563eb, #4f46e5);
        border: none;
        box-shadow: 0 8px 18px rgba(37, 99, 235, 0.45);
        color: white;
    }

    .stButton > button:hover {
        box-shadow: 0 12px 26px rgba(37, 99, 235, 0.7);
        transform: translateY(-0.5px);
    }

    /* Chat container */
    .chat-container {
        border-radius: 14px;
        background: #020617;
        border: 1px solid #1f2937;
        padding: 10px;
        height: 220px;
        overflow-y: auto;
    }

    .chat-bubble-user {
        max-width: 90%;
        padding: 7px 10px;
        border-radius: 12px;
        background: #1d4ed8;
        color: #e5e7eb;
        font-size: 13px;
        line-height: 1.4;
        white-space: pre-wrap;
    }

    .chat-bubble-assistant {
        max-width: 90%;
        padding: 7px 10px;
        border-radius: 12px;
        background: #111827;
        color: #e5e7eb;
        font-size: 13px;
        line-height: 1.4;
        white-space: pre-wrap;
    }

    /* Hide fullscreen button on folium */
    button[title="View fullscreen"] {
        display: none;
    }

    /* Small pill labels */
    .pill {
        display: inline-block;
        font-size: 10px;
        padding: 2px 8px;
        border-radius: 999px;
        background: #0f172a;
        color: #9ca3af;
        border: 1px solid #1f2937;
    }

    /* Change analysis cards */
    .metric-card {
        background: #020617;
        border-radius: 14px;
        border: 1px solid #1f2937;
        padding: 10px 12px;
    }

    .metric-label {
        font-size: 11px;
        color: #9ca3af;
        margin-bottom: 2px;
    }

    .metric-value {
        font-size: 18px;
        font-weight: 600;
        color: #f9fafb;
    }

    .metric-caption {
        font-size: 11px;
        color: #9ca3af;
        margin-top: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# 2. SESSION STATE (LOGIC KEPT SAME, + LOCATION)
# -------------------------
if "analysis_function" not in st.session_state:
    st.session_state["analysis_function"] = "change_detection"

if "year_a" not in st.session_state:
    st.session_state["year_a"] = YEARS[max(0, len(YEARS) - 2)]

if "year_b" not in st.session_state:
    st.session_state["year_b"] = YEARS[max(0, len(YEARS) - 1)]

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = [
        {
            "role": "assistant",
            "content": (
                "Hi! I can help you explore Dynamic World land cover and update the map.\n\n"
                "You can change the function and years, then ask me to explain what changed."
            ),
        }
    ]

# NEW: location in session state (defaults from config)
if "location_name" not in st.session_state:
    st.session_state["location_name"] = LOCATION_NAME

if "location_lat" not in st.session_state:
    st.session_state["location_lat"] = LOCATION_LAT

if "location_lon" not in st.session_state:
    st.session_state["location_lon"] = LOCATION_LON


# -------------------------
# 3. INIT EARTH ENGINE (UNCHANGED LOGIC)
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
# 4. MAP LEGEND (INSIDE MAP, LOGIC SAME)
# -------------------------
def add_dw_legend_to_map(m):
    items_html = ""
    for label, color in zip(CLASS_LABELS, CLASS_PALETTE):
        items_html += (
            f"<div style='display:flex;align-items:center;margin-bottom:3px;'>"
            f"<span style='display:inline-block;width:12px;height:12px;"
            f"border-radius:3px;border:1px solid #64748b;"
            f"background:#{color};margin-right:6px;'></span>"
            f"<span style='font-size:11px;color:#e5e7eb;'>{label}</span>"
            f"</div>"
        )

    legend_html = f"""
    <div style="
        position: absolute;
        bottom: 10px;
        right: 10px;
        z-index: 9999;
        background-color: rgba(15, 23, 42, 0.96);
        padding: 8px 10px;
        border-radius: 10px;
        border: 1px solid #1f2937;
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
# 5. CHAT → MAP CONTROL (SAME LOGIC)
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

    # detect years
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
# 6. TOP BAR
# -------------------------
top_left, top_right = st.columns([0.5, 0.5])

with top_left:
    st.markdown(
        "<span style='font-size:12px;color:#9ca3af;'>"
        "◀ Back to Dashboard</span>",
        unsafe_allow_html=True,
    )
with top_right:
    st.markdown(
        "<div style='text-align:right;font-size:11px;color:#6b7280;'>"
        "Dynamic World · Google Earth Engine</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div style="margin-top:4px;margin-bottom:10px;">
      <div style="font-size:20px;font-weight:600;color:#f9fafb;">
        Change Detection Analysis
      </div>
      <div style="font-size:12px;color:#9ca3af;">
        Compare environmental changes over time for your study area.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# 7. MAIN LAYOUT: LEFT SIDEBAR + RIGHT CONTENT
# -------------------------
left_col, right_col = st.columns([0.26, 0.74], gap="large")

# ===== LEFT SIDEBAR =====
with left_col:
    st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)

    # (1) DATA LAYERS SECTION REMOVED AS REQUESTED

    # Analysis settings (logic identical, only style changed)
    st.markdown(
        "<div class='sidebar-section-title'>Analysis Settings</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='sidebar-subtext'>Choose function and years.</div>",
        unsafe_allow_html=True,
    )

    func_options = ["change_detection", "single_year", "timeseries"]
    func_labels = {
        "change_detection": "Change detection (A → B)",
        "single_year": "Single year map",
        "timeseries": "Time series (A → B)",
    }
    func_index = func_options.index(st.session_state["analysis_function"])
    selected_func = st.radio(
        "Function",
        options=func_options,
        index=func_index,
        format_func=lambda v: func_labels[v],
        horizontal=False,
        label_visibility="collapsed",
    )
    st.session_state["analysis_function"] = selected_func

    if selected_func == "single_year":
        st.markdown(
            "<span class='sidebar-subtext'>Year</span>",
            unsafe_allow_html=True,
        )
        idx = YEARS.index(st.session_state["year_a"])
        year_single = st.selectbox(
            label="",
            options=YEARS,
            index=idx,
            key="year_single_select",
        )
        st.session_state["year_a"] = year_single
        st.session_state["year_b"] = year_single
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            label = (
                "Start year (A)" if selected_func == "timeseries" else "Year A (Before)"
            )
            st.markdown(
                f"<span class='sidebar-subtext'>{label}</span>",
                unsafe_allow_html=True,
            )
            idx_a = YEARS.index(st.session_state["year_a"])
            year_a = st.selectbox(
                label="",
                options=YEARS,
                index=idx_a,
                key="year_a_select",
            )
            st.session_state["year_a"] = year_a
        with col_b:
            label = (
                "End year (B)" if selected_func == "timeseries" else "Year B (After)"
            )
            st.markdown(
                f"<span class='sidebar-subtext'>{label}</span>",
                unsafe_allow_html=True,
            )
            idx_b = YEARS.index(st.session_state["year_b"])
            year_b = st.selectbox(
                label="",
                options=YEARS,
                index=idx_b,
                key="year_b_select",
            )
            st.session_state["year_b"] = year_b

    st.markdown(
        "<div class='sidebar-subtext' style='margin-top:6px;'>"
        "Use the controls below to pick the map location.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # (2) LOCATION SELECTION (NEW)
    st.markdown(
        "<div class='sidebar-section-title'>Location</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='sidebar-subtext'>Change the study area name and coordinates.</div>",
        unsafe_allow_html=True,
    )

    # Name
    location_name_input = st.text_input(
        "Location name",
        value=st.session_state["location_name"],
    )

    # Lat / Lon
    col_lat, col_lon = st.columns(2)
    with col_lat:
        lat_input = st.number_input(
            "Latitude",
            value=float(st.session_state["location_lat"]),
            format="%.6f",
        )
    with col_lon:
        lon_input = st.number_input(
            "Longitude",
            value=float(st.session_state["location_lon"]),
            format="%.6f",
        )

    # Update session state
    st.session_state["location_name"] = location_name_input.strip() or LOCATION_NAME
    st.session_state["location_lat"] = lat_input
    st.session_state["location_lon"] = lon_input

    st.markdown(
        "<div class='sidebar-subtext' style='margin-top:4px;'>"
        "The map and analysis will use this point as the center.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Chatbot title
    st.markdown(
        "<div class='sidebar-section-title' style='margin-bottom:2px;'>Chatbot</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='sidebar-subtext'>Ask about what changed or request map settings.</div>",
        unsafe_allow_html=True,
    )

    # Chat history (unchanged logic)
    st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
    for msg in st.session_state["chat_history"]:
        if msg["role"] == "user":
            align = "flex-end"
            bubble_class = "chat-bubble-user"
            name = "You"
        else:
            align = "flex-start"
            bubble_class = "chat-bubble-assistant"
            name = "Assistant"

        st.markdown(
            f"""
            <div style="display:flex;justify-content:{align};margin-bottom:6px;">
              <div>
                <div style="font-size:10px;color:#6b7280;margin-bottom:2px;
                            text-align:{'right' if msg['role']=='user' else 'left'};">
                    {name}
                </div>
                <div class="{bubble_class}">
                  {msg["content"]}
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # Chat input (logic same)
    with st.form("chat_form", clear_on_submit=True):
        placeholder = (
            "Example: \"Explain the main changes\", "
            "\"swap years\", \"reset map\"..."
        )
        user_text = st.text_input("", placeholder=placeholder)
        run_clicked = st.form_submit_button("▶ Run")

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

    st.markdown("</div>", unsafe_allow_html=True)  # end sidebar card


# ===== RIGHT CONTENT: MAP + CHANGE ANALYSIS CARDS =====
with right_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    af = st.session_state["analysis_function"]
    ya = st.session_state["year_a"]
    yb = st.session_state["year_b"]

    # current location values
    current_name = st.session_state["location_name"]
    current_lat = st.session_state["location_lat"]
    current_lon = st.session_state["location_lon"]

    # Header row above maps
    title_left, title_center, title_right = st.columns([0.33, 0.34, 0.33])
    with title_left:
        if af == "change_detection":
            st.markdown(
                "<div style='font-size:13px;font-weight:600;color:#e5e7eb;'>Before</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='font-size:11px;color:#9ca3af;'>{ya}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:13px;font-weight:600;color:#e5e7eb;'>Map view</div>",
                unsafe_allow_html=True,
            )
    with title_center:
        st.markdown(
            "<div style='text-align:center;font-size:11px;color:#6b7280;'>"
            f"{current_name}</div>",
            unsafe_allow_html=True,
        )
    with title_right:
        if af == "change_detection":
            st.markdown(
                "<div style='text-align:right;font-size:13px;font-weight:600;color:#e5e7eb;'>After</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='text-align:right;font-size:11px;color:#9ca3af;'>{yb}</div>",
                unsafe_allow_html=True,
            )

    # MAP(S)
    with st.spinner("Loading Dynamic World layers from Earth Engine..."):
        # location point for Earth Engine (now uses selected coordinates)
        location_point = ee.Geometry.Point([current_lon, current_lat])

        if af == "single_year":
            tile_urls = get_dw_tile_urls(location_point, ya, ya)
        else:
            tile_urls = get_dw_tile_urls(location_point, ya, yb)

        if af == "change_detection":
            # Dual map: before / after (logic same as before)
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
            # Single map (single_year or timeseries) – logic same
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

    # CHANGE ANALYSIS SECTION (visual only; does not depend on Phase-1 stats)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:13px;font-weight:600;color:#e5e7eb;margin-bottom:6px;'>"
        "Change Analysis</div>",
        unsafe_allow_html=True,
    )

    ca1, ca2, ca3 = st.columns([0.33, 0.33, 0.34])

    with ca1:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown(
            "<div class='metric-label'>Overall Change</div>",
            unsafe_allow_html=True,
        )
        # We don't have real % from Phase-1 here, so show N/A text
        st.markdown(
            "<div class='metric-value'>N/A</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='metric-caption'>Numerical stats require Phase-1 outputs.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with ca2:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markmarkdown(
            "<div class='metric-label'>Time Span</div>",
            unsafe_allow_html=True,
        )
        if af == "single_year":
            span_text = "Single year"
        else:
            span_text = f"{abs(yb - ya)} years" if yb != ya else "Same year"
        st.markdown(
            f"<div class='metric-value'>{span_text}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='metric-caption'>From {ya} to {yb}.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with ca3:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown(
            "<div class='metric-label'>Current Mode</div>",
            unsafe_allow_html=True,
        )
        mode_name = {
            "change_detection": "Change detection",
            "single_year": "Single year",
            "timeseries": "Time series",
        }[af]
        st.markdown(
            f"<div class='metric-value'>{mode_name}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='metric-caption'>Use chat or sidebar to switch mode.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)  # end right panel card
