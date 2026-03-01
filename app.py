# app.py
import json

import streamlit as st
import ee
import folium
from streamlit_folium import st_folium

from config import YEARS, LOCATION_LAT, LOCATION_LON, LOCATION_NAME
from gee_utils import get_dw_tile_urls
from chat_utils import ask_chatbot
from ui_components import render_dw_legend


# -------------------------
# 1. PAGE CONFIG & CUSTOM CSS
# -------------------------
st.set_page_config(
    page_title="GEE Chatbot – Dynamic World Explorer",
    page_icon="🌍",
    layout="wide",
)

# Light CSS to mimic your old HTML style
st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at top left, #e0f2fe, #f9fafb);
    }

    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }

    .panel-card {
        background: #ffffff;
        border-radius: 18px;
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.16);
        padding: 18px 18px 14px;
    }

    /* Hide "View fullscreen" button on folium iframe to keep it clean */
    button[title="View fullscreen"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# 2. INITIALIZE GOOGLE EARTH ENGINE (SERVICE ACCOUNT)
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

    # ServiceAccountCredentials accepts (service_account, key_data)
    credentials = ee.ServiceAccountCredentials(
        service_account_email, key_data=service_account_json
    )

    if project_id:
        ee.Initialize(credentials, project=project_id)
    else:
        ee.Initialize(credentials)

    st.session_state.ee_initialized = True


init_ee()

# Fixed study location (does not change)
location_point = ee.Geometry.Point([LOCATION_LON, LOCATION_LAT])


# -------------------------
# 3. SESSION STATE FOR CHAT HISTORY
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
# 4. LAYOUT: LEFT PANEL (controls + chat) & RIGHT PANEL (map + legend)
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

    # ---- Analysis settings card ----
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

    # Year selectors
    col_year_a, col_year_b = st.columns(2)
    with col_year_a:
        st.markdown(
            "<label style='font-size:11px;color:#6b7280;'>Year A</label>",
            unsafe_allow_html=True,
        )
        year_a = st.selectbox(
            label="",
            options=YEARS,
            index=max(0, len(YEARS) - 2),
            key="year_a_select",
        )

    with col_year_b:
        st.markdown(
            "<label style='font-size:11px;color:#6b7280;'>Year B</label>",
            unsafe_allow_html=True,
        )
        year_b = st.selectbox(
            label="",
            options=YEARS,
            index=max(0, len(YEARS) - 1),
            key="year_b_select",
        )

    # Function select (for now used in the prompt, not logic)
    st.markdown(
        "<label style='font-size:11px;color:#6b7280;margin-top:4px;'>Function</label>",
        unsafe_allow_html=True,
    )
    analysis_function = st.selectbox(
        label="",
        options=[
            "change_detection",
            "single_year",
            "timeseries",
        ],
        index=0,
        key="function_select",
    )

    st.markdown(
        "<p style='font-size:11px;color:#6b7280;margin-top:6px;'>"
        "Location is fixed to the study area. Years control which Dynamic World "
        "layers you see on the map."
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

    # Render chat history
    for msg in st.session_state["chat_history"]:
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

    # ---- Chat input + Run button ----
    with st.form("chat_form", clear_on_submit=True):
        user_text = st.text_input(
            label="",
            placeholder="Optional: ask a question about the change",
        )
        run_clicked = st.form_submit_button("▶ Run")

    if run_clicked:
        # If user typed something, use it; otherwise auto-generate a “run” message
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

        # Build messages for OpenAI
        messages_for_api = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that explains Dynamic World land "
                    "cover maps and changes over time in simple language. "
                    "The location is fixed; the user chooses Year A and Year B and "
                    "an analysis function (change_detection, single_year, timeseries). "
                    "Explain what the map likely shows, how land cover changed, "
                    "and any important patterns at that location."
                ),
            }
        ]
        messages_for_api.extend(st.session_state["chat_history"])

        # Call chatbot
        with st.spinner("Thinking..."):
            reply = ask_chatbot(messages_for_api)

        st.session_state["chat_history"].append(
            {"role": "assistant", "content": reply}
        )

    st.markdown("</div>", unsafe_allow_html=True)  # end left panel card


# ---------- RIGHT PANEL ----------
with right_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    # Header: title + caption
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
            "Use the layer control on the map to toggle Satellite / DW Year A / "
            "DW Year B / Change."
            "</div>",
            unsafe_allow_html=True,
        )

    # Map + legend side by side
    map_col, legend_col = st.columns([0.7, 0.3])

    with map_col:
        with st.spinner("Loading Dynamic World layers from Earth Engine..."):
            tile_urls = get_dw_tile_urls(location_point, year_a, year_b)

            # Create Folium map centered on AOI
            m = folium.Map(
                location=[LOCATION_LAT, LOCATION_LON],
                zoom_start=11,
                tiles=None,  # we'll define base layer manually
                control_scale=True,
            )

            # Satellite base layer (Esri imagery, similar to your old map)
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

            # Dynamic World Year A
            if tile_urls.get("a"):
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["a"],
                    attr="Google Earth Engine – Dynamic World",
                    name=f"DW · Year A ({year_a})",
                    overlay=True,
                    control=True,
                    opacity=0.8,
                ).add_to(m)

            # Dynamic World Year B
            if tile_urls.get("b"):
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["b"],
                    attr="Google Earth Engine – Dynamic World",
                    name=f"DW · Year B ({year_b})",
                    overlay=True,
                    control=True,
                    opacity=0.8,
                ).add_to(m)

            # Change layer (A → B)
            if tile_urls.get("change"):
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["change"],
                    attr="Google Earth Engine – Dynamic World Change",
                    name=f"DW · Change ({year_a} → {year_b})",
                    overlay=True,
                    control=True,
                    opacity=0.8,
                ).add_to(m)

            # Layer control (like your old layer chips/radios)
            folium.LayerControl(collapsed=False).add_to(m)

        # Embed the Folium map into Streamlit
        st_folium(m, height=480, use_container_width=True)

    with legend_col:
        render_dw_legend()

    st.markdown("</div>", unsafe_allow_html=True)  # end right panel card
