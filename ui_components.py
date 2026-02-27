# ui_components.py
"""
Streamlit UI helper components (legend etc.).
"""

import streamlit as st
from config import CLASS_LABELS, CLASS_PALETTE


def render_legend():
    """
    Show the Dynamic World legend (class color + label).
    """
    st.markdown("### Legend (Dynamic World Classes)")

    for label, color in zip(CLASS_LABELS, CLASS_PALETTE):
        st.markdown(
            f"<span style='display:inline-block;width:16px;height:16px;"
            f"background:#{color};border-radius:3px;margin-right:6px;'></span>{label}",
            unsafe_allow_html=True,
        )
