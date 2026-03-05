# main.py  (FastAPI backend)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ee

from config import LOCATION_LAT, LOCATION_LON, LOCATION_NAME
from gee_utils import get_dw_tile_urls
from chat_utils import ask_chatbot

app = FastAPI()

# allow your HTML to call this API from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # later you can restrict this to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- EARTH ENGINE INIT (same idea as before) ----------
def init_ee():
    # here you can copy exactly the EE init you used in Streamlit
    service_account_json = ...   # load from env / file
    credentials = ee.ServiceAccountCredentials(
        service_account_json["client_email"],
        key_data=service_account_json_json_string,
    )
    ee.Initialize(credentials)

init_ee()
LOCATION_POINT = ee.Geometry.Point([LOCATION_LON, LOCATION_LAT])


# ---------- MODELS ----------
class TilesRequest(BaseModel):
    mode: str          # "change_detection" | "single_year" | "timeseries"
    year_a: int
    year_b: int

class TilesResponse(BaseModel):
    dw_a_tiles: str | None = None
    dw_b_tiles: str | None = None
    change_tiles: str | None = None


class ChatRequest(BaseModel):
    message: str
    mode: str
    year_a: int
    year_b: int
    city: str | None = None     # for later if you geocode

class ChatResponse(BaseModel):
    reply: str
    summary: str | None = None


# ---------- ENDPOINT: TILES ----------
@app.post("/tiles", response_model=TilesResponse)
def get_tiles(req: TilesRequest):
    """
    Reuse your existing gee_utils.get_dw_tile_urls logic.
    Keep the logic exactly as in your old app.
    """
    urls = get_dw_tile_urls(LOCATION_POINT, req.year_a, req.year_b)
    # urls is something like {"a": "...", "b": "...", "change": "..."}
    return TilesResponse(
        dw_a_tiles=urls.get("a"),
        dw_b_tiles=urls.get("b"),
        change_tiles=urls.get("change"),
    )


# ---------- ENDPOINT: CHAT ----------
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Reuse your ask_chatbot logic.
    """
    system_msg = {
        "role": "system",
        "content": (
            "You are a helpful assistant for a Dynamic World map app. "
            f"Study area: {LOCATION_NAME}. "
            f"Mode: {req.mode}, years: {req.year_a}–{req.year_b}. "
            "Explain land-cover patterns and changes in very simple language."
        ),
    }
    messages = [system_msg, {"role": "user", "content": req.message}]
    reply_text = ask_chatbot(messages)

    # you can later add a smarter summary here; for now we just reuse reply
    return ChatResponse(reply=reply_text, summary=reply_text)
