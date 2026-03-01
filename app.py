# app.py
import json

import streamlit as st
import ee

from config import YEARS, LOCATION_LAT, LOCATION_LON, LOCATION_NAME
from gee_utils import create_dynamic_world_map
from chat_utils import ask_chatbot
from ui_components import render_dw_legend


# -------------------------
# 1. PAGE CONFIG & LIGHT CSS
# -------------------------
st.set_page_config(
    page_title="GEE Chatbot – Dynamic World Explorer",
    page_icon="🌍",
    layout="wide",
)

# Simple CSS to get a similar "card" feeling
st.markdown(
    """
    <style>
    /* Make background soft like your old radial gradient */
    .stApp {
        background: radial-gradient(circle at top left, #e0f2fe, #f9fafb);
    }

    /* Reduce default padding so it feels more like your HTML layout */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }

    /* Style "cards" a bit */
    .panel-card {
        background: #ffffff;
        border-radius: 18px;
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.16);
        padding: 18px 18px 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# 2. INIT EARTH ENGINE (SERVICE ACCOUNT)
# -------------------------
def init_ee():
    if getattr(st.session_state, "ee_initialized", False):
        return

    service_account_json = st.secrets.get("EE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        st.error(
            "EE_SERVICE_ACCOUNT_JSON is missing.\n\n"
            "In Streamlit Cloud, open your app → Settings → Secrets and add "
            "EE_SERVICE_ACCOUNT_JSON with your full service account JSON."
        )
        st.stop()

    info = json.loads(service_account_json)
    email = info["client_email"]
    project_id = info.get("project_id")

    credentials = ee.ServiceAccountCredentials(
        email=email,
        key_data=service_account_json,
    )

    if project_id:
        ee.Initialize(credentials, project=project_id)
    else:
        ee.Initialize(credentials)

    st.session_state.ee_initialized = True


init_ee()

location_point = ee.Geometry.Point([LOCATION_LON, LOCATION_LAT])


# -------------------------
# 3. SESSION STATE FOR CHAT
# -------------------------
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = [
        {
            "role": "assistant",
            "content": (
                "Hi! I can help you explore Dynamic World land cover and "
                "understand changes between two years at this fixed location."
            ),
        }
    ]


# -------------------------
# 4. LAYOUT: LEFT PANEL + RIGHT PANEL (like your HTML)
# -------------------------
left_col, right_col = st.columns([0.36, 0.64], gap="large")

# ---------- LEFT PANEL ----------
with left_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    # Title row (GEE Chatbot + Beta badge)
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
        "Explore Dynamic World land cover with AI + interactive maps."
        "</p>",
        unsafe_allow_html=True,
    )

    # ---- Analysis settings "card" ----
    st.markdown(
        "<div style='background:#f9fafb;border-radius:14px;"
        "border:1px solid #e5e7eb;padding:10px 10px 8px;margin-bottom:10px;'>",
        unsafe_allow_html=True,
    )

    # Header row: title + pill
    col_h1, col_pill = st.columns([0.6, 0.4])
    with col_h1:
        st.markdown(
            "<span style='font-weight:600;color:#111827;font-size:12px;'>"
            "Analysis settings</span>",
            unsafe_allow_html=True,
        )
    with col_pill:
        st.markdown(
            "<div style='font-size:10px;padding:2px 8px;border-radius:999px;"
            "background:#eef2ff;color:#4f46e5;text-align:right;'>"
            "Step 1 · Configure</div>",
            unsafe_allow_html=True,
        )

    # Year A / Year B selectors
    col_year_a, col_year_b = st.columns(2)
    with col_year_a:
        st.markdown(
            "<label style='font-size:11px;color:#6b7280;'>Year A</label>",
            unsafe_allow_html=True,
        )
        year_a = st.selectbox("", YEARS, index=len(YEARS) - 2, key="year_a_select")
    with col_year_b:
        st.markdown(
            "<label style='font-size:11px;color:#6b7280;'>Year B</label>",
            unsafe_allow_html=True,
        )
        year_b = st.selectbox("", YEARS, index=len(YEARS) - 1, key="year_b_select")

    # Function select
    st.markdown(
        "<label style='font-size:11px;color:#6b7280;margin-top:4px;'>Function</label>",
        unsafe_allow_html=True,
    )
    analysis_function = st.selectbox(
        "",
        [
            "change_detection",
            "single_year",
            "timeseries",
        ],
        index=0,
        key="function_select",
    )

    # Note: we keep AOI fixed to keep things simple and match
    # "location does not change". If you want a text box + "use map view",
    # we can add that later.

    st.markdown(
        "<p style='font-size:11px;color:#6b7280;margin-top:6px;'>"
        "Location is fixed to the study area. Years control which images "
        "you see on the map."
        "</p>",
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)  # end analysis settings card

    # ---- Messages area ----
    st.markdown(
        "<div style='border-radius:12px;background:#f9fafb;border:1px solid #e5e7eb;"
        "padding:10px;height:320px;overflow-y:auto;'>",
        unsafe_allow_html=True,
    )

    # Render chat history messages
    for msg in st.session_state["chat_history"]:
        # Similar bubble style: blue for user, grey for bot
        bg = "#dbeafe" if msg["role"] == "user" else "#f3f4f6"
        align = "flex-end" if msg["role"] == "user" else "flex-start"
        st.markdown(
            f"""
            <div style="
                display:flex;
                justify-content:{align};
                margin-bottom:6px;
            ">
              <div style="
                max-width:90%;
                padding:8px 10px;
                border-radius:12px;
                background:{bg};
                font-size:13px;
                line-height:1.4;
              ">
                {msg["content"]}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)  # end messages box

    # ---- Chat input (Run) ----
    with st.form("chat_form", clear_on_submit=True):
        user_text = st.text_input(
            "",
            placeholder="Optional: ask a question about the change",
        )
        run_clicked = st.form_submit_button("▶ Run")

    # When Run clicked: update chat + (optionally) do analysis in chatbot
    if run_clicked:
        # 1) Add user message (or system summary if empty)
        if user_text.strip():
            st.session_state["chat_history"].append(
                {"role": "user", "content": user_text.strip()}
            )
        else:
            st.session_state["chat_history"].append(
                {
                    "role": "user",
                    "content": (
                        f"Run {analysis_function} for {LOCATION_NAME} "
                        f"({year_a} → {year_b})."
                    ),
                }
            )

        # 2) Build messages for OpenAI
        messages_for_api = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that explains Dynamic World land "
                    "cover maps and changes over time in very simple language. "
                    "The location is fixed; the user chooses Year A and Year B and "
                    "an analysis function (change_detection, single_year, timeseries). "
                    "Explain what the map likely shows, how land cover changed, "
                    "and any important patterns."
                ),
            }
        ]
        messages_for_api.extend(st.session_state["chat_history"])

        # 3) Call chatbot
        with st.spinner("Thinking..."):
            reply = ask_chatbot(messages_for_api)

        # 4) Save reply
        st.session_state["chat_history"].append(
            {"role": "assistant", "content": reply}
        )

    st.markdown("</div>", unsafe_allow_html=True)  # end left panel card


# ---------- RIGHT PANEL ----------
with right_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    # Header: title + small caption
    head_left, head_right = st.columns([0.6, 0.4])
    with head_left:
        st.markdown(
            "<div style='font-size:16px;font-weight:600;color:#111827;"
            "margin-bottom:2px;'>Interactive map</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='font-size:12px;color:#6b7280;'>{LOCATION_NAME} · "
            f"Dynamic World {year_a}–{year_b}</div>",
            unsafe_allow_html=True,
        )
    with head_right:
        st.markdown(
            "<div style='font-size:11px;color:#6b7280;text-align:right;'>"
            "Use the layer control on the map to toggle DW Year A / DW Year B / Change."
            "</div>",
            unsafe_allow_html=True,
        )

    # Map + legend side by side
    map_col, legend_col = st.columns([0.7, 0.3])

    with map_col:
        with st.spinner("Loading Dynamic World layers from Earth Engine..."):
            dynamic_map = create_dynamic_world_map(location_point, year_a, year_b)

        # geemap has .to_streamlit() to embed interactive map.:contentReference[oaicite:6]{index=6}
        dynamic_map.to_streamlit(height=480)

    with legend_col:
        render_dw_legend()

    st.markdown("</div>", unsafe_allow_html=True)  # end right panel card
