# app.py
import json

import streamlit as st
import ee

from config import YEARS, LOCATION_LAT, LOCATION_LON, LOCATION_NAME
from gee_utils import get_comparison_images
from chat_utils import ask_chatbot
from ui_components import render_legend


# -------------------------
# 1. PAGE CONFIG
# -------------------------
st.set_page_config(
    page_title="GEE Dynamic World Chatbot",
    page_icon="🌍",
    layout="wide",
)

st.title("🌍 GEE Dynamic World Chatbot")
st.caption(
    "Compare Dynamic World land cover for two years at a fixed location "
    "and chat with an AI assistant about the changes."
)


# -------------------------
# 2. INITIALIZE GOOGLE EARTH ENGINE (SERVICE ACCOUNT)
# -------------------------
def init_earth_engine():
    """
    Initialize Earth Engine using a service account JSON
    stored in Streamlit secrets as EE_SERVICE_ACCOUNT_JSON.
    """
    if getattr(st.session_state, "ee_initialized", False):
        return  # Already initialized in this session

    service_account_json = st.secrets.get("EE_SERVICE_ACCOUNT_JSON", None)
    if not service_account_json:
        st.error(
            "EE_SERVICE_ACCOUNT_JSON is missing. "
            "Go to Streamlit Cloud -> App -> Settings -> Secrets and add it."
        )
        st.stop()

    info = json.loads(service_account_json)

    service_account_email = info["client_email"]
    project_id = info.get("project_id", None)

    credentials = ee.ServiceAccountCredentials(
        email=service_account_email,
        key_data=service_account_json,
    )

    if project_id:
        ee.Initialize(credentials, project=project_id)
    else:
        ee.Initialize(credentials)

    st.session_state.ee_initialized = True


init_earth_engine()

# Define fixed location point
location_point = ee.Geometry.Point([LOCATION_LON, LOCATION_LAT])


# -------------------------
# 3. SIDEBAR CONTROLS
# -------------------------
with st.sidebar:
    st.header("🧭 Map Settings")

    st.markdown(
        f"**Location:** {LOCATION_NAME}  \n"
        f"Lat: `{LOCATION_LAT}`, Lon: `{LOCATION_LON}`"
    )

    year_a = st.selectbox("Year A (left)", YEARS, index=0)
    year_b = st.selectbox("Year B (right)", YEARS, index=len(YEARS) - 1)

    generate_map = st.button("🗺️ Generate Map", type="primary")


# -------------------------
# 4. CHAT SESSION STATE
# -------------------------
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = [
        {
            "role": "assistant",
            "content": (
                "Hi! I can help you understand the Dynamic World land cover "
                "map and the changes between the two years."
            ),
        }
    ]


# -------------------------
# 5. MAP + LEGEND LAYOUT
# -------------------------
map_col, legend_col = st.columns([3, 1])

with map_col:
    st.subheader("Dynamic World Comparison")

    if generate_map:
        with st.spinner("Requesting images from Google Earth Engine..."):
            try:
                img_a, img_b = get_comparison_images(location_point, year_a, year_b)

                st.markdown(f"**{LOCATION_NAME}: {year_a} vs {year_b}**")

                col1, col2 = st.columns(2)
                with col1:
                    st.image(img_a, caption=f"{year_a}", use_column_width=True)
                with col2:
                    st.image(img_b, caption=f"{year_b}", use_column_width=True)

            except Exception as e:
                st.error(f"Error while getting images from GEE: {e}")
    else:
        st.info(
            "Choose Year A and Year B from the sidebar, "
            "then click **Generate Map**."
        )

with legend_col:
    render_legend()


# -------------------------
# 6. CHATBOT UI
# -------------------------
st.markdown("---")
st.subheader("💬 Chatbot: Ask About the Map and Changes")

# Show previous messages
for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input box for new question
user_input = st.chat_input(
    "Ask a question about land cover or changes between the years..."
)

if user_input:
    # Add user message
    st.session_state["chat_history"].append(
        {"role": "user", "content": user_input}
    )

    # Build messages for OpenAI
    messages_for_api = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant that explains Dynamic World land cover "
                "maps and changes over time in simple language. "
                "The location is fixed and the user compares different years."
            ),
        }
    ]
    messages_for_api.extend(st.session_state["chat_history"])

    # Call chatbot
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply = ask_chatbot(messages_for_api)
            st.markdown(reply)

    # Save assistant reply
    st.session_state["chat_history"].append(
        {"role": "assistant", "content": reply}
    )
