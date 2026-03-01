# ui_components.py
"""
Small helper components for the Streamlit UI:
- Legend for Dynamic World classes
"""

import streamlit as st
from config import CLASS_LABELS, CLASS_PALETTE


def render_dw_legend():
    """
    Show a compact Dynamic World legend, similar to your old right-side panel.
    """
    st.markdown("### Dynamic World classes")

    for label, color in zip(CLASS_LABELS, CLASS_PALETTE):
        st.markdown(
            f"<div style='display:flex;align-items:center;margin-bottom:4px;'>"
            f"<span style='display:inline-block;width:16px;height:16px;"
            f"border-radius:4px;border:1px solid #d1d5db;"
            f"background:#{color};margin-right:8px;'></span>"
            f"<span style='font-size:12px;color:#374151;'>{label}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
