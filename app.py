# app.py
import json

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
# 1. PAGE CONFIG & CUSTOM CSS
# -------------------------
st.set_page_config(
    page_title="GEE Chatbot – Dynamic World Explorer",
    page_icon="🌍",
    layout="wide",
)

# CSS to improve look, make it closer to your HTML design
st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at top left, #e0f2fe, #f9fafb);
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

    /* Make buttons a bit nicer */
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
# 4. SMALL HELPER: LEGEND INSIDE THE MAP
# -------------------------
def add_dw_legend_to_map(m):
    """Inject a small legend box inside the Folium map (bottom-right)."""
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
# 5. LAYOUT: LEFT PANEL (controls + chat) & RIGHT PANEL (map)
# -------------------------
# Make map bigger → give it more width
left_col, right_col = st.columns([0.32, 0.68], gap="large")

# ---------- LEFT PANEL ----------
with left_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

   

    # ---- Analysis settings "card" (buttons above chat) ----
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

    # Year selectors (A = before, B = after)
    col_year_a, col_year_b = st.columns(2)
    with col_year_a:
        st.markdown(
            "<label style='font-size:11px;color:#6b7280;'>Year A (Before)</label>",
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
            "<label style='font-size:11px;color:#6b7280;'>Year B (After)</label>",
            unsafe_allow_html=True,
        )
        year_b = st.selectbox(
            label="",
            options=YEARS,
            index=max(0, len(YEARS) - 1),
            key="year_b_select",
        )

    # Function select
    st.markdown(
        "<label style='font-size:11px;color:#6b7280;margin-top:4px;'>Function</label>",
        unsafe_allow_html=True,
    )
    analysis_function = st.selectbox(
        label="",
        options=["change_detection", "single_year", "timeseries"],
        index=0,
        key="function_select",
    )

    st.markdown(
        "<p style='font-size:11px;color:#6b7280;margin-top:6px;'>"
        "Location is fixed to the study area. Use the function and years to "
        "control what the map shows."
        "</p>",
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)  # end analysis settings card

    # ---- Chatbot (bottom-left): messages + input ----
    # Messages area
    st.markdown(
        "<div style='border-radius:12px;background:#f9fafb;border:1px solid #e5e7eb;"
        "padding:10px;height:260px;overflow-y:auto;margin-top:4px;'>",
        unsafe_allow_html=True,
    )

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
                white-space:pre-wrap;
              ">
                {msg["content"]}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)  # end messages box

    # Chat input + Run button directly under messages (chatbot at bottom)
    with st.form("chat_form", clear_on_submit=True):
        user_text = st.text_input(
            label="",
            placeholder="Optional: ask a question about the change",
        )
        run_clicked = st.form_submit_button("▶ Run")

    # When you click Run:
    # - logic for chat works
    # - Streamlit reruns the script, so map above also updates to current options
    if run_clicked:
        # 1) Add a user message (asked question or a default description)
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

        # 2) Prepare messages for OpenAI
        messages_for_api = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that explains Dynamic World "
                    "land cover maps and changes over time in simple language. "
                    "The location is fixed; the user chooses Year A and Year B "
                    "and an analysis function (change_detection, single_year, "
                    "timeseries). Explain what the map likely shows, how land "
                    "cover changed, and any important patterns."
                ),
            }
        ]
        messages_for_api.extend(st.session_state["chat_history"])

        # 3) Call the chatbot
        with st.spinner("Thinking..."):
            reply = ask_chatbot(messages_for_api)

        # 4) Save reply to history
        st.session_state["chat_history"].append(
            {"role": "assistant", "content": reply}
        )

    st.markdown("</div>", unsafe_allow_html=True)  # end left panel card


# ---------- RIGHT PANEL (BIG MAP) ----------
with right_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

    # Header
    head_left, head_right = st.columns([0.6, 0.4])
    with head_left:
        st.markdown(
            "<div style='font-size:16px;font-weight:600;color:#111827;"
            "margin-bottom:2px;'>Interactive map</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='font-size:12px;color:#6b7280;'>{LOCATION_NAME} · "
            f"{analysis_function} · {year_a}–{year_b}</div>",
            unsafe_allow_html=True,
        )
    with head_right:
        st.markdown(
            "<div style='font-size:11px;color:#6b7280;text-align:right;'>"
            "For change detection, the map splits: left = before (Year A), "
            "right = after (Year B). For other functions, use the layer control "
            "to toggle layers."
            "</div>",
            unsafe_allow_html=True,
        )

    # Map area (bigger height)
    with st.spinner("Loading Dynamic World layers from Earth Engine..."):
        tile_urls = get_dw_tile_urls(location_point, year_a, year_b)

        # --- CASE 1: change_detection → split map (before / after) ---
        if analysis_function == "change_detection":
            # Create DualMap (two synchronized maps side by side)
            m = DualMap(
                location=[LOCATION_LAT, LOCATION_LON],
                zoom_start=11,
                tiles=None,
            )

            # LEFT map: Year A
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
                    name=f"DW · Year A ({year_a})",
                    overlay=True,
                    control=True,
                    opacity=0.9,
                ).add_to(m.m1)

            # RIGHT map: Year B
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
                    name=f"DW · Year B ({year_b})",
                    overlay=True,
                    control=True,
                    opacity=0.9,
                ).add_to(m.m2)

            # (Optional) Show change layer as overlay on both maps
            if tile_urls.get("change"):
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["change"],
                    attr="Google Earth Engine – Dynamic World Change",
                    name=f"DW · Change ({year_a} → {year_b})",
                    overlay=True,
                    control=True,
                    opacity=0.7,
                ).add_to(m.m1)
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["change"],
                    attr="Google Earth Engine – Dynamic World Change",
                    name=f"DW · Change ({year_a} → {year_b})",
                    overlay=True,
                    control=True,
                    opacity=0.7,
                ).add_to(m.m2)

            # Layer controls on each side
            folium.LayerControl(collapsed=False).add_to(m.m1)
            folium.LayerControl(collapsed=False).add_to(m.m2)

            # Add legend to the whole DualMap (appears on top of one side)
            add_dw_legend_to_map(m)

        # --- CASE 2: other functions → single big map with layer toggles ---
        else:
            m = folium.Map(
                location=[LOCATION_LAT, LOCATION_LON],
                zoom_start=11,
                tiles=None,
                control_scale=True,
            )

            # Satellite base layer
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

            # DW Year A
            if tile_urls.get("a"):
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["a"],
                    attr="Google Earth Engine – Dynamic World",
                    name=f"DW · Year A ({year_a})",
                    overlay=True,
                    control=True,
                    opacity=0.8,
                ).add_to(m)

            # DW Year B
            if tile_urls.get("b"):
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["b"],
                    attr="Google Earth Engine – Dynamic World",
                    name=f"DW · Year B ({year_b})",
                    overlay=True,
                    control=True,
                    opacity=0.8,
                ).add_to(m)

            # Change layer
            if tile_urls.get("change"):
                folium.raster_layers.TileLayer(
                    tiles=tile_urls["change"],
                    attr="Google Earth Engine – Dynamic World Change",
                    name=f"DW · Change ({year_a} → {year_b})",
                    overlay=True,
                    control=True,
                    opacity=0.7,
                ).add_to(m)

            folium.LayerControl(collapsed=False).add_to(m)

            # Small legend box inside map
            add_dw_legend_to_map(m)

    # Embed folium (or DualMap) in Streamlit – big map
    st_folium(m, height=580, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)  # end right panel card
