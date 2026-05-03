import streamlit as st
from streamlit_app.utils.api_client import get
from streamlit_app.components.icon import icon
from streamlit_app.components.empty_state import empty_state
import pandas as pd

st.markdown(f"""
<div class="main-header">
    <h1>{icon('diagram_project', size='lg')} 概念图谱</h1>
    <p>Obsidian 概念卡片之间的关联网络可视化</p>
</div>
""", unsafe_allow_html=True)

concept_dir = None
try:
    status = get("/api/obsidian/status")
    concept_dir = status.get("concept_files", 0)
except Exception:
    pass

if not concept_dir or concept_dir == 0:
    empty_state(
        title="暂无概念卡片",
        description="还没有概念卡片。请先在「阅读工作台」生成概念卡片并写入 Obsidian。",
        icon_name="diagram_project",
        action_label="前往阅读工作台",
        action_key="go_workbench",
    )
    if st.button("前往阅读工作台", key="go_workbench_btn", use_container_width=True):
        st.switch_page("views/reading_workbench.py")
    st.stop()

import re
from pathlib import Path
import json

VAULT_CONCEPTS = Path(r"C:\Users\Public\Documents\02-概念卡片")

nodes = []
edges = []
concept_data = {}

for md_file in VAULT_CONCEPTS.glob("*.md"):
    name = md_file.stem
    content = md_file.read_text(encoding="utf-8")
    category = "未分类"
    cm = re.search(r'category:\s*"([^"]*)"', content) or re.search(r"category:\s*(.+)", content)
    if cm:
        category = cm.group(1).strip().strip('"')

    links = re.findall(r'\[\[([^\]]+)\]\]', content)
    concept_data[name] = {"category": category, "links": links, "path": str(md_file)}
    nodes.append({"name": name, "category": category})

for name, data in concept_data.items():
    for link in data.get("links", []):
        if link in concept_data:
            edges.append({"source": name, "target": link})

st.subheader(f"🕸️ 概念网络 — {len(nodes)} 个节点, {len(edges)} 条边")

if not nodes:
    empty_state(title="未检测到概念卡片", description="还未检测到概念卡片", icon_name="diagram_project")
    st.stop()

categories = list(set(n.get("category", "未分类") for n in nodes))
selected_cat = st.selectbox("按类别筛选", ["全部"] + categories)

filtered_nodes = nodes if selected_cat == "全部" else [n for n in nodes if n.get("category") == selected_cat]
filtered_names = {n["name"] for n in filtered_nodes}
filtered_edges = [e for e in edges if e["source"] in filtered_names and e["target"] in filtered_names]

col1, col2 = st.columns([2, 1])

with col1:
    try:
        import plotly.graph_objects as go
        node_names = [n["name"] for n in filtered_nodes]
        name_to_idx = {n: i for i, n in enumerate(node_names)}

        source_idx = [name_to_idx[e["source"]] for e in filtered_edges if e["source"] in name_to_idx and e["target"] in name_to_idx]
        target_idx = [name_to_idx[e["target"]] for e in filtered_edges if e["source"] in name_to_idx and e["target"] in name_to_idx]

        cat_colors = {cat: f"hsl({hash(cat) % 360}, 60%, 60%)" for cat in set(n.get("category", "") for n in filtered_nodes)}
        node_colors = [cat_colors.get(n.get("category", ""), "#667eea") for n in filtered_nodes]
        node_sizes = [max(10, concept_data.get(n["name"], {}).get("links", []).__len__() * 5 + 10) for n in filtered_nodes]

        fig = go.Figure(data=[go.Scatter(
            x=[hash(n["name"]) % 50 for n in filtered_nodes],
            y=[(hash(n["name"]) * 7) % 50 for n in filtered_nodes],
            mode="markers+text",
            text=node_names,
            textposition="top center",
            marker=dict(size=node_sizes, color=node_colors, line=dict(width=1, color="#fff")),
            hoverinfo="text",
            hovertext=[f"{n['name']}<br>类别: {n.get('category','')}" for n in filtered_nodes],
        )])

        for s, t in zip(source_idx, target_idx):
            fig.add_trace(go.Scatter(
                x=[hash(node_names[s]) % 50, hash(node_names[t]) % 50],
                y=[(hash(node_names[s]) * 7) % 50, (hash(node_names[t]) * 7) % 50],
                mode="lines",
                line=dict(color="#ddd", width=0.5),
                hoverinfo="none",
                showlegend=False,
            ))

        fig.update_layout(
            title="概念关联网络",
            showlegend=False,
            height=550,
            margin=dict(l=20, r=20, t=40, b=20),
            plot_bgcolor="#0B1120",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.warning("需要 plotly 来渲染概念图谱。请在 requirements.txt 中添加 plotly。")

with col2:
    st.subheader("🎨 图例")
    for cat in sorted(set(n.get("category", "未分类") for n in filtered_nodes)):
        color = cat_colors.get(cat, "#667eea")
        count = sum(1 for n in filtered_nodes if n.get("category") == cat)
        st.markdown(f'<span style="color:{color}">●</span> {cat} ({count})', unsafe_allow_html=True)

    st.divider()
    st.subheader("🔗 最多连接")
    degree = {n["name"]: len(concept_data.get(n["name"], {}).get("links", [])) for n in filtered_nodes}
    top = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:10]
    for name, count in top:
        st.markdown(f"**{name}** — {count} 个链接")

st.caption("💡 数据来自 Obsidian `02-概念卡片/` 目录中的 `[[双链]]` 语法")
