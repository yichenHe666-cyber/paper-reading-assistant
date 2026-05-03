"""Card component for consistent content containers."""

from typing import Optional
import streamlit as st


def card(
    content: str,
    variant: str = "default",
    padding: str = "1.5rem",
    margin: str = "0 0 1rem 0",
    hover: bool = True,
    custom_class: str = "",
) -> None:
    """Render a styled card container.

    Args:
        content: HTML content to place inside the card.
        variant: One of default|elevated|outlined|gradient.
        padding: CSS padding value.
        margin: CSS margin value.
        hover: Whether to enable hover lift effect.
        custom_class: Additional CSS classes.
    """
    base_class = "ui-card"
    if variant != "default":
        base_class += f" ui-card-{variant}"
    if hover and variant != "gradient":
        base_class += " ui-card-hover"
    if custom_class:
        base_class += f" {custom_class}"

    style = f"padding: {padding}; margin: {margin};"
    html = f'<div class="{base_class}" style="{style}">{content}</div>'
    st.markdown(html, unsafe_allow_html=True)


def card_header(title: str, subtitle: Optional[str] = None, icon: Optional[str] = None) -> str:
    """Generate a card header HTML string.

    Args:
        title: Card title.
        subtitle: Optional subtitle.
        icon: Optional Font Awesome icon HTML.

    Returns:
        HTML string for the header.
    """
    icon_html = f'<span style="margin-right:8px;">{icon}</span>' if icon else ""
    subtitle_html = f'<div style="font-size:0.875rem;color:var(--color-text-muted);margin-top:4px;">{subtitle}</div>' if subtitle else ""
    return f"""
    <div style="margin-bottom:1rem;">
        <div style="font-size:1.125rem;font-weight:600;color:var(--color-text-primary);display:flex;align-items:center;">
            {icon_html}{title}
        </div>
        {subtitle_html}
    </div>
    """
