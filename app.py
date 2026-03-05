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
# 1. PAGE CONFIG & GLOBAL CSS
# -------------------------
st.set_page_config(
    page_title="earthmonitor – Dynamic World Explorer",
    page_icon="🌍",
    layout="wide",
)

st.markdown(
    """
    <style>
    html, body, .stApp {
        height: 100vh;
        overflow: hidden;  /* keep one fixed page */
        background: radial-gradient(circle at top left, #020617, #020617 40%, #020617);
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }

    .block-container {
        padding-top: 0.4rem;
        padding-bottom: 0.4rem;
        padding-left: 1.0rem;
        padding-right: 1.0rem;
        max-width: 1400px;
        height: 100vh;  /* full viewport */
    }

    .app-shell {
        display: flex;
        flex-direction: row;
        height: 100%;   /* fill container */
        gap: 0.8rem;
        color: #e5e7eb;
    }

    /* SIDEBAR (LEFT) */
    .sidebar-card {
        background: radial-gradient(circle at top left, #020617, #020617);
        border-radius: 18px;
        border: 1px solid rgba(148, 163, 184, 0.35);
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.6);
        padding: 14px 14px 10px;
        height: 100%;
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    .sidebar-section {
        background: linear-gradient(145deg, rgba(15,23,42,0.95), rgba(15,23,42,0.9));
        border-radius: 14px;
        padding: 10px 11px;
        border: 1px solid rgba(51, 65, 85, 0.9);
    }

    .sidebar-title {
        font-size: 11px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #9ca3af;
        font-weight: 600;
        margin-bottom: 4px;
    }

    .sidebar-heading {
        font-size: 13px;
        font-weight: 600;
        color: #e5e7eb;
        margin-bottom: 2px;
    }

    .brand-logo {
        font-size: 15px;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: #f9fafb;
    }

    .brand-logo span {
        color: #22c55e;
    }

    /* --- CHAT STYLING (container-based) --- */

    /* Style the Streamlit container that holds the chat (identified via #chat-tag) */
    div[data-testid="stVerticalBlock"]:has(p#chat-tag) {
        border-radius: 14px;
        background: radial-gradient(circle at top, #020617, #020617 40%, #020617);
        border: 1px solid rgba(51, 65, 85, 0.95);
        padding: 8px 9px 7px;
        height: 190px;                /* compact fixed height */
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .chat-header-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .chat-header-title {
        font-size: 11px;
        font-weight: 600;
        color: #e5e7eb;
    }

    .chat-header-badge {
        font-size: 10px;
        padding: 2px 9px;
        border-radius: 999px;
        border: 1px solid rgba(55,65,81,0.95);
        color: #9ca3af;
    }

    .chat-sub {
        font-size: 9px;
        color: #9ca3af;
    }

    .chat-messages {
        flex: 1;
        overflow-y: auto;
        padding-right: 2px;
        margin-top: 3px;
        margin-bottom: 3px;
        scrollbar-width: thin;
    }

    .chat-bubble-user,
    .chat-bubble-assistant {
        max-width: 90%;
        padding: 6px 8px;
        border-radius: 10px;
        font-size: 11px;
        line-height: 1.35;
        white-space: pre-wrap;
    }

    .chat-bubble-user {
        background: linear-gradient(135deg, #22c55e, #16a34a);
        color: #f9fafb;
    }

    .chat-bubble-assistant {
        background: rgba(15, 23, 42, 0.96);
        border: 1px solid rgba(55, 65, 81, 0.95);
        color: #e5e7eb;
    }

    .chat-name {
        font-size: 9px;
        color: #6b7280;
        margin-bottom: 1px;
    }

    /* Chat input + button inside that container */
    div[data-testid="stVerticalBlock"]:has(p#chat-tag) .stTextInput > div > input {
        border-radius: 999px;
        padding: 0.25rem 0.6rem;
        background: #020617;
        border: 1px solid #1e293b;
        color: #e5e7eb;
        font-size: 11px;
    }

    div[data-testid="stVerticalBlock"]:has(p#chat-tag) .stButton > button {
        border-radius: 999px;
        padding: 0.25rem 0.7rem;
        font-size: 11px;
        font-weight: 500;
        background: linear-gradient(135deg, #22c55e, #16a34a);
        border: none;
        color: #f9fafb;
        box-shadow: 0 8px 20px rgba(22, 163, 74, 0.55);
    }

    .chat-input-row {
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* Global buttons & inputs (outside chat) */
    .stButton > button {
        border-radius: 999px;
        padding: 0.35rem 0.9rem;
        font-size: 12px;
        font-weight: 500;
        background: linear-gradient(135deg, #22c55e, #16a34a);
        border: none;
        color: #f9fafb;
    }
    .stButton > button:hover {
        box-shadow: 0 18px 40px rgba(22, 163, 74, 0.75);
    }

    .stRadio > div {
        gap: 0.4rem;
    }
    .stSelectbox > div > div {
        min-height: 2.1rem;
    }
    .stTextInput > div > input {
        border-radius: 999px;
        padding: 0.5rem 0.75rem;
        background: #020617;
        border: 1px solid #1e293b;
        color: #e5e7eb;
        font-size: 12px;
    }

    /* MAIN (RIGHT) */
    .main-column {
        height: 100%;
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
    }

    .main-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 4px 4px 2px;
    }

    .back-link {
        font-size: 11px;
        color: #9ca3af;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        cursor: default;
    }

    .back-pill {
        width: 22px;
        height: 22px;
        border-radius: 999px;
        border: 1px solid rgba(51,65,85,0.9);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        color: #e5e7eb;
        background: rgba(15,23,42,0.9);
    }

    .title-block {
        text-align: center;
        flex: 1;
    }

    .title-main {
        font-size: 15px;
        font-weight: 600;
        color: #f9fafb;
    }

    .title-sub {
        font-size: 11px;
        color: #9ca3af;
    }

    .map-card {
        background: radial-gradient(circle at top, #020617, #020617 40%, #020617);
        border-radius: 20px;
        border: 1px solid rgba(30, 64, 175, 0.6);
        box-shadow: 0 22px 50px rgba(15, 23, 42, 0.9);
        padding: 10px 12px 8px;
        flex: 1;                     /* take remaining height */
        display: flex;
        flex-direction: column;
    }

    .map-header-row {
        display: grid;
        grid-template-columns: 1.3fr 1fr 1.3fr;
        align-items: center;
        margin-bottom: 6px;
        font-size: 11px;
        color: #9ca3af;
    }

    .map-label {
        font-size: 12px;
        font-weight: 600;
        color: #f9fafb;
    }

    .map-chip {
        display: inline-flex;
        align-items: center;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 600;
    }

    .chip-before {
        background: rgba(2, 6, 23, 0.85);
        border: 1px solid rgba(59, 130, 246, 0.9);
        color: #bfdbfe;
    }

    .chip-after {
        background: rgba(2, 6, 23, 0.85);
        border: 1px solid rgba(22, 163, 74, 0.9);
        color: #bbf7d0;
        justify-self: end;
    }

    .map-date {
        font-size: 11px;
        color: #9ca3af;
    }

    .metrics-row {
        display: grid;
        grid-template-columns: 1.1fr 0.9fr 1.1fr;
        gap: 8px;
        margin-top: 6px;
    }

    .metric-card {
        background: rgba(15,23,42,0.98);
        border-radius: 14px;
        padding: 7px 9px;
        border: 1px solid rgba(30, 64, 175, 0.6);
        font-size: 11px;
    }

    .metric-label {
        font-size: 11px;
        color: #9ca3af;
        margin-bottom: 3px;
    }

    .metric-value {
        font-size: 14px;
        font-weight: 600;
        color: #f9fafb;
    }

    .metric-sub {
        font-size: 11px;
        color: #9ca3af;
        margin-top: 1px;
    }

    button[title="View fullscreen"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------
# 2. SESSION STATE
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
                "Hi, I'm the earthmonitor assistant.\n"
                "Ask me to show change between two years, a single year, "
                "or a time series (e.g., \"change 2020 to 2024\")."
            ),
        }
    ]


# -------------------------
# 3. INIT GOOGLE EARTH ENGINE
# -------------------------
def init_ee():
    if getattr(st.session_state, "ee_initialized", False):
        return

    service_account_json = st.secrets.get("EE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        st.error(
            "EE_SERVICE_ACCOUNT_JSON is missing.\n\n"
            "In Streamlit Cloud, open your app → Settings → Secrets and add:\n\n"
            "EE_SERVICE_ACCOUNT_JSON = '''\n"
            "{ your full service account JSON here }\n"
            "'''"
        )
        st.stop()

    info = json.loads(service_account_json)
    service_account_email = info["client_email"]
    project_id = info.get("project_id")

    credentials = ee.ServiceAccountCredentials(
        service_account_email, key_data=service_account_json
    )

    if project_id:
        ee.Initialize(credentials, project=project_id)
    else:
        ee.Initialize(credentials)

    st.session_state.ee_initialized = True


init_ee()
location_point = ee.Geometry.Point([LOCATION_LON, LOCATION_LAT])


# -------------------------
# 4. MAP LEGEND
# -------------------------
def add_dw_legend_to_map(m):
    items_html = ""
    for label, color in zip(CLASS_LABELS, CLASS_PALETTE):
        items_html += (
            f"<div style='display:flex;align-items:center;margin-bottom:3px;'>"
            f"<span style='display:inline-block;width:12px;height:12px;"
            f"border-radius:3px;border:1px solid #0f172a;"
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
        padding: 7px 9px;
        border-radius: 12px;
        border: 1px solid rgba(51, 65, 85, 0.95);
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.95);
    ">
      <div style="font-size:11px;font-weight:600;color:#f9fafb;margin-bottom:4px;">
        Dynamic World
      </div>
      {items_html}
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))


# -------------------------
# 5. CHAT → CONTROL MAP
# -------------------------
def update_controls_from_text(text: str):
    t = text.lower()

    if "change" in t or "difference" in t:
        st.session_state["analysis_function"] = "change_detection"
    elif "time series" in t or "timeseries" in t or "timeline" in t:
        st.session_state["analysis_function"] = "timeseries"
    elif "single year" in t or "only" in t:
        st.session_state["analysis_function"] = "single_year"

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
# 6. LAYOUT (SIDEBAR + MAIN)
# -------------------------
st.markdown("<div class='app-shell'>", unsafe_allow_html=True)

left_col, right_col = st.columns([0.26, 0.74], gap="medium")

# ========== LEFT COLUMN: SIDEBAR ==========
with left_col:
    st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)

    st.markdown(
        """
        <div style="display:flex;flex-direction:column;gap:6px;">
          <div class="brand-logo">earth<span>monitor</span></div>
          <div class="sidebar-title">Analysis controls</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Analysis settings
    st.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sidebar-heading'>Mode &amp; Years</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='font-size:10px;color:#9ca3af;margin-bottom:4px;'>"
        "Choose the analysis function and years. The map on the right updates automatically."
        "</div>",
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
        idx = YEARS.index(st.session_state["year_a"])
        st.markdown(
            "<div style='font-size:10px;color:#9ca3af;margin-top:2px;'>Year</div>",
            unsafe_allow_html=True,
        )
        year_single = st.selectbox(
            label="",
            options=YEARS,
            index=idx,
            key="year_single_select",
        )
        st.session_state["year_a"] = year_single
        st.session_state["year_b"] = year_single
    else:
        col_year_a, col_year_b = st.columns(2)
        with col_year_a:
            label = (
                "Start (A)" if selected_func == "timeseries" else "Year A (Before)"
            )
            st.markdown(
                f"<div style='font-size:10px;color:#9ca3af;'>{label}</div>",
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

        with col_year_b:
            label = (
                "End (B)" if selected_func == "timeseries" else "Year B (After)"
            )
            st.markdown(
                f"<div style='font-size:10px;color:#9ca3af;'>{label}</div>",
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
        "<div style='font-size:10px;color:#6b7280;margin-top:4px;'>"
        "Location is fixed to the study area. Use the chatbot below or these controls."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # Chat – single container (box) with messages + input
    chat_container = st.container()
    with chat_container:
        # marker so CSS can find this container
        st.markdown('<p id="chat-tag"></p>', unsafe_allow_html=True)

        st.markdown(
            """
            <div class="chat-header-row">
              <div class="chat-header-title">Assistant</div>
              <div class="chat-header-badge">earthmonitor</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='chat-sub'>Ask for years or modes and I’ll explain what the map shows.</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div class='chat-messages'>", unsafe_allow_html=True)
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
                <div style="display:flex;justify-content:{align};margin-bottom:4px;">
                  <div style="max-width:100%;">
                    <div class="chat-name" style="text-align:{'right' if msg['role']=='user' else 'left'};">
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
        st.markdown("</div>", unsafe_allow_html=True)  # close chat-messages

        col_input, col_btn = st.columns([4, 1])
        with col_input:
            user_text = st.text_input(
                label="",
                placeholder="e.g. change 2020 to 2024",
                key="chat_input",
            )
        with col_btn:
            run_clicked = st.button("▶", key="chat_run")

    st.markdown("</div>", unsafe_allow_html=True)  # sidebar-card

# Handle chat after sidebar so map reacts
if run_clicked:
    text = user_text.strip()
    if text:
        user_msg = text
    else:
        af = st.session_state["analysis_function"]
        ya = st.session_state["year_a"]
        yb = st.session_state["year_b"]
        user_msg = f"Run {af} for {LOCATION_NAME} ({ya} → {yb})."

    st.session_state["chat_history"].append({"role": "user", "content": user_msg})
    update_controls_from_text(user_msg)

    af = st.session_state["analysis_function"]
    ya = st.session_state["year_a"]
    yb = st.session_state["year_b"]

    messages_for_api = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant inside an app called earthmonitor. "
                "The app has a fixed study area and three analysis modes: "
                "change_detection (compare two years), single_year (one year), "
                "and timeseries (start year to end year). "
                f"The current mode is {af}, with years {ya} and {yb}. "
                "Explain what the map likely shows and any important patterns, "
                "in simple language."
            ),
        }
    ]
    messages_for_api.extend(st.session_state["chat_history"])

    with st.spinner("Thinking..."):
        reply = ask_chatbot(messages_for_api)

    st.session_state["chat_history"].append(
        {"role": "assistant", "content": reply}
    )
    st.session_state["chat_input"] = ""  # clear input


# ========== RIGHT COLUMN: MAIN AREA ==========
with right_col:
    st.markdown("<div class='main-column'>", unsafe_allow_html=True)

    # Header
    st.markdown(
        """
        <div class="main-header">
          <div class="back-link">
            <div class="back-pill">←</div>
            <span>Back to Dashboard</span>
          </div>
          <div class="title-block">
            <div class="title-main">Change Detection Analysis</div>
            <div class="title-sub">Compare environmental changes over time</div>
          </div>
          <div style="width:90px;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Map card
    st.markdown("<div class='map-card'>", unsafe_allow_html=True)

    af = st.session_state["analysis_function"]
    ya = st.session_state["year_a"]
    yb = st.session_state["year_b"]

    if af == "change_detection":
        st.markdown(
            f"""
            <div class="map-header-row">
              <div>
                <div class="map-label">Before</div>
                <div class="map-date">Jan 1, {ya}</div>
              </div>
              <div style="text-align:center;">
                <span class="map-chip chip-before">A</span>
                <span style="margin:0 6px;color:#6b7280;">→</span>
                <span class="map-chip chip-after">B</span>
              </div>
              <div style="text-align:right;">
                <div class="map-label">After</div>
                <div class="map-date">Dec 31, {yb}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        label_mid = "Single Year Map" if af == "single_year" else "Time Series"
        st.markdown(
            f"""
            <div class="map-header-row">
              <div></div>
              <div style="text-align:center;">
                <div class="map-label">{label_mid}</div>
                <div class="map-date">{ya} – {yb}</div>
              </div>
              <div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Map logic
    with st.spinner("Loading Dynamic World layers from Earth Engine..."):
        if af == "single_year":
            tile_urls = get_dw_tile_urls(location_point, ya, ya)
        else:
            tile_urls = get_dw_tile_urls(location_point, ya, yb)

        if af == "change_detection":
            m = DualMap(
                location=[LOCATION_LAT, LOCATION_LON],
                zoom_start=11,
                tiles=None,
            )

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
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["change"],
                    attr="Google Earth Engine – Dynamic World Change",
                    name=f"DW · Change ({ya} → {yb})",
                    overlay=True,
                    control=True,
                    opacity=0.7,
                ).add_to(m.m1)
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["change"],
                    attr="Google Earth Engine – Dynamic World Change",
                    name=f"DW · Change ({ya} → {yb})",
                    overlay=True,
                    control=True,
                    opacity=0.7,
                ).add_to(m.m2)

            folium.LayerControl(collapsed=False).add_to(m.m1)
            folium.LayerControl(collapsed=False).add_to(m.m2)

            add_dw_legend_to_map(m)

        else:
            m = folium.Map(
                location=[LOCATION_LAT, LOCATION_LON],
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

    st_folium(m, height=360, use_container_width=True)

    # Metrics under map
    if af == "change_detection":
        mode_label = "Change detection"
        summary = f"{ya} → {yb}"
    elif af == "single_year":
        mode_label = "Single year"
        summary = f"{ya}"
    else:
        mode_label = "Time series"
        summary = f"{ya} – {yb}"

    st.markdown(
        """
        <div style="font-size:11px;color:#9ca3af;margin-top:6px;margin-bottom:3px;">
          Change Analysis
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='metrics-row'>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">Mode</div>
          <div class="metric-value">{mode_label}</div>
          <div class="metric-sub">Driven by controls &amp; chatbot</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">Selected years</div>
          <div class="metric-value">{summary}</div>
          <div class="metric-sub">Earth Engine Dynamic World</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">Study area</div>
          <div class="metric-value">{LOCATION_NAME}</div>
          <div class="metric-sub">Location fixed in this demo</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)  # metrics-row
    st.markdown("</div>", unsafe_allow_html=True)  # map-card
    st.markdown("</div>", unsafe_allow_html=True)  # main-column

st.markdown("</div>", unsafe_allow_html=True)  # app-shell
