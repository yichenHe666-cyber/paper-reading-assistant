"""Loading and skeleton components."""

import streamlit as st
from .icon import icon


def loading_state(message: str = "加载中...") -> None:
    """Render a centered loading spinner with message."""
    spinner = icon("spinner", size="2xl", color="var(--color-primary)")
    html = f"""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:3rem;text-align:center;">
        <div style="font-size:2rem;margin-bottom:1rem;animation:spin 1s linear infinite;">{spinner}</div>
        <div style="font-size:1rem;color:var(--color-text-secondary);font-weight:500;">{message}</div>
    </div>
    <style>
        @keyframes spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
    </style>
    """
    st.markdown(html, unsafe_allow_html=True)


def skeleton_line(width: str = "100%") -> None:
    """Render a single skeleton loading line."""
    st.markdown(f'<div class="ui-skeleton ui-skeleton-line" style="width:{width};"></div>', unsafe_allow_html=True)


def skeleton_card() -> None:
    """Render a skeleton card placeholder."""
    st.markdown('<div class="ui-skeleton ui-skeleton-card"></div>', unsafe_allow_html=True)


def skeleton_text(lines: int = 3) -> None:
    """Render multiple skeleton lines of varying widths."""
    widths = ["100%", "92%", "85%", "78%", "65%", "90%"]
    for i in range(lines):
        skeleton_line(width=widths[i % len(widths)])
