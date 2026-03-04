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
# 1. PAGE CONFIG & CSS (fixed one-page layout)
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
        overflow: hidden; /* prevent page scroll */
    }

    .block-container {
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        max-width: 1300px;
        height: 100%;
    }

    /* Main container uses full height */
    .full-height-layout {
        display: flex;
        flex-direction: column;
        height: 100%;
        gap: 0.4rem;
    }

    .stApp {
        background: radial-gradient(circle at top left, #e0f2fe, #f9fafb);
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }

    .panel-card {
        background: #ffffff;
        border-radius: 18px;
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.16);
        padding: 12px 14px 10px;
    }

    .stButton > button {
        border-radius: 999px;
        padding: 0.45rem 0.9rem;
        font-size: 13px;
        font-weight: 500;
        background: linear-gradient(135deg, #2563eb, #4f46e5);
        border: none;
        box-shadow: 0 8px 18px rgba(37, 99, 235, 0.35);
    }

    .stButton > button:hover {
        box-shadow: 0 12px 24px rgba(37, 99, 235, 0.45);
    }

    /* Chat box: one fixed card with internal scroll for messages */
    .chat-box {
        border-radius: 14px;
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        padding: 8px;
        height: 260px;           /* fixed height */
        display: flex;
        flex-direction: column;
    }

    .chat-messages {
        flex: 1;
        overflow-y: auto;
        margin-bottom: 6px;
    }

    .chat-bubble-user {
        max-width: 90%;
        padding: 8px 10px;
        border-radius: 12px;
        background: #2563eb;
        color: #ffffff;
        font-size: 13px;
        line-height: 1.4;
        white-space: pre-wrap;
    }

    .chat-bubble-assistant {
        max-width: 90%;
        padding: 8px 10px;
        border-radius: 12px;
        background: #f3f4f6;
        color: #111827;
        font-size: 13px;
        line-height: 1.4;
        white-space: pre-wrap;
    }

    button[title="View fullscreen"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# 2. SESSION STATE (function + years + chat)
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
                "Hi! I’m the earthmonitor assistant.\n\n"
                "I can update the map when you ask for different years or analyses.\n"
                "Try things like:\n"
                "- \"Show change between 2020 and 2024\"\n"
                "- \"Single year 2022\"\n"
                "- \"Time series from 2020 to 2024\""
            ),
        }
    ]


# -------------------------
# 3. INIT GOOGLE EARTH ENGINE (service account)
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
# 4. MAP LEGEND (inside map)
# -------------------------
def add_dw_legend_to_map(m):
    items_html = ""
    for label, color in zip(CLASS_LABELS, CLASS_PALETTE):
        items_html += (
            f"<div style='display:flex;align-items:center;margin-bottom:3px;'>"
            f"<span style='display:inline-block;width:12px;height:12px;"
            f"border-radius:3px;border:1px solid #d1d5db;"
            f"background:#{color};margin-right:6px;'></span>"
            f"<span style='font-size:11px;color:#374151;'>{label}</span>"
            f"</div>"
        )

    legend_html = f"""
    <div style="
        position: absolute;
        bottom: 10px;
        right: 10px;
        z-index: 9999;
        background-color: rgba(255, 255, 255, 0.95);
        padding: 6px 8px;
        border-radius: 10px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 6px 14px rgba(15, 23, 42, 0.18);
    ">
      <div style="font-size:11px;font-weight:600;color:#111827;margin-bottom:4px;">
        Dynamic World
      </div>
      {items_html}
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))


# -------------------------
# 5. CHAT → CONTROL MAP (simple parser)
# -------------------------
def update_controls_from_text(text: str):
    t = text.lower()

    # Function detection
    if "change" in t or "difference" in t:
        st.session_state["analysis_function"] = "change_detection"
    elif "time series" in t or "timeseries" in t or "timeline" in t:
        st.session_state["analysis_function"] = "timeseries"
    elif "single year" in t or "only" in t:
        st.session_state["analysis_function"] = "single_year"

    # Year detection
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
# 6. LAYOUT (header + left/right panels)
# -------------------------
st.markdown("<div class='full-height-layout'>", unsafe_allow_html=True)

# Top: big brand header (earthmonitor)
st.markdown(
    """
    <div style="text-align:center;margin-bottom:0.2rem;">
      <div style="
        font-size:34px;
        font-weight:800;
        letter-spacing:0.18em;
        text-transform:uppercase;
        color:#0f172a;
      ">
        earth<span style="color:#2563eb;">monitor</span>
      </div>
      <div style="font-size:12px;color:#6b7280;margin-top:2px;">
        Dynamic World Land Cover Explorer
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Main content: two columns filling the rest of height
left_col, right_col = st.columns([0.32, 0.68], gap="large")

# ---------- LEFT: controls + chat in bottom box ----------
with left_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    # --- Analysis settings card (top) ---
    st.markdown(
        "<div style='background:#f9fafb;border-radius:14px;"
        "border:1px solid #e5e7eb;padding:8px 10px 8px;margin-bottom:8px;'>",
        unsafe_allow_html=True,
    )

    header_col, pill_col = st.columns([0.6, 0.4])
    with header_col:
        st.markdown(
            "<span style='font-weight:600;color:#111827;font-size:12px;'>"
            "Analysis settings</span>",
            unsafe_allow_html=True,
        )
    with pill_col:
        st.markdown(
            "<div style='font-size:10px;padding:2px 8px;border-radius:999px;"
            "background:#eef2ff;color:#4f46e5;text-align:right;'>"
            "Step 1 · Configure</div>",
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
    )
    st.session_state["analysis_function"] = selected_func

    if selected_func == "single_year":
        st.markdown(
            "<label style='font-size:11px;color:#6b7280;margin-top:2px;'>Year</label>",
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
        col_year_a, col_year_b = st.columns(2)
        with col_year_a:
            label = (
                "Start year (A)"
                if selected_func == "timeseries"
                else "Year A (Before)"
            )
            st.markdown(
                f"<label style='font-size:11px;color:#6b7280;'>{label}</label>",
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
                "End year (B)"
                if selected_func == "timeseries"
                else "Year B (After)"
            )
            st.markdown(
                f"<label style='font-size:11px;color:#6b7280;'>{label}</label>",
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
        "<p style='font-size:11px;color:#6b7280;margin-top:4px;margin-bottom:4px;'>"
        "Location is fixed to the study area. Change years here, or ask the chatbot "
        "and the map will update automatically."
        "</p>",
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)  # end settings card

    # --- Chatbox: ONE fixed box at bottom-left ---
    st.markdown(
        "<div class='chat-box'>"
        "<div style='font-size:12px;font-weight:600;color:#111827;margin-bottom:4px;'>"
        "Chatbot</div>",
        unsafe_allow_html=True,
    )

    # Messages (scroll inside)
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

    st.markdown("</div>", unsafe_allow_html=True)  # end chat-messages

    # Input + button still visually part of same "box"
    with st.form("chat_form", clear_on_submit=True):
        user_text = st.text_input(
            label="",
            placeholder="Ask about years, change, or time series…",
        )
        run_clicked = st.form_submit_button("▶ Run")

    st.markdown("</div>", unsafe_allow_html=True)  # end chat-box

    if run_clicked:
        if user_text.strip():
            user_msg = user_text.strip()
        else:
            af = st.session_state["analysis_function"]
            ya = st.session_state["year_a"]
            yb = st.session_state["year_b"]
            user_msg = f"Run {af} for {LOCATION_NAME} ({ya} → {yb})."

        st.session_state["chat_history"].append(
            {"role": "user", "content": user_msg}
        )

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

    st.markdown("</div>", unsafe_allow_html=True)  # end left panel-card


# ---------- RIGHT: map panel ----------
with right_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    af = st.session_state["analysis_function"]
    ya = st.session_state["year_a"]
    yb = st.session_state["year_b"]

    head_left, head_right = st.columns([0.6, 0.4])
    with head_left:
        st.markdown(
            "<div style='font-size:15px;font-weight:600;color:#111827;"
            "margin-bottom:2px;'>Interactive map</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='font-size:12px;color:#6b7280;'>{LOCATION_NAME} · "
            f"{af} · {ya}–{yb}</div>",
            unsafe_allow_html=True,
        )
    with head_right:
        st.markdown(
            "<div style='font-size:11px;color:#6b7280;text-align:right;'>"
            "Change detection: split view (left = before, right = after).<br>"
            "Other modes: use the layer control to toggle layers."
            "</div>",
            unsafe_allow_html=True,
        )

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

            # LEFT: Year A
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

            # RIGHT: Year B
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

    # Slightly smaller map height so page fits with no scroll
    st_folium(m, height=430, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)  # end right panel-card

st.markdown("</div>", unsafe_allow_html=True)  # end full-height-layout
