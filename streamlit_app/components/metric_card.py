"""Metric card component for dashboard KPIs."""

from typing import Optional
import streamlit as st
from .icon import icon


def metric_card(
    value: str,
    label: str,
    change: Optional[str] = None,
    change_positive: bool = True,
    icon_name: Optional[str] = None,
) -> None:
    """Render a KPI metric card.

    Args:
        value: The big number/string to display.
        label: Description below the value.
        change: Optional change indicator text, e.g. '+12%'.
        change_positive: Whether the change is positive (green) or negative (red).
        icon_name: Optional icon to show beside the label.
    """
    icon_html = icon(icon_name, size="lg", color="var(--color-primary)") if icon_name else ""
    change_class = "ui-metric-change-up" if change_positive else "ui-metric-change-down"
    change_html = f'<div class="ui-metric-change {change_class}">{change}</div>' if change else ""

    html = f"""
    <div class="ui-metric-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            {icon_html}
            <span style="font-size:0.875rem;color:var(--color-text-secondary);font-weight:500;">{label}</span>
        </div>
        <div class="ui-metric-value">{value}</div>
        {change_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def metric_row(metrics: list[dict]) -> None:
    """Render a row of metric cards using Streamlit columns.

    Args:
        metrics: List of dicts with keys: value, label, change, change_positive, icon_name.
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            metric_card(
                value=m.get("value", "0"),
                label=m.get("label", ""),
                change=m.get("change"),
                change_positive=m.get("change_positive", True),
                icon_name=m.get("icon_name"),
            )
