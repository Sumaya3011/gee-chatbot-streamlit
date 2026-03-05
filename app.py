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
from change_report_utils import run_change_report  # <-- Phase-2 logic here


# -------------------------
# 1. PAGE CONFIG & CSS
# -------------------------
st.set_page_config(
    page_title="GEE Chatbot – Dynamic World Explorer",
    page_icon="🌍",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at top left, #e0f2fe, #f9fafb);
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }

    .block-container {
        padding-top: 0.8rem;
        padding-bottom: 0.8rem;
        max-width: 1300px;
    }

    .panel-card {
        background: #ffffff;
        border-radius: 18px;
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.16);
        padding: 18px 18px 14px;
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

    .chat-container {
        border-radius: 14px;
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        padding: 10px;
        height: 260px;
        overflow-y: auto;
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
# 2. SESSION STATE
# -------------------------
if "analysis_function" not in st.session_state:
    st.session_state["analysis_function"] = "change_detection"

if "year_a" not in st.session_state:
    # second last year as default A
    st.session_state["year_a"] = YEARS[max(0, len(YEARS) - 2)]

if "year_b" not in st.session_state:
    # last year as default B
    st.session_state["year_b"] = YEARS[max(0, len(YEARS) - 1)]

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = [
        {
            "role": "assistant",
            "content": (
                "Hi! I can help you explore Dynamic World land cover and update the map.\n\n"
                "Chat modes:\n"
                "- **Explain map** → simple description of what the map shows.\n"
                "- **Change analysis report** → Phase-2 style report (Change Detection + Risk + Recommendations)."
            ),
        }
    ]

# new: chat mode (Explain map / Change analysis report)
if "chat_mode" not in st.session_state:
    st.session_state["chat_mode"] = "Explain map"

# new: store last change-analysis report
if "change_report_text" not in st.session_state:
    st.session_state["change_report_text"] = None

if "change_report_json" not in st.session_state:
    st.session_state["change_report_json"] = None


# -------------------------
# 3. INIT EARTH ENGINE
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
location_point = ee.Geometry.Point([LOCATION_LON, LOCATION_LAT])


# -------------------------
# 4. MAP LEGEND (INSIDE MAP)
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
# 5. CHAT → MAP CONTROL
# -------------------------
def update_controls_from_text(text: str):
    """
    Let the chat control function and years.
    """
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
    if "change analysis" in t or "change detection" in t or "difference" in t:
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
# 6. LAYOUT: LEFT (controls+chat) / RIGHT (map+report)
# -------------------------
left_col, right_col = st.columns([0.32, 0.68], gap="large")

# ===== LEFT PANEL =====
with left_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    # Title
    col_title, col_badge = st.columns([0.7, 0.3])
    with col_title:
        st.markdown("### GEE Chatbot")
    with col_badge:
        st.markdown(
            "<span style='font-size:10px;padding:2px 6px;border-radius:999px;"
            "background:#eff6ff;color:#1d4ed8;font-weight:600;"
            "text-transform:uppercase;letter-spacing:0.04em;'>Beta</span>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<p style='font-size:12px;color:#6b7280;margin-top:2px;'>"
        "Explore Dynamic World land cover with AI, interactive maps, and Phase-2 change-analysis reports."
        "</p>",
        unsafe_allow_html=True,
    )

    # --- Analysis settings card ---
    st.markdown(
        "<div style='background:#f9fafb;border-radius:14px;"
        "border:1px solid #e5e7eb;padding:10px 10px 8px;margin-bottom:10px;'>",
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

    # Year controls
    if selected_func == "single_year":
        st.markdown(
            "<label style='font-size:11px;color:#6b7280;margin-top:4px;'>Year</label>",
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
        "<p style='font-size:11px;color:#6b7280;margin-top:6px;'>"
        "Location is fixed to the study area. Change function and years, or use the chatbot."
        "</p>",
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # --- Chat mode switch ---
    st.markdown(
        "<div style='font-size:12px;font-weight:600;color:#111827;margin-bottom:4px;'>"
        "Chat mode</div>",
        unsafe_allow_html=True,
    )
    mode_options = ["Explain map", "Change analysis report"]
    mode_index = mode_options.index(st.session_state["chat_mode"])
    chat_mode = st.radio(
        "Chat mode",
        options=mode_options,
        index=mode_index,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state["chat_mode"] = chat_mode

    # --- Chat box ---
    st.markdown(
        "<div style='font-size:12px;font-weight:600;color:#111827;margin-bottom:4px;'>"
        "Chatbot</div>",
        unsafe_allow_html=True,
    )

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

    # --- Chat input form ---
    with st.form("chat_form", clear_on_submit=True):
        placeholder = (
            "Ask about the map, or for a report "
            "(e.g. 'Summarize changes and give heatwave risk + recommendations')."
        )
        user_text = st.text_input("", placeholder=placeholder)
        run_clicked = st.form_submit_button("▶ Run")

    if run_clicked:
        # user message
        if user_text.strip():
            user_msg = user_text.strip()
        else:
            af = st.session_state["analysis_function"]
            ya = st.session_state["year_a"]
            yb = st.session_state["year_b"]
            user_msg = f"Run {af} for {LOCATION_NAME} ({ya} → {yb})."

        st.session_state["chat_history"].append({"role": "user", "content": user_msg})

        # update map controls from text
        update_controls_from_text(user_msg)

        af = st.session_state["analysis_function"]
        ya = st.session_state["year_a"]
        yb = st.session_state["year_b"]

        if st.session_state["chat_mode"] == "Explain map":
            # old simple chatbot using ask_chatbot
            system_msg = {
                "role": "system",
                "content": (
                    "You are a helpful assistant that explains Dynamic World land "
                    "cover maps and changes over time in SIMPLE language. "
                    "The app has three analysis modes: change_detection (compare two years), "
                    "single_year (one year), and timeseries (start→end years). "
                    f"Current mode: {af}, years: {ya}–{yb}. "
                    "Explain what the map likely shows and any important patterns. "
                    "Keep it short and clear."
                ),
            }
            messages_for_api = [system_msg] + st.session_state["chat_history"]

            with st.spinner("Thinking..."):
                reply = ask_chatbot(messages_for_api)

            st.session_state["chat_history"].append(
                {"role": "assistant", "content": reply}
            )

        else:
            # NEW: Phase-2 report using run_change_report
            try:
                with st.spinner("Generating change-analysis report..."):
                    out = run_change_report(user_msg)  # uses Phase-2 notebook logic

                st.session_state["change_report_text"] = out["report_text"]
                st.session_state["change_report_json"] = out["report_json"]

                st.session_state["chat_history"].append(
                    {
                        "role": "assistant",
                        "content": (
                            "I generated a **Change Analysis report** using the Phase-2 logic.\n\n"
                            "You can view it in the **'Change analysis report' tab on the right**."
                        ),
                    }
                )
            except Exception as e:
                st.session_state["change_report_text"] = None
                st.session_state["change_report_json"] = None
                st.session_state["chat_history"].append(
                    {
                        "role": "assistant",
                        "content": (
                            "Sorry, I couldn't generate the change-analysis report. "
                            f"Error: {e}"
                        ),
                    }
                )

    st.markdown("</div>", unsafe_allow_html=True)  # end left panel card


# ===== RIGHT PANEL =====
with right_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    af = st.session_state["analysis_function"]
    ya = st.session_state["year_a"]
    yb = st.session_state["year_b"]

    st.markdown(
        "<div style='font-size:16px;font-weight:600;color:#111827;margin-bottom:4px;'>"
        "Analysis</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='font-size:12px;color:#6b7280;margin-bottom:8px;'>"
        f"{LOCATION_NAME} · {af} · {ya}–{yb}</div>",
        unsafe_allow_html=True,
    )

    # tabs: map + report
    map_tab, report_tab = st.tabs(["🗺️ Map", "📊 Change analysis report"])

    # ---- MAP TAB ----
    with map_tab:
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

                # left: year A
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

                # right: year B
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

                # optional change overlay
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

        st_folium(m, height=580, use_container_width=True)

    # ---- REPORT TAB ----
    with report_tab:
        r_text = st.session_state.get("change_report_text")
        r_json = st.session_state.get("change_report_json")

        if not r_text or not r_json:
            st.info(
                "No change-analysis report yet.\n\n"
                "Switch Chat mode to **Change analysis report**, ask a question, and click **Run**."
            )
        else:
            cd = r_json["change_detection"]
            ra = r_json["risk_analysis"]
            rec = r_json["recommendations"]
            sugg = r_json["suggested_questions"]

            st.markdown("#### Change Detection – key stats")
            c1, c2 = st.columns(2)
            with c1:
                st.metric(
                    "Overall change (%)",
                    f"{cd['key_stats']['overall_change_percent']:.2f}",
                )
                st.metric(
                    "Water gain (%)",
                    f"{cd['key_stats']['water_gain_percent']:.2f}",
                )
            with c2:
                st.metric(
                    "Water loss (%)",
                    f"{cd['key_stats']['water_loss_percent']:.2f}",
                )
                st.metric(
                    "Vegetation loss (%)",
                    f"{cd['key_stats']['vegetation_loss_percent']:.2f}",
                )

            st.markdown("---")
            st.markdown("#### Full report")
            st.markdown(r_text)

            st.markdown("---")
            st.markdown("#### Suggested questions")
            for i, q in enumerate(sugg, start=1):
                st.markdown(f"{i}. {q}")

    st.markdown("</div>", unsafe_allow_html=True)
