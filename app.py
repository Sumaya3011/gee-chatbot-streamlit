# app.py
import json
import re
from pathlib import Path

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
    st.session_state["year_a"] = YEARS[max(0, len(YEARS) - 2)]

if "year_b" not in st.session_state:
    st.session_state["year_b"] = YEARS[max(0, len(YEARS) - 1)]

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = [
        {
            "role": "assistant",
            "content": (
                "Hi! I can help you explore Dynamic World land cover and update the map.\n\n"
                "Chat modes:\n"
                "- **Explain map** → simple description of what the map shows\n"
                "- **Change analysis report** → structured report: Change Detection + Risk + Recommendations"
            ),
        }
    ]

# new: store last change-analysis report
if "change_report_text" not in st.session_state:
    st.session_state["change_report_text"] = None

# new: chat mode
if "chat_mode" not in st.session_state:
    st.session_state["chat_mode"] = "Explain map"


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
# 6. OPTIONAL: LOAD PHASE-1 CHANGE STATS (IF EXISTS)
# -------------------------
CHANGE_STATS_PATH = Path("outputs/change_stats.json")


def load_change_stats_if_available():
    """Try to load Phase-1 change_stats.json. If missing, return None (do not crash app)."""
    if not CHANGE_STATS_PATH.exists():
        return None
    try:
        with open(CHANGE_STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def build_change_facts_text(stats: dict | None, year_a: int, year_b: int) -> str:
    """
    Turn stats into a small JSON-like text for the model.
    If stats is None, explain that numbers are not available.
    """
    if stats is None:
        return (
            "{\n"
            f'  "note": "Phase-1 change_stats.json not found in the app. '
            f'Model should answer qualitatively based on land-cover change between {year_a} and {year_b}.",\n'
            f'  "year_a": {year_a},\n'
            f'  "year_b": {year_b}\n'
            "}"
        )

    # lightly pick some keys if present
    before_date = stats.get("before_date", f"{year_a}-01-01")
    after_date = stats.get("after_date", f"{year_b}-12-31")
    facts = {
        "time_range": f"{before_date} → {after_date}",
        "overall_change_percent": stats.get("overall_change_percent", None),
        "water_gain_percent": stats.get("water_gain_percent", None),
        "water_loss_percent": stats.get("water_loss_percent", None),
        "vegetation_loss_percent": stats.get("vegetation_loss_percent", None),
        "top_transitions": stats.get("top_transitions", [])[:3],
        "study_area": LOCATION_NAME,
    }
    return json.dumps(facts, indent=2)


def build_change_analysis_system_prompt(facts_text: str, year_a: int, year_b: int) -> str:
    """
    System message for 'Change analysis report' mode.
    This is a simplified version of your Phase-2 notebook logic.
    """
    return f"""
You are an expert climate-risk analyst for satellite-based land-cover change.

The app shows Dynamic World land cover for a fixed AOI.
The user selects Year A and Year B; the app can also compute change statistics (if available).

FACTS (from Phase-1 change_stats.json or fallback info):
{facts_text}

Current years:
- year_a (before): {year_a}
- year_b (after): {year_b}

Your job: when the user asks for a **Change analysis report**, you must output a short structured report in MARKDOWN with this structure:

### A) Change Detection
- Briefly explain the method (Dynamic World, pixel-by-pixel comparison).
- List key statistics if numbers are in FACTS (overall_change_percent, etc.).
- Natural-language summary: what changed, where, and how much – using top_transitions if present.
- If numbers are not available, say you are describing change qualitatively.

### B) Risk Analysis (Heatwave)
Explain using Hazard, Exposure, Vulnerability, Risk:
1) Hazard – qualitatively infer from changes in built-up and vegetation. Make it clear temperature data is NOT available, hazard is inferred.
2) Exposure – which areas/types of land cover are more exposed to heat.
3) Vulnerability – which land-cover types are more vulnerable (built-up) vs less (water/vegetation).
4) Risk Scoring – use formula: Risk = Hazard × Exposure × Vulnerability.
   Give a risk_level: low / medium / high and a short justification.

### C) Recommendations (Decision Support)
Start with one intro sentence:
"Based on the detected land-cover transitions and associated risk analysis, it is recommended to:"

Then give 3–5 bullet points with practical actions (avoid, mitigate, monitor).

Then three subsections:
1) Avoidance Recommendations
2) Mitigation Recommendations
3) Monitoring Recommendations

### Suggested questions
At the end, list 3–6 numbered follow-up questions the user could ask.

Important:
- Be concise (no huge walls of text).
- Use simple, clear English (suitable for non-experts).
- Never invent exact numbers that are NOT in FACTS.
""".strip()


# -------------------------
# 7. LAYOUT: LEFT (controls + chat) / RIGHT (map + report)
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
        "Explore Dynamic World land cover with AI, interactive maps, and change-analysis reports."
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
            "(e.g. 'Summarize changes and give risk + recommendations')."
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

        # build messages for ask_chatbot
        if st.session_state["chat_mode"] == "Explain map":
            system_msg = {
                "role": "system",
                "content": (
                    "You are a helpful assistant that explains Dynamic World land "
                    "cover maps and changes over time in SIMPLE language. "
                    "The app has three analysis modes: change_detection (compare two years), "
                    "single_year (one year), and timeseries (start→end years). "
                    f"Current mode: {af}, years: {ya} to {yb}. "
                    "Explain what the map likely shows and any important patterns. "
                    "Keep it short and clear."
                ),
            }
        else:
            # change-analysis mode → Phase-2 style system prompt with facts
            stats = load_change_stats_if_available()
            facts_text = build_change_facts_text(stats, ya, yb)
            system_msg = {
                "role": "system",
                "content": build_change_analysis_system_prompt(facts_text, ya, yb),
            }

        messages_for_api = [system_msg] + st.session_state["chat_history"]

        with st.spinner("Thinking..."):
            reply = ask_chatbot(messages_for_api)

        st.session_state["chat_history"].append(
            {"role": "assistant", "content": reply}
        )

        # if we are in change-analysis mode, also store report for right tab
        if st.session_state["chat_mode"] == "Change analysis report":
            st.session_state["change_report_text"] = reply

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
        if st.session_state["change_report_text"]:
            st.markdown(
                "#### Change analysis report\n"
                "_Generated from your last question in **Change analysis report** mode._\n"
            )
            st.markdown(st.session_state["change_report_text"])
        else:
            st.info(
                "No change-analysis report yet.\n\n"
                "Switch Chat mode to **Change analysis report**, ask a question, and click **Run**."
            )

    st.markdown("</div>", unsafe_allow_html=True)
