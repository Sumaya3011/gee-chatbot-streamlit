# app.py
import json
import re
import os
from pathlib import Path

import streamlit as st
import ee
import folium
from folium.plugins import DualMap
from streamlit_folium import st_folium
from openai import OpenAI

from config import (
    YEARS,
    LOCATION_LAT,
    LOCATION_LON,
    LOCATION_NAME,
    CLASS_LABELS,
    CLASS_PALETTE,
)
from gee_utils import get_dw_tile_urls
from chat_utils import ask_chatbot  # simple map-explainer chat


# -------------------------
# 1. PAGE CONFIG & CUSTOM CSS
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

    /* Chat box look */
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

    /* Hide "View fullscreen" icon to keep the map clean */
    button[title="View fullscreen"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# 2. INIT SESSION STATE
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
                "Hi! I can help you explore Dynamic World land cover and "
                "update the map when you ask for different years or analyses.\n\n"
                "Chat modes:\n"
                "- **Explain map**: simple explanation of what you see.\n"
                "- **Change analysis report**: full report (Change Detection + Risk + Recommendations)."
            ),
        }
    ]

# NEW: store the last change-analysis report text
if "change_report_text" not in st.session_state:
    st.session_state["change_report_text"] = None

# NEW: chat mode (Explain vs Change Analysis)
if "chat_mode" not in st.session_state:
    st.session_state["chat_mode"] = "Explain map"


# -------------------------
# 3. INITIALIZE GOOGLE EARTH ENGINE
# -------------------------
def init_ee():
    """Initialize Earth Engine using service account JSON from Streamlit secrets."""
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
# 4. HELPER: LEGEND BOX INSIDE MAP
# -------------------------
def add_dw_legend_to_map(m):
    """Small legend box inside the Folium map (bottom-right)."""
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
# 5. HELPER: CHAT → CONTROL MAP (years & function)
# -------------------------
def update_controls_from_text(text: str):
    """
    Make the chat control the map settings (same as before):

    - detect function: change_detection, single_year, timeseries
    - detect explicit years (2020, 2024, ...)
    - optional simple commands like "swap years", "reset map"
    """
    t = text.lower().strip()

    # Reset
    if "reset" in t and ("map" in t or "settings" in t or "all" in t):
        st.session_state["analysis_function"] = "change_detection"
        st.session_state["year_a"] = YEARS[max(0, len(YEARS) - 2)]
        st.session_state["year_b"] = YEARS[max(0, len(YEARS) - 1)]
        return

    # Swap
    if ("swap" in t or "switch" in t or "reverse" in t or "flip" in t) and "year" in t:
        ya = st.session_state["year_a"]
        yb = st.session_state["year_b"]
        st.session_state["year_a"], st.session_state["year_b"] = yb, ya

    # Next year (move end year forward)
    if "next year" in t:
        cur_b = st.session_state["year_b"]
        if cur_b in YEARS:
            idx = YEARS.index(cur_b)
            if idx < len(YEARS) - 1:
                st.session_state["year_b"] = YEARS[idx + 1]

    # Previous year (move start year back)
    if "previous year" in t or "last year" in t:
        cur_a = st.session_state["year_a"]
        if cur_a in YEARS:
            idx = YEARS.index(cur_a)
            if idx > 0:
                st.session_state["year_a"] = YEARS[idx - 1]

    # Function detection
    if "change analysis" in t or "change detection" in t or "difference" in t:
        st.session_state["analysis_function"] = "change_detection"
    elif "time series" in t or "timeseries" in t or "timeline" in t:
        st.session_state["analysis_function"] = "timeseries"
    elif "single year" in t or "only" in t:
        st.session_state["analysis_function"] = "single_year"

    # Explicit years
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
# 6. NEW: CHANGE ANALYSIS REPORT LOGIC (Phase 2 style)
# -------------------------

# where we expect your Phase-1 JSON
CHANGE_STATS_PATH = Path("outputs/change_stats.json")


def load_change_stats_for_app() -> dict:
    """
    Load Phase-1 change_stats.json for this AOI.

    Put your file in: outputs/change_stats.json (in your repo).
    """
    if not CHANGE_STATS_PATH.exists():
        st.error(
            "Change-stats file not found.\n\n"
            "Please add your Phase 1 output as 'outputs/change_stats.json' "
            "in the app repository."
        )
        st.stop()

    with open(CHANGE_STATS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_core_facts_for_app(change_stats: dict) -> dict:
    """
    Small version of your notebook's extract_core_facts:
    we use:
      - before_date / after_date
      - overall_change_percent
      - water gain/loss
      - vegetation loss
      - top_transitions (top 3)
    """
    def _safe(d, k, default=None):
        return d[k] if k in d else default

    before_date = _safe(change_stats, "before_date", "unknown_start")
    after_date = _safe(change_stats, "after_date", "unknown_end")

    overall_change_percent = float(_safe(change_stats, "overall_change_percent", 0.0))
    water_gain_percent = float(_safe(change_stats, "water_gain_percent", 0.0))
    water_loss_percent = float(_safe(change_stats, "water_loss_percent", 0.0))
    vegetation_loss_percent = float(_safe(change_stats, "vegetation_loss_percent", 0.0))

    transitions = _safe(change_stats, "top_transitions", [])
    transitions_sorted = sorted(
        transitions, key=lambda x: float(x.get("percent", 0.0)), reverse=True
    )
    top3 = transitions_sorted[:3]

    facts = {
        "time_range": f"{before_date} → {after_date}",
        "before_date": before_date,
        "after_date": after_date,
        "key_stats": {
            "overall_change_percent": overall_change_percent,
            "water_gain_percent": water_gain_percent,
            "water_loss_percent": water_loss_percent,
            "vegetation_loss_percent": vegetation_loss_percent,
        },
        "top_transitions": top3,
        "study_area": LOCATION_NAME,
    }
    return facts


def build_change_analysis_prompt(user_question: str, facts: dict) -> str:
    """
    Build a prompt similar to your Phase-2 notebook, but simpler:
    we ask for markdown (no JSON schema) with:

    A) Change Detection
    B) Risk Analysis
    C) Recommendations
    and Suggested questions at the end.
    """
    facts_blob = json.dumps(facts, indent=2)

    return f"""
You are an expert climate-risk analyst for satellite-based change detection.
Use ONLY the FACTS provided and the USER QUESTION to write a **short, clear report**
for decision-makers.

Study area: {facts.get("study_area", "Abu Dhabi AOI")}

FACTS:
{facts_blob}

USER QUESTION:
{user_question}

Write your answer in **markdown** with this structure:

### A) Change Detection
- Briefly explain the method (Dynamic World, pixel-by-pixel comparison).
- List key statistics from FACTS:
  - overall_change_percent
  - water_gain_percent
  - water_loss_percent
  - vegetation_loss_percent
- Natural-language summary: what changed, where, and how much – use top_transitions
  (e.g. trees → water, crops → built-up).

### B) Risk Analysis (Heatwave)
Explain using Hazard, Exposure, Vulnerability, Risk:
1) Hazard – explain qualitatively how built-up and vegetation changes may affect heat.
   Make it clear that temperature is NOT available: hazard is inferred.
2) Exposure – explain which kind of areas are more exposed (for example areas with big transitions).
3) Vulnerability – which land-cover classes are more vulnerable (built-up) vs less (water/vegetation).
4) Risk Scoring – Use: Risk = Hazard × Exposure × Vulnerability.
   Give a risk_level label: low / medium / high and a short justification using the numbers.

### C) Recommendations (Decision Support)
Start with one short intro paragraph:
"Based on the detected land-cover transitions and associated risk analysis, it is recommended to:"

Then give 3–5 bullet points of **practical, data-based** actions
(e.g. limit dense urban expansion in high-risk zones, increase vegetation, continuous monitoring).

Then three subsections:

1) Avoidance Recommendations
   - Actions to avoid very high-risk planning choices.

2) Mitigation Recommendations
   - Actions to reduce risk in existing or medium-risk areas.

3) Monitoring Recommendations
   - Actions for ongoing satellite monitoring and early warning.

End with a section:

### Suggested questions
- 3–6 numbered follow-up questions that a user could ask next.

Be concise, avoid long paragraphs, and make sure everything is consistent with the FACTS.
""".strip()


def get_openai_client() -> OpenAI:
    """
    Get OpenAI client from Streamlit secrets or environment.
    DO NOT hardcode the key in the code.
    """
    api_key = st.secrets.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        st.error(
            "OPENAI_API_KEY is not set.\n\n"
            "In Streamlit Cloud, add it under Settings → Secrets as OPENAI_API_KEY."
        )
        st.stop()
    return OpenAI(api_key=api_key)


def run_change_analysis_report(user_question: str) -> str:
    """
    Full Phase-2 style pipeline for the app:

    - load change_stats.json
    - extract core facts
    - build prompt
    - call OpenAI
    - return markdown report (string)
    """
    change_stats = load_change_stats_for_app()
    facts = extract_core_facts_for_app(change_stats)
    prompt = build_change_analysis_prompt(user_question, facts)

    client = get_openai_client()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    report_text = resp.choices[0].message.content
    return report_text


# -------------------------
# 7. LAYOUT: LEFT PANEL (controls + chat) & RIGHT PANEL (map + report)
# -------------------------
left_col, right_col = st.columns([0.32, 0.68], gap="large")

# ---------- LEFT PANEL ----------
with left_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    # Title row
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
        "Explore Dynamic World land cover with AI, maps, and change-analysis reports."
        "</p>",
        unsafe_allow_html=True,
    )

    # ---- Analysis settings (function first, then years) ----
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

    # Year controls depend on function
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
        "Location is fixed to the study area. Change function and years, or ask the chatbot, "
        "and the map + report will update."
        "</p>",
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)  # end settings card

    # ---- Chatbot mode ----
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

    # ---- Chatbot: fixed box with scroll ----
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

    st.markdown("</div>", unsafe_allow_html=True)  # end chat-container

    # Chat input + Run button
    with st.form("chat_form", clear_on_submit=True):
        placeholder = (
            "Ask about the map (Explain mode) or request a report "
            "(e.g. 'Summarize changes and give risk + recommendations')."
        )
        user_text = st.text_input(
            label="",
            placeholder=placeholder,
        )
        run_clicked = st.form_submit_button("▶ Run")

    if run_clicked:
        # 1) user message
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

        # 2) update map controls from text
        update_controls_from_text(user_msg)

        # 3) choose behavior by chat mode
        af = st.session_state["analysis_function"]
        ya = st.session_state["year_a"]
        yb = st.session_state["year_b"]

        if st.session_state["chat_mode"] == "Explain map":
            # simple explanation using existing chatbot
            messages_for_api = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant that explains Dynamic World land "
                        "cover maps and changes over time in simple language. "
                        "The location is fixed. The app has three analysis modes: "
                        "change_detection (compare two years), single_year (one year), "
                        "and timeseries (start year to end year). "
                        f"The current mode is {af}, with years {ya} and {yb}. "
                        "Describe what the map likely shows and any important patterns."
                    ),
                }
            ]
            messages_for_api.extend(st.session_state["chat_history"])

            with st.spinner("Thinking..."):
                reply = ask_chatbot(messages_for_api)

            st.session_state["chat_history"].append(
                {"role": "assistant", "content": reply}
            )

        else:
            # Change analysis report mode (Phase-2 style)
            with st.spinner("Building change-analysis report..."):
                report_text = run_change_analysis_report(user_msg)

            # Save report for the right-side panel
            st.session_state["change_report_text"] = report_text

            # Add a small confirmation bubble
            st.session_state["chat_history"].append(
                {
                    "role": "assistant",
                    "content": (
                        "I generated a **Change Analysis report** based on your question "
                        "and the Phase-1 statistics.\n\n"
                        "You can view it in the **'Change analysis report' tab on the right**."
                    ),
                }
            )

    st.markdown("</div>", unsafe_allow_html=True)  # end left panel card


# ---------- RIGHT PANEL (MAP + REPORT) ----------
with right_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    af = st.session_state["analysis_function"]
    ya = st.session_state["year_a"]
    yb = st.session_state["year_b"]

    st.markdown(
        "<div style='font-size:16px;font-weight:600;color:#111827;"
        "margin-bottom:4px;'>Analysis</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div style='font-size:12px;color:#6b7280;margin-bottom:8px;'>"
        f"{LOCATION_NAME} · {af} · {ya}–{yb}</div>",
        unsafe_allow_html=True,
    )

    # Two tabs: Map + Change-analysis report
    map_tab, report_tab = st.tabs(["🗺️ Map", "📊 Change analysis report"])

    # ---- MAP TAB ----
    with map_tab:
        with st.spinner("Loading Dynamic World layers from Earth Engine..."):
            if af == "single_year":
                tile_urls = get_dw_tile_urls(location_point, ya, ya)
            else:
                tile_urls = get_dw_tile_urls(location_point, ya, yb)

            if af == "change_detection":
                # DualMap split view
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
                    for map_obj in (m.m1, m.m2):
                        folium.raster_layers.TileLayer(
                            tiles=tile_urls["change"],
                            attr="Google Earth Engine – Dynamic World Change",
                            name=f"DW · Change ({ya} → {yb})",
                            overlay=True,
                            control=True,
                            opacity=0.7,
                        ).add_to(map_obj)

                folium.LayerControl(collapsed=False).add_to(m.m1)
                folium.LayerControl(collapsed=False).add_to(m.m2)

                add_dw_legend_to_map(m)

            else:
                # Single map with layers
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
                "_Generated from Phase-1 statistics + your last question._\n",
            )
            st.markdown(st.session_state["change_report_text"])
        else:
            st.info(
                "No change-analysis report yet.\n\n"
                "Use **Chat mode → Change analysis report**, ask a question, "
                "and press **Run** to generate one."
            )

    st.markdown("</div>", unsafe_allow_html=True)  # end right panel card
