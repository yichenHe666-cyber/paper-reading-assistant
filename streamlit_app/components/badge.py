"""Badge / pill component for labels and statuses."""

from typing import Optional

import streamlit as st
from .icon import icon

VALID_VARIANTS = {"default", "primary", "success", "warning", "danger", "info"}


def badge(
    text: str,
    variant: str = "default",
    icon_name: Optional[str] = None,
) -> None:
    """Render a small badge pill.

    Args:
        text: Badge label text.
        variant: Color variant name.
        icon_name: Optional icon key.
    """
    if variant not in VALID_VARIANTS:
        variant = "default"
    icon_html = icon(icon_name, size="xs") if icon_name else ""
    html = f'<span class="ui-badge ui-badge-{variant}">{icon_html}{text}</span>'
    st.markdown(html, unsafe_allow_html=True)


def badge_group(labels: list[str], variant: str = "default") -> None:
    """Render a horizontal group of badges with wrapping."""
    badges = " ".join(
        f'<span class="ui-badge ui-badge-{variant}">{lab}</span>' for lab in labels
    )
    st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:6px;">{badges}</div>', unsafe_allow_html=True)
