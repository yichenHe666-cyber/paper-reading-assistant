"""Badge / pill component for labels and statuses."""

from typing import Optional

import streamlit as st
from .icon import icon

VALID_VARIANTS = {"default", "primary", "success", "warning", "danger", "info"}


def badge(
    text: str,
    variant: str = "default",
    icon_name: Optional[str] = None,
) -> str:
    """Build a small badge pill HTML string.

    Args:
        text: Badge label text.
        variant: Color variant name.
        icon_name: Optional icon key.

    Returns:
        HTML string for the badge span. Callers are responsible for
        rendering it (e.g. via ``st.markdown(..., unsafe_allow_html=True)``
        or by embedding it inside another HTML fragment).
    """
    if variant not in VALID_VARIANTS:
        variant = "default"
    icon_html = icon(icon_name, size="xs") if icon_name else ""
    html = f'<span class="ui-badge ui-badge-{variant}">{icon_html}{text}</span>'
    return html


def badge_group(labels: list[str], variant: str = "default") -> str:
    """Build a horizontal group of badges with wrapping as an HTML string."""
    badges = " ".join(
        f'<span class="ui-badge ui-badge-{variant}">{lab}</span>' for lab in labels
    )
    return f'<div style="display:flex;flex-wrap:wrap;gap:6px;">{badges}</div>'
