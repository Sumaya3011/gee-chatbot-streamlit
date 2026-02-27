# chat_utils.py
"""
All chatbot logic using OpenAI.
No Streamlit layout code here.
"""

from openai import OpenAI
import streamlit as st

from config import OPENAI_MODEL


def _get_openai_client() -> OpenAI:
    """
    Build an OpenAI client using the API key stored in Streamlit secrets.
    """
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. "
            "Go to Streamlit Cloud -> App -> Settings -> Secrets "
            "and add OPENAI_API_KEY."
        )
    return OpenAI(api_key=api_key)


def ask_chatbot(history_messages):
    """
    Call the OpenAI chat model and return the assistant's text.

    history_messages: list of dicts:
        [
          {"role": "system"/"user"/"assistant", "content": "text"},
          ...
        ]
    """
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=history_messages,
    )
    return response.choices[0].message.content
