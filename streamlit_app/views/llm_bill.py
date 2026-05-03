import streamlit as st
from streamlit_app.utils.api_client import get
from streamlit_app.components.icon import icon
from streamlit_app.components.metric_card import metric_row
from streamlit_app.components.empty_state import empty_state
import pandas as pd

st.markdown(f"""
<div class="main-header">
    <h1>{icon('receipt_long', size='lg')} LLM 账单</h1>
    <p>实时监控 LLM API 调用花费，按日、按类型追踪成本</p>
</div>
""", unsafe_allow_html=True)

try:
    summary = get("/api/system/llm-cost")
except Exception:
    summary = {}
    st.warning("无法连接后端获取花费数据")

metric_row([
    {"value": f"${summary.get('today_cost_usd', 0):.4f}", "label": "今日花费", "icon_name": "coins"},
    {"value": f"${summary.get('week_cost_usd', 0):.4f}", "label": "本周花费", "icon_name": "calendar_week"},
    {"value": f"${summary.get('month_cost_usd', 0):.4f}", "label": "本月花费", "icon_name": "calendar_days"},
    {"value": f"${summary.get('total_cost_usd', 0):.4f}", "label": "累计花费", "icon_name": "receipt_long"},
])

st.divider()

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📊 每日花费趋势 (近 14 天)")
    try:
        daily = get("/api/system/llm-cost/daily")
    except Exception:
        daily = []
    if daily:
        df_daily = pd.DataFrame(daily)
        df_daily["日期"] = df_daily.get("date", df_daily.iloc[:, 0] if len(df_daily.columns) > 0 else "")
        df_daily["花费($)"] = df_daily.get("cost_usd", df_daily.get("cost", df_daily.iloc[:, 1] if len(df_daily.columns) > 1 else 0))
        st.bar_chart(df_daily.set_index("日期")[["花费($)"]], use_container_width=True)
    else:
        empty_state(title="暂无数据", description="暂无每日花费数据", icon_name="chart_bar")

with col_right:
    st.subheader("🥧 按调用类型花费分布")
    try:
        by_type = get("/api/system/llm-cost/by-type")
    except Exception:
        by_type = []
    if by_type:
        df_type = pd.DataFrame(by_type)
        type_label_col = df_type.get("call_type", df_type.get("type", df_type.iloc[:, 0] if len(df_type.columns) > 0 else ""))
        cost_col = df_type.get("cost_usd", df_type.get("cost", df_type.iloc[:, 1] if len(df_type.columns) > 1 else 0))
        chart_data = pd.DataFrame({"类型": type_label_col, "花费($)": cost_col})
        st.bar_chart(chart_data.set_index("类型"), use_container_width=True)
    else:
        empty_state(title="暂无数据", description="暂无调用类型分布数据", icon_name="chart_pie")

st.divider()

st.subheader("📋 花费明细")
try:
    detail = get("/api/system/llm-cost/detail")
except Exception:
    detail = []
if detail:
    rows = []
    for d in detail:
        rows.append({
            "时间": str(d.get("created_at", ""))[:19],
            "类型": d.get("call_type", ""),
            "模型": d.get("model", ""),
            "Tokens": d.get("total_tokens", 0),
            "耗时(ms)": d.get("duration_ms", 0),
            "费用": f"${d.get('cost_usd', 0):.4f}",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    empty_state(title="暂无记录", description="暂无花费明细记录", icon_name="list")
