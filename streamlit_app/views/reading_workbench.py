# -*- coding: utf-8 -*-
import streamlit as st
from streamlit_app.utils.api_client import get, post, patch, upload_pdf
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
from streamlit_app.components.empty_state import empty_state
import json

paper_id = st.session_state.selected_paper_id

if not paper_id:
    st.markdown(f"""
    <div class="main-header">
        <h1>{icon('book_open', size='lg')} 阅读工作台</h1>
        <p>请先在「主题浏览」中选择一篇论文开始精读</p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("📂 前往主题浏览", use_container_width=True, type="primary"):
        st.switch_page("views/topic_browser.py")
    st.stop()

paper = None
try:
    paper = get(f"/api/papers/{paper_id}")
except Exception:
    pass

if not paper or "error" in paper:
    st.error("无法获取论文信息，请返回主题浏览重新选择")
    st.stop()

st.markdown(f"""
<div class="main-header">
    <h1>{icon('book_open', size='lg')} 阅读工作台</h1>
    <p>学术论文精读 — Keshav 三遍法 + Booth 批判审查框架</p>
</div>
""", unsafe_allow_html=True)

authors_str = paper.get("authors", "[]")
try:
    authors_list = json.loads(authors_str) if isinstance(authors_str, str) else authors_str
    authors_display = ", ".join(authors_list)
except Exception:
    authors_display = str(authors_str)

st.markdown("---")
st.subheader(paper.get("title", "Untitled"))

meta_parts = []
if authors_display:
    meta_parts.append(f"**作者**: {authors_display}")
if paper.get("year"):
    meta_parts.append(f"**年份**: {paper.get('year')}")
meta_parts.append(f"**主题**: {paper.get('topic_name_cn', paper.get('topic_id', ''))}")
if paper.get("subtopic"):
    meta_parts.append(f"**子主题**: {paper.get('subtopic')}")
if paper.get("venue"):
    meta_parts.append(f"**会议/期刊**: {paper.get('venue')}")
if paper.get("doi"):
    meta_parts.append(f"**DOI**: {paper.get('doi')}")

st.caption(f"{icon('info', size='xs')} ｜ ".join(meta_parts))

col_pdf, col_notes = st.columns(2)
with col_pdf:
    if paper.get("pdf_url"):
        pdf_url = paper["pdf_url"]
        is_local_upload = pdf_url.startswith("local://uploaded/")
        if st.button("👁️ 在线浏览 PDF", key="view_pdf_inline", use_container_width=True, type="primary"):
            st.session_state.show_pdf_viewer = not st.session_state.get("show_pdf_viewer", False)
        if is_local_upload:
            st.button("📤 本地已上传", disabled=True, use_container_width=True)
        elif pdf_url.startswith("https://github.com/papers-we-love/papers-we-love/blob/master/"):
            st.link_button(f"{icon('link', size='sm')} GitHub 源链接", pdf_url, use_container_width=True)
        else:
            st.link_button(f"{icon('link', size='sm')} 外部 PDF 链接", pdf_url, use_container_width=True)
        if st.button("⬇️ 下载并提取 PDF 文本", key="dl_pdf", use_container_width=True):
            with st.spinner("正在下载并提取 PDF 文本..."):
                dl_result = post("/api/reading/download-pdf", {"paper_id": paper_id})
            if dl_result.get("error"):
                st.error(f"下载失败: {dl_result['error']}")
            elif dl_result.get("status") == "text_extracted":
                st.success("PDF 文本已提取并保存为摘要")
                st.rerun()
            else:
                st.info(f"PDF 处理结果: {dl_result.get('status', 'unknown')}")
    else:
        if st.button("🔍 自动查找 PDF 来源", key="resolve_pdf", use_container_width=True, type="primary"):
            with st.spinner("正在通过 Unpaywall / Semantic Scholar / arXiv / CORE / OpenAlex 查找可用 PDF..."):
                resolve_result = post("/api/reading/resolve-pdf", {"paper_id": paper_id})
            if resolve_result.get("pdf_url"):
                source_name = {
                    "unpaywall": "Unpaywall 开放获取",
                    "semantic_scholar": "Semantic Scholar",
                    "arxiv_via_s2": "arXiv (via S2)",
                    "arxiv_search": "arXiv",
                    "core": "CORE 开放获取",
                    "openalex_doi": "OpenAlex",
                    "openalex_search": "OpenAlex",
                }.get(resolve_result.get("source", ""), resolve_result.get("source", ""))
                st.success(f"找到 PDF 来源: {source_name}")
                if resolve_result.get("doi"):
                    st.info(f"DOI: {resolve_result['doi']}")
                st.rerun()
            else:
                st.warning("未能找到可用的 PDF 来源，已尝试所有合法开放获取渠道")
        st.button("📄 暂无 PDF", disabled=True, use_container_width=True)

    st.divider()
    st.markdown(f"**{icon('upload', size='sm')} 手动上传 PDF**")
    uploaded_file = st.file_uploader(
        "选择本地 PDF 文件",
        type=["pdf"],
        key=f"pdf_uploader_{paper_id}",
        label_visibility="collapsed",
    )
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        file_name = uploaded_file.name
        col_up1, col_up2 = st.columns([3, 2])
        with col_up1:
            st.caption(f"已选择: {file_name} ({round(len(file_bytes)/1024, 1)} KB)")
        with col_up2:
            if st.button("📤 确认上传", key=f"confirm_upload_{paper_id}", use_container_width=True, type="primary"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                status_text.info("正在上传 PDF...")
                progress_bar.progress(30)
                try:
                    upload_result = upload_pdf("/api/reading/upload-pdf", paper_id, file_bytes, file_name)
                    progress_bar.progress(70)
                    if upload_result.get("error"):
                        status_text.error(f"上传失败: {upload_result['error']}")
                        progress_bar.progress(100)
                    else:
                        status_text.success("PDF 上传成功！")
                        progress_bar.progress(100)
                        st.info(f"文件大小: {upload_result.get('pdf_size_kb', '?')} KB")
                        if upload_result.get("text_length"):
                            st.success(f"已提取文本: {upload_result['text_length']} 字符")
                        st.rerun()
                except Exception as e:
                    status_text.error(f"上传异常: {str(e)}")
                    progress_bar.progress(100)
with col_notes:
    notes_url = paper.get("community_notes_url")
    if not notes_url and paper.get("topic_id"):
        notes_url = f"https://github.com/papers-we-love/papers-we-love/tree/master/{paper['topic_id']}#readme"
    if notes_url:
        st.link_button(f"{icon('comments', size='sm')} 社区笔记", notes_url, use_container_width=True)
    else:
        st.button("💬 暂无社区笔记", disabled=True, use_container_width=True)

if st.session_state.get("show_pdf_viewer", False) and paper.get("pdf_url"):
    st.markdown("---")
    pdf_url = paper["pdf_url"]
    is_local = pdf_url.startswith("local://uploaded/")
    if is_local:
        st.info(f"{icon('upload', size='sm')} 本地上传的 PDF 请使用下方「下载并提取 PDF 文本」按钮进行 AI 阅读分析")
        st.markdown(f"""
        <div style="border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 20px; text-align: center; background: var(--color-bg);">
            <p style="font-size: 1.2em; margin-bottom: 10px;">{icon('file_pdf', size='lg')}</p>
            <p style="color: var(--color-text-secondary);">文件已成功上传并保存，文本已提取可供 AI 分析</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        if "github.com" in pdf_url and "/blob/" in pdf_url:
            pdf_url = pdf_url.replace("/blob/", "/raw/")
        st.markdown(f"""
        <iframe 
            src="{pdf_url}" 
            width="100%" 
            height="800px" 
            style="border: 1px solid var(--color-border); border-radius: var(--radius-lg);"
            type="application/pdf">
        </iframe>
        <p style="text-align:center; color:var(--color-text-muted); font-size:0.85em;">
        {icon('lightbulb', size='xs')} 如果 PDF 未显示，请点击上方「外部 PDF 链接」在新标签页中查看
        </p>
        """, unsafe_allow_html=True)
    if st.button("❌ 关闭 PDF 浏览器", key="close_pdf"):
        st.session_state.show_pdf_viewer = False
        st.rerun()

st.markdown("---")

gen = st.session_state.generated.get(paper_id, {})
has_gen = bool(gen)

if "reading_round" not in st.session_state:
    st.session_state.reading_round = "R1"

st.radio(
    f"{icon('ruler_combined', size='sm')} 阅读轮次（Keshav 三遍法）",
    ["R1 浏览", "R2 精读", "R3 深度"],
    horizontal=True,
    key="reading_round_selector",
    index=["R1","R2","R3"].index(st.session_state.reading_round) if st.session_state.reading_round in ["R1","R2","R3"] else 0,
    help="R1=第一遍5C摘要·阅读策略 | R2=形式化拆解·批判审查 | R3=完整学术笔记"
)

if st.session_state.reading_round_selector != st.session_state.reading_round:
    st.session_state.reading_round = st.session_state.reading_round_selector.replace("R1 浏览","R1").replace("R2 精读","R2").replace("R3 深度","R3")

reading_round = st.session_state.reading_round
gen = st.session_state.generated.get(paper_id, {})

first_pass = gen.get("first_pass")
formal_decon = gen.get("formal_decon")
critical_review = gen.get("critical_review")
note_draft = gen.get("note_draft")
vocabulary = gen.get("vocabulary")
vocab_md = gen.get("vocabulary_md")

has_r1 = bool(first_pass)
has_r2 = bool(formal_decon) or bool(critical_review)
has_r3 = bool(note_draft) and has_r2

# ── Determine tabs based on round ──
tabs_available = [f"{icon('sparkles', size='sm')} 一键生成"]
if reading_round in ("R1", "R2", "R3"):
    tabs_available.append(f"{icon('search', size='sm')} 5C摘要")
if reading_round in ("R2", "R3"):
    tabs_available.extend([f"{icon('calculator', size='sm')} 形式化拆解", f"{icon('scale_balanced', size='sm')} 批判性审查"])
if reading_round in ("R3",):
    tabs_available.append(f"{icon('pen_to_square', size='sm')} 完整笔记")
tabs_available.append(f"{icon('book', size='sm')} 专业词汇")
tabs_available.append(f"{icon('microscope', size='sm')} 相关研究")

tab_objects = st.tabs(tabs_available)

# ══════════════════════════════════════
# TAB: 一键生成
# ══════════════════════════════════════
with tab_objects[0]:
    st.subheader("✨ 学术论文精读生成")
    round_desc = {
        "R1": "第一遍浏览：生成 5C 摘要、阅读策略、假设背景、警告标志 + 专业词汇表",
        "R2": "第二遍精读：在 R1 基础上追加形式化拆解（符号表·定理·推导检查）+ 批判性审查（假设审计·方法局限·可复现性）",
        "R3": "第三遍深度：在 R1+R2 基础上合成完整 6 章学术笔记（元数据定位·论证图谱·形式化拆解·批判审查·概念卡片·阅读日志）",
    }
    st.caption(round_desc.get(reading_round, ""))

    need_generate = True
    if reading_round == "R1" and has_r1:
        need_generate = False
    elif reading_round == "R2" and has_r2:
        need_generate = False
    elif reading_round == "R3" and has_r3:
        need_generate = False

    if need_generate:
        gen_label = {
            "R1": f"{icon('sparkles', size='sm')} R1 第一遍浏览",
            "R2": f"{icon('sparkles', size='sm')} R2 精读分析",
            "R3": f"{icon('sparkles', size='sm')} R3 深度合成",
        }
        if st.button(gen_label.get(reading_round, f"{icon('sparkles', size='sm')} 一键生成"), use_container_width=True, type="primary"):
            with st.spinner(f"正在执行 {reading_round} 分析..."):
                result = post("/api/reading/one-click", {"paper_id": paper_id, "reading_round": reading_round})

            if result.get("error"):
                st.error(f"{result['error']}")
            else:
                merged = {**st.session_state.generated.get(paper_id, {}), **result}
                st.session_state.generated[paper_id] = merged
                patch(f"/api/papers/{paper_id}", {"read_status": "精读中"})
                if result.get("errors"):
                    st.warning("部分内容生成失败：")
                    for err in result["errors"]:
                        st.error(f"  • {err}")
                else:
                    cache_info = result.get("from_cache", [])
                    if cache_info and isinstance(cache_info, list) and cache_info:
                        st.success(f"{reading_round} 生成完毕！（{', '.join(cache_info[:3])} 来自缓存）")
                    else:
                        st.success(f"{reading_round} 生成完毕！切换上方标签页查看详情。")
                st.rerun()
    else:
        st.success(f"{reading_round} 内容已生成")
        if st.button("🔄 重新生成当前轮次", use_container_width=True):
            keys_to_remove = {"R1": ["R1_first_pass"], "R2": ["R1_first_pass", "R2_formal_decon", "R2_critical_review"],
                              "R3": ["R1_first_pass", "R2_formal_decon", "R2_critical_review", "R3_smart_note"]}
            gen_current = st.session_state.generated.get(paper_id, {})
            for key in keys_to_remove.get(reading_round, []):
                gen_current.pop(key, None)
            gen_current.pop("first_pass", None)
            gen_current.pop("formal_decon", None)
            gen_current.pop("critical_review", None)
            gen_current.pop("note_draft", None)
            st.session_state.generated[paper_id] = gen_current
            st.rerun()

    if gen and not need_generate:
        st.divider()
        st.subheader("☑️ 生成状态")
        cols = []
        if reading_round in ("R1", "R2", "R3"):
            cols.extend(["5C摘要", "阅读策略", "词汇表"])
        if reading_round in ("R2", "R3"):
            cols.extend(["形式化拆解", "批判审查"])
        if reading_round == "R3":
            cols.append("完整笔记")
        metrics_cols = st.columns(len(cols))
        for i, col_name in enumerate(cols):
            key_map = {"5C摘要": "first_pass", "阅读策略": "first_pass", "词汇表": "vocabulary",
                       "形式化拆解": "formal_decon", "批判审查": "critical_review", "完整笔记": "note_draft"}
            has_it = bool(gen.get(key_map.get(col_name, "")))
            with metrics_cols[i]:
                st.metric(col_name, icon("check", size="sm") if has_it else icon("xmark", size="sm"))

# ══════════════════════════════════════
# TAB: 5C摘要
# ══════════════════════════════════════
if len(tab_objects) > 1:
    with tab_objects[1]:
        if not first_pass:
            empty_state(
                title="尚未生成内容",
                description="请先在「一键生成」中选择 R1 并生成内容",
                icon_name="search",
            )
        else:
            st.subheader("🔍 5C 摘要分析")
            five_c = first_pass.get("5c_summary", {})
            if five_c:
                st.markdown(f"**Category（类别）**: {five_c.get('category', 'N/A')}")
                st.markdown(f"**Context（背景）**: {five_c.get('context', 'N/A')}")
                st.markdown(f"**Correctness（核心主张）**: {five_c.get('correctness', 'N/A')}")
                st.markdown(f"**Contribution（贡献）**: {five_c.get('contribution', 'N/A')}")
                st.markdown(f"**Clarity（写作质量）**: {five_c.get('clarity', 'N/A')}")

            st.markdown(f"### {icon('compass', size='sm')} 阅读策略")
            strategy = first_pass.get("reading_strategy", {})
            if strategy:
                st.markdown(f"- **阅读顺序**: {strategy.get('order', '')}")
                st.markdown(f"- **重点聚焦**: {strategy.get('focus', '')}")
                st.markdown(f"- **预计时间**: {strategy.get('estimated_time', '')}")
                st.markdown(f"- **建议**: **{strategy.get('skip_or_read', '')}**")

            st.markdown(f"### {icon('triangle_exclamation', size='sm')} 警告标志")
            warnings = first_pass.get("warning_flags", [])
            if warnings:
                for w in warnings:
                    st.warning(f"**{w.get('flag', '')}** — {w.get('impact', '')} （{w.get('evidence', '')}）")

            bg = first_pass.get("assumptions_background", {})
            if bg:
                with st.expander(f"{icon('book', size='sm')} 前置知识与理论背景"):
                    if bg.get("prerequisites"):
                        st.markdown("**前置知识**：")
                        for p in bg["prerequisites"]:
                            st.markdown(f"- {p}")
                    st.markdown(f"**理论背景**: {bg.get('theory_background', '')}")

# ── TAB: 形式化拆解 ──
form_tab_idx = 2 if reading_round in ("R2", "R3") else None
if form_tab_idx and form_tab_idx < len(tab_objects):
    with tab_objects[form_tab_idx]:
        if not formal_decon:
            empty_state(
                title="尚未生成内容",
                description="请先在「一键生成」中选择 R2 并生成内容",
                icon_name="calculator",
            )
        else:
            st.subheader("🧮 形式化内容拆解")
            syms = formal_decon.get("symbol_table", [])
            if syms:
                st.markdown("### 符号表")
                st.dataframe(
                    [{"符号": s.get("symbol", ""), "含义": s.get("meaning", ""),
                      "位置": s.get("location", ""), "类型": s.get("type", "")} for s in syms],
                    use_container_width=True, hide_index=True
                )

            theorems = formal_decon.get("theorems", [])
            if theorems:
                st.markdown("### 定理与证明策略")
                for t in theorems:
                    card(
                        content=f"""
                        <b>{icon('ruler_combined', size='sm')} {t.get('statement', '')[:100]}</b><br/>
                        <span style="color:var(--color-text-secondary);">策略: {t.get('proof_strategy', '')} | 位置: {t.get('location', '')}</span>
                        <p>{t.get('proof_summary', '')}</p>
                        """,
                        variant="default",
                        padding="1rem",
                    )

            derivs = formal_decon.get("derivation_checks", [])
            if derivs:
                st.markdown(f"### {icon('search', size='sm')} 需手动推导的跳步")
                for i, d in enumerate(derivs):
                    with st.expander(f"跳步 {i+1}: {d.get('gap_description', '')[:60]}..."):
                        st.markdown(f"**位置**: {d.get('location', '')}")
                        st.markdown(f"**描述**: {d.get('gap_description', '')}")
                        st.text_area("我的推导", key=f"my_derivation_{i}", placeholder="在此填写你的推导过程...", height=100)

            bounds = formal_decon.get("boundary_conditions", [])
            if bounds:
                st.markdown(f"### {icon('bolt', size='sm')} 边界条件")
                for b in bounds:
                    st.info(f"**假设**: {b.get('assumption', '')} ({b.get('type', '')}) → 违反后果: {b.get('violation_consequence', '')}")

            gaps = formal_decon.get("formal_gaps", [])
            if gaps:
                st.markdown(f"### {icon('circle_exclamation', size='sm')} 形式化缺失警告")
                for g in gaps:
                    st.error(f"**{g.get('concept', '')}** @ {g.get('mention_location', '')}: {g.get('missing', '')}")

# ── TAB: 批判性审查 ──
crit_tab_idx = form_tab_idx + 1 if form_tab_idx else None
if crit_tab_idx and crit_tab_idx < len(tab_objects):
    with tab_objects[crit_tab_idx]:
        if not critical_review:
            empty_state(
                title="尚未生成内容",
                description="请先在「一键生成」中选择 R2 并生成内容",
                icon_name="scale_balanced",
            )
        else:
            st.subheader("⚖️ 批判性审查 (Booth 框架)")

            findings = critical_review.get("findings", [])
            if findings:
                severity_icon = {"fatal": icon("circle_xmark", size="sm"), "serious": icon("triangle_exclamation", size="sm"),
                                 "minor": icon("circle_exclamation", size="sm"), "negligible": icon("circle_info", size="sm")}
                for f in sorted(findings, key=lambda x: {"fatal": 0, "serious": 1, "minor": 2, "negligible": 3}.get(x.get("severity", ""), 4)):
                    sev = f.get("severity", "")
                    icon_html = severity_icon.get(sev, icon("circle_info", size="sm"))
                    if sev in ("fatal", "serious"):
                        st.error(f"{icon_html} **[{sev.upper()}]** {f.get('issue', '')}")
                    elif sev == "minor":
                        st.warning(f"{icon_html} **[{sev.upper()}]** {f.get('issue', '')}")
                    else:
                        st.info(f"{icon_html} [{sev}] {f.get('issue', '')}")
                    st.caption(f"证据: {f.get('evidence', '')} | 审稿意见: {f.get('reviewer_comment', '')}")

            cross = critical_review.get("cross_paper_findings", [])
            if cross:
                st.markdown(f"### {icon('link', size='sm')} 跨论文对比发现")
                for cp in cross:
                    rel_icon = {"contradiction": icon("xmark", size="sm"), "extension": icon("arrow_right", size="sm"),
                                "supersedes": icon("arrow_up", size="sm"), "alternative": icon("rotate", size="sm")}
                    st.markdown(f"{rel_icon.get(cp.get('relationship', ''), '')} **{cp.get('issue', '')}** — 关联: {cp.get('related_paper', '')}")
                    st.caption(cp.get("detail", ""))

# ── TAB: 完整笔记 (R3 only) ──
note_tab_idx = None
if reading_round == "R3":
    note_tab_idx = len(tab_objects) - 2
if note_tab_idx and note_tab_idx < len(tab_objects):
    with tab_objects[note_tab_idx]:
        if not note_draft:
            empty_state(
                title="尚未生成内容",
                description="请先在「一键生成」中选择 R3 并生成完整笔记",
                icon_name="pen_to_square",
            )
        else:
            st.subheader("📝 完整学术笔记")
            if isinstance(note_draft, dict):
                st.json(note_draft)
            else:
                st.markdown(note_draft[:8000])
                if len(str(note_draft)) > 8000:
                    with st.expander("查看完整笔记"):
                        st.markdown(str(note_draft)[8000:])

            st.divider()
            st.subheader("📤 写入 Obsidian")
            st.caption("目标 Vault: C:\\Users\\Public\\Documents")
            if st.button("📝 写入 Obsidian（完整学术笔记）", use_container_width=True, type="primary"):
                with st.spinner("正在写入 Obsidian Vault..."):
                    raw_cards = gen.get("concept_cards", [])
                    if isinstance(raw_cards, dict):
                        safe_cards = [
                            {"name": k, "name_en": k, "definition": str(v), "category": "5C",
                             "related_concepts": [], "related_papers": [], "difficulty": "中等",
                             "context_in_paper": "", "evolution_line": "", "one_sentence": str(v),
                             "formal_definition": str(v)}
                            for k, v in raw_cards.items()
                        ]
                    elif isinstance(raw_cards, list):
                        safe_cards = [c for c in raw_cards if isinstance(c, dict)]
                    else:
                        safe_cards = []
                    write_result = post("/api/obsidian/write-all", {
                        "paper_id": paper_id,
                        "note_draft": note_draft,
                        "concept_cards": safe_cards,
                        "vocabulary_md": gen.get("vocabulary_md", ""),
                    })
                if write_result.get("error"):
                    st.error(f"写入失败: {write_result['error']}")
                else:
                    st.success("已全部写入 Obsidian！")
                    st.info(f"论文笔记: `{write_result.get('paper_path', '')}`")

# ── TAB: 专业词汇 (last tab) ──
vocab_tab_idx = len(tab_objects) - 1
with tab_objects[vocab_tab_idx]:
    if not vocabulary:
        empty_state(
            title="尚未生成内容",
            description="请先在「一键生成」中生成内容（专业词汇随 R1 一起生成）",
            icon_name="book",
        )
    else:
        st.subheader("📖 专业词汇表")
        cs = vocabulary.get("cs_terms", [])
        adv = vocabulary.get("advanced_words", [])

        col_meta1, col_meta2 = st.columns(2)
        with col_meta1:
            st.metric(f"{icon('microscope', size='sm')} 专业术语", len(cs))
        with col_meta2:
            st.metric(f"{icon('language', size='sm')} 学术词汇", len(adv))

        if cs:
            st.markdown(f"### {icon('microscope', size='sm')} 计算机专业术语")
            st.dataframe(
                [{"术语": w['word'], "音标": w.get('phonetic', ''), "学术定义": (w.get('formal_definition', w.get('meaning_cn', '')))[:60],
                  "上下文": (w.get('context_in_paper', ''))[:40]} for w in cs],
                use_container_width=True, hide_index=True
            )

        if adv:
            st.markdown(f"### {icon('language', size='sm')} 学术英语词汇")
            st.dataframe(
                [{"词汇": w['word'], "音标": w.get('phonetic', ''), "学术用法": (w.get('academic_usage', w.get('meaning_cn', '')))[:50],
                  "搭配": ", ".join(w.get('collocations', [])[:2])} for w in adv],
                use_container_width=True, hide_index=True
            )

        if vocab_md:
            with st.expander(f"{icon('file_lines', size='sm')} 查看 Markdown 源码"):
                st.code(vocab_md, language="markdown")

# ── TAB: 相关研究 (AI Research) ──
research_tab_idx = len(tab_objects) - 1
with tab_objects[research_tab_idx]:
    st.subheader("🔬 AI 研究助手 — 相关研究")
    st.caption("基于 GPT Researcher，为当前论文搜索相关研究成果")

    paper_title = paper.get("title", "")
    paper_abstract = paper.get("abstract", "")

    default_query = f"关于「{paper_title}」的最新相关研究进展和对比分析"
    research_query = st.text_area(
        "研究问题",
        value=default_query,
        height=80,
        key="research_query_input",
    )

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        r_report_type = st.selectbox(
            "报告类型",
            options=[("快速摘要", "research_report"), ("深度分析", "detailed_report")],
            format_func=lambda x: x[0],
            index=0,
            key="research_report_type",
        )
    with col_r2:
        r_tone = st.selectbox(
            "风格",
            options=[("客观", "Objective"), ("学术", "Formal"), ("分析", "Analytical")],
            format_func=lambda x: x[0],
            index=1,
            key="research_tone",
        )

    if st.button("🚀 发起相关研究", key="start_research_btn", use_container_width=True):
        if research_query.strip():
            with st.spinner(f"{icon('spinner', size='sm')} AI 正在搜索和分析相关研究，请耐心等待..."):
                result = post("/api/research/sync", {
                    "query": research_query.strip(),
                    "report_type": r_report_type[1],
                    "report_source": "web",
                    "tone": r_tone[1],
                    "paper_id": paper_id,
                })
            if "error" in result:
                st.error(f"研究失败：{result['error']}")
            else:
                st.success("研究完成！")
                st.rerun()
        else:
            st.warning("请输入研究问题")

    st.markdown("---")
    st.markdown(f"#### {icon('list', size='sm')} 已关联的研究报告")

    try:
        related = get(f"/api/research/paper/{paper_id}/related")
        related_reports = related.get("reports", [])
    except Exception:
        related_reports = []

    if not related_reports:
        empty_state(
            title="暂无关联研究",
            description="暂无关联的研究报告。点击上方按钮发起相关研究！",
            icon_name="microscope",
        )
    else:
        for rr in related_reports:
            r_status = rr.get("status", "unknown")
            status_icon_map = {"pending": icon("clock", size="sm"), "completed": icon("check", size="sm"), "failed": icon("xmark", size="sm")}
            status_icon = status_icon_map.get(r_status, icon("question", size="sm"))
            card(
                content=f"""
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                    <div>
                        <div style="font-weight:600; color:var(--color-text-primary);">{status_icon} {rr.get('query', 'N/A')}</div>
                        <div style="font-size:0.8rem; color:var(--color-text-muted);">
                            类型: {rr.get('report_type', '')} | 成本: ${rr.get('research_costs', 0):.4f} | {rr.get('created_at', '')}
                        </div>
                    </div>
                </div>
                """,
                variant="default",
                padding="1rem",
            )

            if r_status == "completed" and rr.get("report_content"):
                with st.expander("查看报告"):
                    st.markdown(rr["report_content"])
                    if rr.get("source_urls"):
                        st.markdown(f"**{icon('link', size='sm')} 参考来源：**")
                        for url in rr["source_urls"]:
                            st.markdown(f"- [{url}]({url})")
