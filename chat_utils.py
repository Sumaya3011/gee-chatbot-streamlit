# chat_utils.py
"""
Chatbot logic using OpenAI.
No Streamlit layout here, only API calls.
"""

from openai import OpenAI
import streamlit as st

from config import OPENAI_MODEL


def _get_openai_client() -> OpenAI:
    """
    Build an OpenAI client using API key from Streamlit secrets.
    """
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. "
            "Add it in Streamlit Cloud -> Your app -> Settings -> Secrets."
        )
    return OpenAI(api_key=api_key)


def ask_chatbot(history_messages):
    """
    Call the OpenAI chat model and return text reply.

    history_messages: list of dict:
      [{"role": "system"/"user"/"assistant", "content": "..."}, ...]
    """
    client = _get_openai_client()

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=history_messages,
    )
    return response.choices[0].message.content
