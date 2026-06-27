# -*- coding: utf-8 -*-
"""WPS 风格 PDF 论文阅读器视图。

通过 PDF.js（CDN）在 st.components.v1.html 嵌入的完整 HTML/JS UI 中渲染论文 PDF，
外观与交互仿照 WPS Office 的 PDF 阅读页面：顶部工具栏 + 左侧可收起侧边栏（缩略图/大纲）
+ 中央连续滚动视图 + 底部状态栏。
"""
import os
import base64
import html as _html

import streamlit as st
import streamlit.components.v1 as components

from streamlit_app.utils.api_client import get  # noqa: F401  (复用错误处理约定)
from streamlit_app.components.icon import icon  # noqa: F401

st.set_page_config(layout="wide")

# ── 解析 paper_id ───────────────────────────────────────────
paper_id = st.session_state.get("selected_paper_id") or st.query_params.get("paper_id")
if not paper_id:
    st.error("请先选择一篇论文")
    if st.button("返回主题浏览", use_container_width=True):
        st.switch_page("views/topic_browser.py")
    st.stop()

# ── 获取论文元信息 ───────────────────────────────────────────
paper = None
try:
    paper = get(f"/api/papers/{paper_id}")
except Exception:
    pass
if not paper or (isinstance(paper, dict) and "error" in paper):
    st.error("无法获取论文信息")
    if st.button("返回主题浏览", use_container_width=True):
        st.switch_page("views/topic_browser.py")
    st.stop()

title = paper.get("title", "Untitled")
file_name = (title[:40] + "…") if len(title) > 40 else title

# ── 获取 PDF 二进制并 base64 编码 ────────────────────────────
# api_client.post 返回 resp.json()，无法承载二进制，因此此处直接调用 requests
# （与 api_client._import_requests 同样的优雅降级模式）。
API_BASE = "http://127.0.0.1:8000"
_headers = {}
_api_key = os.getenv("API_KEY", "")
if _api_key:
    _headers["X-API-Key"] = _api_key

pdf_b64 = None
pdf_error = None

_requests_mod = None
try:
    import requests as _requests_mod  # type: ignore
    _requests_mod = _requests_mod
except ImportError:
    _requests_mod = None

if _requests_mod is None:
    try:
        import httpx as _requests_mod  # type: ignore
    except ImportError:
        _requests_mod = None

if _requests_mod is None:
    pdf_error = "requests/httpx 库未安装"
else:
    try:
        if hasattr(_requests_mod, "post") and not hasattr(_requests_mod, "Client"):
            # requests 风格
            _resp = _requests_mod.post(
                f"{API_BASE}/api/reading/proxy-pdf",
                json={"paper_id": paper_id},
                timeout=60,
                headers=_headers,
            )
            content = _resp.content
            status = _resp.status_code
        else:
            # httpx 风格
            with _requests_mod.Client(timeout=60, headers=_headers) as _client:
                _resp = _client.post(
                    f"{API_BASE}/api/reading/proxy-pdf",
                    json={"paper_id": paper_id},
                )
            content = _resp.content
            status = _resp.status_code
        if status == 200 and content:
            pdf_b64 = base64.b64encode(content).decode("ascii")
        else:
            pdf_error = f"HTTP {status}"
    except Exception as e:
        pdf_error = str(e)

if not pdf_b64:
    st.error(f"无法加载 PDF：{pdf_error}")
    pdf_url = paper.get("pdf_url")
    if pdf_url:
        st.link_button("在外部打开原始 PDF", pdf_url, use_container_width=True)
    if st.button("返回主题浏览", use_container_width=True):
        st.switch_page("views/topic_browser.py")
    st.stop()

# ── 顶部真实的 Streamlit 返回按钮（HTML 内的返回箭头无法跨 iframe 导航） ──
_col_back, __col_title = st.columns([1, 6])
with _col_back:
    if st.button("← 返回主题浏览", use_container_width=True, key="pdf_reader_back"):
        st.switch_page("views/topic_browser.py")
with _col_title:
    st.markdown(
        f"<div style='font-size:0.9rem;color:var(--color-text-secondary);"
        f"padding-top:0.35rem;'>📄 { _html.escape(file_name) }</div>",
        unsafe_allow_html=True,
    )

# ── WPS 风格 PDF 阅读器（HTML + CSS + JS） ──────────────────
HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDF 阅读器</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<style>
  * { box-sizing: border-box; }
  html, body {
    height: 100%;
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f0f0f0;
    color: #202124;
    overflow: hidden;
  }
  #app {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  /* ── 顶部工具栏 ── */
  #toolbar {
    height: 48px;
    flex: 0 0 48px;
    background: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    align-items: center;
    padding: 0 10px;
    gap: 8px;
    font-size: 13px;
    overflow-x: auto;
    overflow-y: hidden;
    white-space: nowrap;
    z-index: 20;
  }
  .tb-group {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 0 6px;
    border-right: 1px solid #ececec;
  }
  .tb-group:last-child { border-right: none; }
  .tb-btn {
    height: 30px;
    min-width: 30px;
    padding: 0 8px;
    border: 1px solid transparent;
    background: transparent;
    color: #5f6368;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  .tb-btn:hover { background: #f1f3f4; color: #202124; }
  .tb-btn:active { background: #e4e7e9; }
  .tb-btn.primary {
    background: #2b5fff;
    color: #fff;
    border-color: #2b5fff;
  }
  .tb-btn.primary:hover { background: #1f4ad9; }
  .tb-btn.active {
    background: #e8f0fe;
    color: #2b5fff;
    border-color: #c6dafc;
  }
  .tb-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .tb-input {
    height: 28px;
    border: 1px solid #dadce0;
    border-radius: 4px;
    text-align: center;
    font-size: 13px;
    color: #202124;
    background: #fff;
  }
  #pageInput { width: 48px; }
  #zoomInput { width: 56px; }
  #searchInput {
    width: 140px;
    text-align: left;
    padding: 0 8px;
  }
  .tb-sep {
    width: 1px;
    height: 22px;
    background: #e0e0e0;
    margin: 0 2px;
  }
  .file-name {
    font-weight: 600;
    color: #202124;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-left: 4px;
  }
  .match-count {
    font-size: 12px;
    color: #5f6368;
    min-width: 56px;
    text-align: center;
  }

  /* ── 主体：侧边栏 + 视图 ── */
  #body {
    flex: 1 1 auto;
    display: flex;
    min-height: 0;
    position: relative;
  }
  #sidebar {
    width: 220px;
    flex: 0 0 220px;
    background: #fafafa;
    border-right: 1px solid #e0e0e0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    transition: width 0.2s, flex-basis 0.2s, padding 0.2s;
    overflow: hidden;
  }
  #sidebar.collapsed {
    width: 0;
    flex-basis: 0;
    border-right: none;
  }
  .sidebar-tabs {
    display: flex;
    border-bottom: 1px solid #e0e0e0;
    flex: 0 0 36px;
  }
  .sidebar-tab {
    flex: 1;
    height: 36px;
    border: none;
    background: transparent;
    color: #5f6368;
    font-size: 13px;
    cursor: pointer;
    border-bottom: 2px solid transparent;
  }
  .sidebar-tab.active {
    color: #2b5fff;
    border-bottom-color: #2b5fff;
    font-weight: 600;
  }
  .sidebar-content {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 8px;
  }
  .thumb-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 10px;
    cursor: pointer;
    padding: 4px;
    border: 2px solid transparent;
    border-radius: 4px;
  }
  .thumb-item:hover { background: #eef1f3; }
  .thumb-item.active { border-color: #2b5fff; background: #e8f0fe; }
  .thumb-item canvas {
    background: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.15);
    max-width: 100%;
    height: auto;
  }
  .thumb-item .thumb-num {
    margin-top: 4px;
    font-size: 11px;
    color: #5f6368;
  }
  .outline-item {
    padding: 6px 8px;
    cursor: pointer;
    color: #202124;
    font-size: 13px;
    border-radius: 4px;
    line-height: 1.4;
  }
  .outline-item:hover { background: #eef1f3; color: #2b5fff; }
  .outline-empty { color: #999; font-size: 12px; padding: 12px 8px; text-align: center; }

  /* ── 视图区 ── */
  #viewer {
    flex: 1 1 auto;
    overflow: auto;
    background: #f0f0f0;
    padding: 16px;
    min-height: 0;
    position: relative;
  }
  #pages-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }
  #pages-container.mode-double {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    justify-items: center;
  }
  .page-wrapper {
    position: relative;
    background: #fff;
    box-shadow: 0 2px 8px rgba(0,0,0,0.18);
    line-height: 0;
  }
  .page-wrapper.hidden { display: none !important; }
  .page-wrapper canvas { display: block; }
  .page-wrapper .page-label {
    position: absolute;
    bottom: 4px;
    right: 6px;
    background: rgba(0,0,0,0.55);
    color: #fff;
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 3px;
    line-height: 1.4;
    pointer-events: none;
  }
  .page-placeholder {
    background: #e8e8e8;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #999;
    font-size: 14px;
  }
  .page-placeholder i { font-size: 24px; opacity: 0.6; }

  /* ── 底部状态栏 ── */
  #statusbar {
    height: 28px;
    flex: 0 0 28px;
    background: #ffffff;
    border-top: 1px solid #e0e0e0;
    display: flex;
    align-items: center;
    padding: 0 14px;
    gap: 18px;
    font-size: 12px;
    color: #5f6368;
    z-index: 20;
  }
  #statusbar .sep { color: #ccc; }
  #progressWrap {
    flex: 1;
    height: 4px;
    background: #e0e0e0;
    border-radius: 2px;
    overflow: hidden;
    margin-left: 8px;
  }
  #progressBar {
    height: 100%;
    width: 0%;
    background: #2b5fff;
    transition: width 0.2s;
  }

  /* 加载遮罩 */
  #loadingMask {
    position: absolute;
    inset: 0;
    background: rgba(240,240,240,0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #2b5fff;
    font-size: 15px;
    z-index: 50;
    flex-direction: column;
    gap: 12px;
  }
  #loadingMask.hidden { display: none; }
  .spinner {
    border: 3px solid #c6dafc;
    border-top-color: #2b5fff;
    border-radius: 50%;
    width: 32px;
    height: 32px;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div id="app">
  <!-- 顶部工具栏 -->
  <div id="toolbar">
    <div class="tb-group">
      <button class="tb-btn" id="btnSidebar" title="侧边栏"><i class="fa-solid fa-bars"></i></button>
      <button class="tb-btn" id="btnBack" title="返回"><i class="fa-solid fa-chevron-left"></i></button>
      <span class="file-name" id="fileName">__FILE_NAME__</span>
    </div>

    <div class="tb-group">
      <button class="tb-btn" id="btnPrev" title="上一页"><i class="fa-solid fa-chevron-left"></i> 上一页</button>
      <input type="number" class="tb-input" id="pageInput" value="1" min="1">
      <span style="color:#5f6368;">/</span>
      <span id="pageTotal" style="min-width:36px;text-align:center;color:#5f6368;">-</span>
      <button class="tb-btn" id="btnNext" title="下一页">下一页 <i class="fa-solid fa-chevron-right"></i></button>
    </div>

    <div class="tb-group">
      <button class="tb-btn" id="btnZoomOut" title="缩小"><i class="fa-solid fa-magnifying-glass-minus"></i></button>
      <input type="text" class="tb-input" id="zoomInput" value="100%">
      <button class="tb-btn" id="btnZoomIn" title="放大"><i class="fa-solid fa-magnifying-glass-plus"></i></button>
      <button class="tb-btn" id="btnFitWidth" title="适合宽度">适合宽度</button>
      <button class="tb-btn" id="btnFitPage" title="适合页面">适合页面</button>
    </div>

    <div class="tb-group">
      <button class="tb-btn" id="btnRotate" title="顺时针旋转 90°"><i class="fa-solid fa-rotate-right"></i> 旋转</button>
    </div>

    <div class="tb-group">
      <input type="text" class="tb-input" id="searchInput" placeholder="搜索关键词...">
      <button class="tb-btn" id="btnSearchPrev" title="上一个匹配"><i class="fa-solid fa-chevron-up"></i></button>
      <span class="match-count" id="matchCount">0 / 0</span>
      <button class="tb-btn" id="btnSearchNext" title="下一个匹配"><i class="fa-solid fa-chevron-down"></i></button>
    </div>

    <div class="tb-group">
      <button class="tb-btn" id="btnModeSingle" title="单页">单页</button>
      <button class="tb-btn active" id="btnModeContinuous" title="连续滚动">连续</button>
      <button class="tb-btn" id="btnModeDouble" title="双页">双页</button>
    </div>

    <div class="tb-group">
      <a class="tb-btn primary" id="btnDownload" title="下载 PDF" download>
        <i class="fa-solid fa-download"></i> 下载
      </a>
    </div>
  </div>

  <!-- 主体 -->
  <div id="body">
    <div id="sidebar">
      <div class="sidebar-tabs">
        <button class="sidebar-tab active" data-tab="thumbnails">缩略图</button>
        <button class="sidebar-tab" data-tab="outline">大纲</button>
      </div>
      <div class="sidebar-content" id="sidebarThumbnails"></div>
      <div class="sidebar-content" id="sidebarOutline" style="display:none;"></div>
    </div>

    <div id="viewer">
      <div id="pages-container"></div>
      <div id="loadingMask"><div class="spinner"></div><div>正在加载 PDF…</div></div>
    </div>
  </div>

  <!-- 底部状态栏 -->
  <div id="statusbar">
    <span>第 <b id="stPage">1</b> / <b id="stTotal">-</b> 页</span>
    <span class="sep">|</span>
    <span>缩放 <b id="stZoom">100%</b></span>
    <span class="sep">|</span>
    <span>进度 <b id="stProgress">0%</b></span>
    <div id="progressWrap"><div id="progressBar"></div></div>
  </div>
</div>

<script>
(function () {
  "use strict";

  const PDF_DATA = "data:application/pdf;base64,__PDF_B64__";

  // ── 全局状态 ──
  const state = {
    pdfDoc: null,
    totalPages: 0,
    currentPage: 1,
    scale: 1.2,           // 初始渲染缩放（PDF 像素 / CSS 像素）
    zoomPct: 100,         // 显示给用户的缩放百分比
    rotation: 0,          // 全局旋转（0/90/180/270）
    viewMode: 'continuous', // 'single' | 'continuous' | 'double'
    pageViews: [],        // 每页 getViewport(scale=1, rotation=0) 的原始尺寸缓存
    renderedPages: new Set(),
    rendering: false,
    searchMatches: [],    // 命中的页码数组（1-based）
    searchIdx: -1,
    sidebarOpen: true,
    sidebarTab: 'thumbnails',
  };

  // ── DOM 引用 ──
  const $ = (id) => document.getElementById(id);
  const pagesContainer = $('pages-container');
  const viewer = $('viewer');
  const pageInput = $('pageInput');
  const pageTotal = $('pageTotal');
  const zoomInput = $('zoomInput');
  const matchCount = $('matchCount');
  const loadingMask = $('loadingMask');

  // ── PDF.js 初始化 ──
  if (window.pdfjsLib) {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  } else {
    loadingMask.innerHTML = '<div style="color:#d93025;"><i class="fa-solid fa-triangle-exclamation"></i> PDF.js 加载失败，请检查网络</div>';
    return;
  }

  // ── 工具函数 ──
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function viewportFor(num, scale, rotation) {
    return state.pdfDoc.getPage(num).then(function (page) {
      return page.getViewport({ scale: scale, rotation: rotation });
    });
  }

  function getRotatedViewport(page, scale) {
    return page.getViewport({ scale: scale, rotation: state.rotation });
  }

  // 计算适合宽度的缩放
  function computeFitWidthScale() {
    if (!state.pdfDoc || state.totalPages === 0) return 1;
    // 使用第一页尺寸作参考
    return state.pdfDoc.getPage(1).then(function (page) {
      const vp = page.getViewport({ scale: 1, rotation: state.rotation });
      const avail = viewer.clientWidth - 32; // 减去 padding
      let s = avail / vp.width;
      // 双页模式要除以 2
      if (state.viewMode === 'double') s = s / 2 - 6;
      return Math.max(0.2, s);
    });
  }

  function computeFitPageScale() {
    if (!state.pdfDoc || state.totalPages === 0) return 1;
    return state.pdfDoc.getPage(1).then(function (page) {
      const vp = page.getViewport({ scale: 1, rotation: state.rotation });
      const availW = viewer.clientWidth - 32;
      const availH = viewer.clientHeight - 32;
      return Math.max(0.2, Math.min(availW / vp.width, availH / vp.height));
    });
  }

  // ── 渲染单页到指定 canvas ──
  function renderPageTo(num, canvas, scale) {
    return state.pdfDoc.getPage(num).then(function (page) {
      const vp = getRotatedViewport(page, scale);
      const ctx = canvas.getContext('2d');
      // 处理高 DPI
      const outputScale = window.devicePixelRatio || 1;
      canvas.width = Math.floor(vp.width * outputScale);
      canvas.height = Math.floor(vp.height * outputScale);
      canvas.style.width = Math.floor(vp.width) + 'px';
      canvas.style.height = Math.floor(vp.height) + 'px';
      ctx.setTransform(outputScale, 0, 0, outputScale, 0, 0);
      const renderTask = page.render({
        canvasContext: ctx,
        viewport: vp,
        transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null,
      });
      return renderTask.promise;
    });
  }

  // ── 为主视图创建占位 ──
  function buildPlaceholders() {
    pagesContainer.innerHTML = '';
    state.renderedPages.clear();
    for (let i = 1; i <= state.totalPages; i++) {
      const wrap = document.createElement('div');
      wrap.className = 'page-wrapper';
      wrap.dataset.page = String(i);
      wrap.id = 'page-wrap-' + i;

      const placeholder = document.createElement('div');
      placeholder.className = 'page-placeholder';
      placeholder.style.width = '300px';
      placeholder.style.height = '400px';
      placeholder.innerHTML = '<i class="fa-solid fa-file-lines"></i>';

      const label = document.createElement('div');
      label.className = 'page-label';
      label.textContent = String(i);

      wrap.appendChild(placeholder);
      wrap.appendChild(label);
      pagesContainer.appendChild(wrap);
    }
    applyViewModeVisibility();
    observePages();
  }

  // ── 渲染主视图中某页（替换占位为 canvas） ──
  function renderMainPage(num) {
    if (state.renderedPages.has(num)) return Promise.resolve();
    const wrap = $('page-wrap-' + num);
    if (!wrap) return Promise.resolve();
    state.renderedPages.add(num);
    return state.pdfDoc.getPage(num).then(function (page) {
      const vp = getRotatedViewport(page, state.scale);
      // 先按真实尺寸调整占位容器，避免滚动条跳动
      const placeholder = wrap.querySelector('.page-placeholder');
      if (placeholder) {
        placeholder.style.width = Math.floor(vp.width) + 'px';
        placeholder.style.height = Math.floor(vp.height) + 'px';
      }
      // 移除已存在的 canvas
      const oldCanvas = wrap.querySelector('canvas');
      if (oldCanvas) oldCanvas.remove();
      const canvas = document.createElement('canvas');
      wrap.insertBefore(canvas, wrap.querySelector('.page-label'));
      return renderPageTo(num, canvas, state.scale).then(function () {
        if (placeholder) placeholder.remove();
      });
    }).catch(function () {
      state.renderedPages.delete(num);
    });
  }

  // ── 重新渲染所有已渲染页（缩放/旋转后） ──
  function rerenderVisible() {
    state.renderedPages.clear();
    for (let i = 1; i <= state.totalPages; i++) {
      const wrap = $('page-wrap-' + i);
      if (!wrap) continue;
      // 还原为占位
      const oldCanvas = wrap.querySelector('canvas');
      if (oldCanvas) oldCanvas.remove();
      if (!wrap.querySelector('.page-placeholder')) {
        const ph = document.createElement('div');
        ph.className = 'page-placeholder';
        ph.innerHTML = '<i class="fa-solid fa-file-lines"></i>';
        wrap.insertBefore(ph, wrap.querySelector('.page-label'));
      }
    }
    // 更新所有占位尺寸
    const updateSizes = [];
    for (let i = 1; i <= state.totalPages; i++) {
      updateSizes.push(
        state.pdfDoc.getPage(i).then(function (page) {
          const vp = getRotatedViewport(page, state.scale);
          const wrap = $('page-wrap-' + i);
          if (wrap) {
            const ph = wrap.querySelector('.page-placeholder');
            if (ph) {
              ph.style.width = Math.floor(vp.width) + 'px';
              ph.style.height = Math.floor(vp.height) + 'px';
            }
          }
        })
      );
    }
    Promise.all(updateSizes).then(function () {
      // 渲染当前可见页
      renderVisiblePages();
    });
  }

  // ── 根据视口可见性渲染 ──
  function renderVisiblePages() {
    if (state.viewMode === 'single') {
      renderMainPage(state.currentPage);
      return;
    }
    if (state.viewMode === 'double') {
      renderMainPage(state.currentPage);
      if (state.currentPage + 1 <= state.totalPages) {
        renderMainPage(state.currentPage + 1);
      }
      return;
    }
    // continuous：遍历所有页，渲染在视口附近的
    const viewerRect = viewer.getBoundingClientRect();
    const margin = 400;
    for (let i = 1; i <= state.totalPages; i++) {
      const wrap = $('page-wrap-' + i);
      if (!wrap || wrap.classList.contains('hidden')) continue;
      const r = wrap.getBoundingClientRect();
      const visible = (r.bottom > viewerRect.top - margin) && (r.top < viewerRect.bottom + margin);
      if (visible) renderMainPage(i);
    }
  }

  // ── IntersectionObserver：进入视口时渲染 ──
  let io = null;
  function observePages() {
    if (io) io.disconnect();
    io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          const num = parseInt(entry.target.dataset.page, 10);
          renderMainPage(num);
        }
      });
    }, { root: viewer, rootMargin: '600px 0px', threshold: 0 });
    document.querySelectorAll('.page-wrapper').forEach(function (el) {
      io.observe(el);
    });
  }

  // ── 视图模式可见性 ──
  function applyViewModeVisibility() {
    const wraps = document.querySelectorAll('.page-wrapper');
    if (state.viewMode === 'continuous') {
      pagesContainer.classList.remove('mode-double');
      wraps.forEach(function (w) { w.classList.remove('hidden'); });
    } else if (state.viewMode === 'single') {
      pagesContainer.classList.remove('mode-double');
      wraps.forEach(function (w) {
        w.classList.toggle('hidden', parseInt(w.dataset.page, 10) !== state.currentPage);
      });
    } else if (state.viewMode === 'double') {
      pagesContainer.classList.add('mode-double');
      // 双页：当前页与下一页成对显示。简化：显示所有页（grid 自动两列），但隐藏非当前对。
      const pairStart = state.currentPage % 2 === 0 ? state.currentPage - 1 : state.currentPage;
      wraps.forEach(function (w) {
        const n = parseInt(w.dataset.page, 10);
        w.classList.toggle('hidden', !(n === pairStart || n === pairStart + 1));
      });
    }
  }

  // ── 跳转到指定页 ──
  function jumpToPage(num) {
    num = clamp(num, 1, state.totalPages);
    state.currentPage = num;
    pageInput.value = num;
    if (state.viewMode === 'single' || state.viewMode === 'double') {
      applyViewModeVisibility();
      renderVisiblePages();
      const wrap = $('page-wrap-' + num);
      if (wrap) wrap.scrollIntoView({ behavior: 'auto', block: 'start' });
    } else {
      const wrap = $('page-wrap-' + num);
      if (wrap) wrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    updateStatus();
    highlightThumb(num);
  }

  // ── 缩放 ──
  function setZoom(pct) {
    pct = clamp(pct, 20, 600);
    state.zoomPct = pct;
    state.scale = (pct / 100) * 1.2; // 1.2 是 PDF.js 的基础渲染缩放
    zoomInput.value = pct + '%';
    rerenderVisible();
    updateStatus();
  }
  function zoomIn() { setZoom(state.zoomPct + 10); }
  function zoomOut() { setZoom(state.zoomPct - 10); }

  function fitWidth() {
    computeFitWidthScale().then(function (s) {
      const pct = Math.round((s / 1.2) * 100);
      setZoom(pct);
    });
  }
  function fitPage() {
    computeFitPageScale().then(function (s) {
      const pct = Math.round((s / 1.2) * 100);
      setZoom(pct);
    });
  }

  // ── 旋转 ──
  function rotate() {
    state.rotation = (state.rotation + 90) % 360;
    rerenderVisible();
  }

  // ── 视图模式切换 ──
  function setViewMode(mode) {
    state.viewMode = mode;
    $('btnModeSingle').classList.toggle('active', mode === 'single');
    $('btnModeContinuous').classList.toggle('active', mode === 'continuous');
    $('btnModeDouble').classList.toggle('active', mode === 'double');
    applyViewModeVisibility();
    renderVisiblePages();
    jumpToPage(state.currentPage);
  }

  // ── 状态栏更新 ──
  function updateStatus() {
    $('stPage').textContent = state.currentPage;
    $('stTotal').textContent = state.totalPages;
    $('stZoom').textContent = state.zoomPct + '%';
    const progress = state.totalPages > 0
      ? Math.round((state.currentPage / state.totalPages) * 100) : 0;
    $('stProgress').textContent = progress + '%';
    $('progressBar').style.width = progress + '%';
    pageTotal.textContent = state.totalPages;
  }

  // ── 缩略图 ──
  function buildThumbnails() {
    const container = $('sidebarThumbnails');
    container.innerHTML = '';
    const thumbScale = 0.2;
    let chain = Promise.resolve();
    for (let i = 1; i <= state.totalPages; i++) {
      (function (num) {
        const item = document.createElement('div');
        item.className = 'thumb-item';
        item.dataset.page = String(num);
        item.innerHTML = '<canvas></canvas><div class="thumb-num">' + num + '</div>';
        item.addEventListener('click', function () { jumpToPage(num); });
        container.appendChild(item);
        chain = chain.then(function () {
          return state.pdfDoc.getPage(num).then(function (page) {
            const vp = page.getViewport({ scale: thumbScale, rotation: state.rotation });
            const canvas = item.querySelector('canvas');
            canvas.width = Math.floor(vp.width);
            canvas.height = Math.floor(vp.height);
            return page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
          });
        });
      })(i);
    }
  }

  function highlightThumb(num) {
    document.querySelectorAll('.thumb-item').forEach(function (el) {
      el.classList.toggle('active', parseInt(el.dataset.page, 10) === num);
    });
    const active = document.querySelector('.thumb-item.active');
    if (active && state.sidebarTab === 'thumbnails') {
      active.scrollIntoView({ block: 'nearest' });
    }
  }

  // ── 大纲 ──
  function buildOutline() {
    const container = $('sidebarOutline');
    container.innerHTML = '';
    return state.pdfDoc.getOutline().then(function (outline) {
      if (!outline || outline.length === 0) {
        container.innerHTML = '<div class="outline-empty">该 PDF 没有大纲</div>';
        return;
      }
      const renderNode = function (node, depth) {
        const div = document.createElement('div');
        div.className = 'outline-item';
        div.style.paddingLeft = (8 + depth * 14) + 'px';
        div.textContent = node.title || '(无标题)';
        div.addEventListener('click', function () {
          jumpToDestination(node.dest);
        });
        container.appendChild(div);
        if (node.items && node.items.length) {
          node.items.forEach(function (child) { renderNode(child, depth + 1); });
        }
      };
      outline.forEach(function (node) { renderNode(node, 0); });
    }).catch(function () {
      container.innerHTML = '<div class="outline-empty">无法读取大纲</div>';
    });
  }

  function jumpToDestination(dest) {
    try {
      const promise = (typeof dest === 'string')
        ? state.pdfDoc.getDestination(dest)
        : Promise.resolve(dest);
      promise.then(function (explicit) {
        if (!explicit) return;
        state.pdfDoc.getPageIndex(explicit[0]).then(function (idx) {
          jumpToPage(idx + 1);
        });
      });
    } catch (e) { /* 忽略 */ }
  }

  // ── 搜索（页级匹配导航） ──
  function runSearch() {
    const q = $('searchInput').value.trim();
    if (!q) {
      state.searchMatches = [];
      state.searchIdx = -1;
      matchCount.textContent = '0 / 0';
      return;
    }
    const lower = q.toLowerCase();
    state.searchMatches = [];
    let chain = Promise.resolve();
    for (let i = 1; i <= state.totalPages; i++) {
      (function (num) {
        chain = chain.then(function () {
          return state.pdfDoc.getPage(num).then(function (page) {
            return page.getTextContent();
          }).then(function (tc) {
            const text = (tc.items || []).map(function (it) { return it.str || ''; }).join(' ').toLowerCase();
            if (text.indexOf(lower) !== -1) state.searchMatches.push(num);
          }).catch(function () {});
        });
      })(i);
    }
    chain.then(function () {
      state.searchIdx = state.searchMatches.length > 0 ? 0 : -1;
      updateMatchCount();
      if (state.searchMatches.length > 0) jumpToPage(state.searchMatches[0]);
    });
  }
  function updateMatchCount() {
    const total = state.searchMatches.length;
    const cur = total > 0 ? (state.searchIdx + 1) : 0;
    matchCount.textContent = cur + ' / ' + total;
  }
  function nextMatch() {
    if (state.searchMatches.length === 0) return;
    state.searchIdx = (state.searchIdx + 1) % state.searchMatches.length;
    updateMatchCount();
    jumpToPage(state.searchMatches[state.searchIdx]);
  }
  function prevMatch() {
    if (state.searchMatches.length === 0) return;
    state.searchIdx = (state.searchIdx - 1 + state.searchMatches.length) % state.searchMatches.length;
    updateMatchCount();
    jumpToPage(state.searchMatches[state.searchIdx]);
  }

  // ── 滚动监听：更新当前页 ──
  let scrollTimer = null;
  viewer.addEventListener('scroll', function () {
    if (state.viewMode !== 'continuous') return;
    if (scrollTimer) clearTimeout(scrollTimer);
    scrollTimer = setTimeout(function () {
      const viewerRect = viewer.getBoundingClientRect();
      let best = state.currentPage;
      let bestDist = Infinity;
      for (let i = 1; i <= state.totalPages; i++) {
        const wrap = $('page-wrap-' + i);
        if (!wrap || wrap.classList.contains('hidden')) continue;
        const r = wrap.getBoundingClientRect();
        // 选择顶部最接近视口顶部的页
        const dist = Math.abs(r.top - viewerRect.top);
        if (dist < bestDist && r.bottom > viewerRect.top) {
          bestDist = dist;
          best = i;
        }
      }
      if (best !== state.currentPage) {
        state.currentPage = best;
        pageInput.value = best;
        updateStatus();
        highlightThumb(best);
      }
      renderVisiblePages();
    }, 80);
  });

  // ── 侧边栏切换 ──
  function toggleSidebar() {
    state.sidebarOpen = !state.sidebarOpen;
    $('sidebar').classList.toggle('collapsed', !state.sidebarOpen);
  }
  function switchSidebarTab(tab) {
    state.sidebarTab = tab;
    document.querySelectorAll('.sidebar-tab').forEach(function (el) {
      el.classList.toggle('active', el.dataset.tab === tab);
    });
    $('sidebarThumbnails').style.display = tab === 'thumbnails' ? 'block' : 'none';
    $('sidebarOutline').style.display = tab === 'outline' ? 'block' : 'none';
  }

  // ── 事件绑定 ──
  $('btnSidebar').addEventListener('click', toggleSidebar);
  $('btnBack').addEventListener('click', function () {
    // iframe 内无法直接切换 Streamlit 页，尝试通知父窗口
    try { window.parent.postMessage({ type: 'pdf_reader_back' }, '*'); } catch (e) {}
    // 滚到顶部作为视觉反馈
    viewer.scrollTop = 0;
  });
  $('btnPrev').addEventListener('click', function () { jumpToPage(state.currentPage - 1); });
  $('btnNext').addEventListener('click', function () { jumpToPage(state.currentPage + 1); });
  pageInput.addEventListener('change', function () {
    const n = parseInt(pageInput.value, 10);
    if (!isNaN(n)) jumpToPage(n);
  });
  $('btnZoomOut').addEventListener('click', zoomOut);
  $('btnZoomIn').addEventListener('click', zoomIn);
  zoomInput.addEventListener('change', function () {
    const v = parseInt(zoomInput.value, 10);
    if (!isNaN(v)) setZoom(v);
  });
  $('btnFitWidth').addEventListener('click', fitWidth);
  $('btnFitPage').addEventListener('click', fitPage);
  $('btnRotate').addEventListener('click', rotate);
  $('btnSearchNext').addEventListener('click', nextMatch);
  $('btnSearchPrev').addEventListener('click', prevMatch);
  $('searchInput').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); runSearch(); }
  });
  $('btnModeSingle').addEventListener('click', function () { setViewMode('single'); });
  $('btnModeContinuous').addEventListener('click', function () { setViewMode('continuous'); });
  $('btnModeDouble').addEventListener('click', function () { setViewMode('double'); });
  document.querySelectorAll('.sidebar-tab').forEach(function (el) {
    el.addEventListener('click', function () { switchSidebarTab(el.dataset.tab); });
  });

  // 下载链接
  $('btnDownload').setAttribute('href', PDF_DATA);
  $('btnDownload').setAttribute('download', document.title || 'paper.pdf');

  // 键盘快捷键
  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') { jumpToPage(state.currentPage - 1); e.preventDefault(); }
    else if (e.key === 'ArrowRight' || e.key === 'PageDown') { jumpToPage(state.currentPage + 1); e.preventDefault(); }
    else if (e.key === '+' || e.key === '=') { zoomIn(); }
    else if (e.key === '-') { zoomOut(); }
  });

  // ── 启动：加载 PDF ──
  const loadingTask = pdfjsLib.getDocument({ url: PDF_DATA });
  loadingTask.promise.then(function (pdf) {
    state.pdfDoc = pdf;
    state.totalPages = pdf.numPages;
    loadingMask.classList.add('hidden');
    buildPlaceholders();
    buildThumbnails();
    buildOutline();
    updateStatus();
    // 初始跳到第 1 页并渲染
    setTimeout(function () {
      renderVisiblePages();
      highlightThumb(1);
    }, 100);
  }).catch(function (err) {
    loadingMask.innerHTML =
      '<div style="color:#d93025;text-align:center;padding:20px;">' +
      '<i class="fa-solid fa-triangle-exclamation" style="font-size:28px;"></i>' +
      '<div style="margin-top:8px;">PDF 加载失败：' + (err && err.message ? err.message : String(err)) + '</div></div>';
  });
})();
</script>
</body>
</html>
'''

html_str = (HTML_TEMPLATE
            .replace("__PDF_B64__", pdf_b64)
            .replace("__FILE_NAME__", _html.escape(file_name)))

components.html(html_str, height=900, scrolling=True)
