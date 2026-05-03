"""Empty state component for when no data is available."""

from typing import Optional
import streamlit as st
from .icon import icon


def empty_state(
    title: str = "暂无数据",
    description: str = "当前没有可显示的内容",
    icon_name: str = "inbox",
    action_label: Optional[str] = None,
    action_key: Optional[str] = None,
) -> bool:
    """Render an empty state illustration with optional action button.

    Args:
        title: Main message.
        description: Subtitle description.
        icon_name: Icon key from ICON_MAP.
        action_label: If provided, renders a button below the text.
        action_key: Streamlit button key.

    Returns:
        True if the action button was clicked, else False.
    """
    icon_html = icon(icon_name, size="2xl", color="var(--color-text-muted)")
    html = f"""
    <div class="ui-empty-state">
        <div class="ui-empty-state-icon">{icon_html}</div>
        <div class="ui-empty-state-title">{title}</div>
        <div class="ui-empty-state-desc">{description}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

    if action_label and action_key:
        cols = st.columns([1, 2, 1])
        with cols[1]:
            return st.button(action_label, key=action_key, use_container_width=True)
    return False
