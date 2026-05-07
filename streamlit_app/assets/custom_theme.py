"""Design Tokens for 核动力科研牛马 UI System — Glassmorphism Dark Theme."""

COLORS = {
    "primary": "#2dd4bf",
    "primary_dark": "#14b8a6",
    "primary_light": "#5eead4",
    "secondary": "#0ea5e9",
    "success": "#34d399",
    "warning": "#f59e0b",
    "danger": "#f87171",
    "info": "#38bdf8",
    "bg": "#0B1120",
    "bg_secondary": "#0f172a",
    "surface": "rgba(255, 255, 255, 0.03)",
    "surface_hover": "rgba(255, 255, 255, 0.06)",
    "surface_glass": "rgba(15, 23, 42, 0.60)",
    "text_primary": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "border": "rgba(255, 255, 255, 0.06)",
    "border_light": "rgba(255, 255, 255, 0.10)",
    "accent_gold": "#fbbf24",
    "accent_orange": "#f59e0b",
}

SPACING = {
    "xs": "4px",
    "sm": "8px",
    "md": "16px",
    "lg": "24px",
    "xl": "32px",
    "2xl": "48px",
}

RADIUS = {
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "20px",
    "2xl": "24px",
    "full": "9999px",
}

SHADOWS = {
    "sm": "0 1px 3px rgba(0,0,0,0.3)",
    "md": "0 4px 12px rgba(0,0,0,0.4)",
    "lg": "0 8px 30px rgba(0,0,0,0.5)",
    "xl": "0 12px 40px rgba(0,0,0,0.6)",
    "glow_primary": "0 0 20px rgba(45, 212, 191, 0.15)",
    "glow_gold": "0 0 20px rgba(251, 191, 36, 0.15)",
}

TYPOGRAPHY = {
    "xs": "0.75rem",
    "sm": "0.875rem",
    "md": "1rem",
    "lg": "1.125rem",
    "xl": "1.25rem",
    "2xl": "1.5rem",
    "3xl": "2rem",
    "4xl": "2.5rem",
}

TRANSITIONS = {
    "fast": "all 0.15s ease",
    "normal": "all 0.2s ease",
    "slow": "all 0.3s ease",
}


def get_css_variables() -> str:
    """Return CSS variable definitions for injection into :root."""
    lines = ["    :root {"]
    for key, val in COLORS.items():
        lines.append(f"        --color-{key}: {val};")
    for key, val in SPACING.items():
        lines.append(f"        --spacing-{key}: {val};")
    for key, val in RADIUS.items():
        lines.append(f"        --radius-{key}: {val};")
    for key, val in SHADOWS.items():
        lines.append(f"        --shadow-{key}: {val};")
    for key, val in TYPOGRAPHY.items():
        lines.append(f"        --text-{key}: {val};")
    lines.append("    }")
    return "\n".join(lines)


def get_global_css() -> str:
    """Return the full global CSS string for Streamlit injection."""
    css = f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css');
    {get_css_variables()}
    html, body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: var(--color-bg) !important; }}
    [class*="css"] {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
    .stApp {{ background: var(--color-bg) !important; }}
    [data-testid="stAppViewContainer"] {{ background: var(--color-bg) !important; }}

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: rgba(255,255,255,0.2); }}

    /* ── Buttons ── */
    .stButton button {{
        border-radius: var(--radius-md) !important;
        font-weight: 600 !important;
        transition: {TRANSITIONS['normal']} !important;
        border: none !important;
        background: rgba(255,255,255,0.06) !important;
        color: var(--color-text-primary) !important;
        backdrop-filter: blur(10px);
    }}
    .stButton button:hover {{
        transform: translateY(-1px);
        background: rgba(255,255,255,0.10) !important;
        box-shadow: var(--shadow-md);
    }}
    .stButton button[kind="primary"] {{
        background: linear-gradient(135deg, var(--color-primary), var(--color-primary-dark)) !important;
        color: #0B1120 !important;
        box-shadow: var(--shadow-glow_primary);
    }}
    .stButton button[kind="primary"]:hover {{
        box-shadow: 0 0 30px rgba(45, 212, 191, 0.3);
    }}
    .stButton button[kind="secondary"] {{
        background: transparent !important;
        color: var(--color-primary) !important;
        border: 1.5px solid rgba(45, 212, 191, 0.3) !important;
    }}
    .stButton button[kind="secondary"]:hover {{
        background: rgba(45, 212, 191, 0.1) !important;
        border-color: var(--color-primary) !important;
    }}

    /* ── Inputs ── */
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"],
    .stNumberInput input, .stDateInput input {{
        border-radius: var(--radius-md) !important;
        border: 1.5px solid var(--color-border) !important;
        background: rgba(255,255,255,0.03) !important;
        color: var(--color-text-primary) !important;
        transition: {TRANSITIONS['normal']} !important;
    }}
    .stTextInput input:focus, .stTextArea textarea:focus {{
        border-color: var(--color-primary) !important;
        box-shadow: 0 0 0 3px rgba(45, 212, 191, 0.15) !important;
    }}
    .stTextInput label, .stTextArea label, .stSelectbox label, .stNumberInput label {{
        color: var(--color-text-secondary) !important;
    }}

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {{
        border-bottom: 1px solid var(--color-border) !important;
        gap: 4px !important;
        background: transparent !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 8px 8px 0 0 !important;
        padding: 10px 20px !important;
        font-weight: 500 !important;
        color: var(--color-text-secondary) !important;
        border-bottom: 2px solid transparent !important;
        transition: {TRANSITIONS['normal']} !important;
        background: transparent !important;
    }}
    .stTabs [data-baseweb="tab"]:hover {{
        color: var(--color-primary) !important;
        background: rgba(45, 212, 191, 0.05) !important;
    }}
    .stTabs [aria-selected="true"] {{
        color: var(--color-primary) !important;
        border-bottom: 2px solid var(--color-primary) !important;
        font-weight: 600 !important;
    }}

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #080d17 0%, #0B1120 100%) !important;
        border-right: 1px solid var(--color-border) !important;
        min-width: 260px !important;
        max-width: 260px !important;
    }}
    section[data-testid="stSidebar"] > div {{
        overflow-y: auto !important;
        height: 100vh !important;
    }}
    section[data-testid="stSidebar"] > div > div {{
        height: auto !important;
        overflow: visible !important;
    }}
    [data-testid="stSidebarNav"] a {{
        color: var(--color-text-primary) !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        border-radius: var(--radius-md) !important;
        margin: 3px 10px !important;
        padding: 10px 14px !important;
        transition: {TRANSITIONS['normal']} !important;
        display: flex !important;
        align-items: center !important;
        gap: 12px !important;
        background: linear-gradient(90deg, rgba(45, 212, 191, 0.08) 0%, rgba(14, 165, 233, 0.04) 50%, transparent 100%) !important;
        border: 1px solid rgba(45, 212, 191, 0.08) !important;
    }}
    [data-testid="stSidebarNav"] a:hover {{
        color: var(--color-primary) !important;
        background: linear-gradient(90deg, rgba(45, 212, 191, 0.18) 0%, rgba(14, 165, 233, 0.10) 50%, rgba(15, 23, 42, 0.3) 100%) !important;
        border-color: rgba(45, 212, 191, 0.25) !important;
        transform: translateX(3px);
    }}
    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        color: #0B1120 !important;
        background: linear-gradient(135deg, var(--color-primary), var(--color-primary-dark)) !important;
        font-weight: 700 !important;
        box-shadow: var(--shadow-glow_primary);
        border-color: rgba(45, 212, 191, 0.5) !important;
    }}
    [data-testid="stSidebarNav"] .st-emotion-cache-aw5rte {{
        color: var(--color-primary) !important;
        font-weight: 700 !important;
        font-size: 0.7rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
        margin: 20px 10px 8px !important;
        opacity: 0.7;
    }}
    [data-testid="stSidebar"] h2 {{
        color: var(--color-text-primary) !important;
    }}
    [data-testid="stSidebar"] .stCaption {{
        color: var(--color-text-muted) !important;
    }}

    /* ── Cards ── */
    .ui-card {{
        background: var(--color-surface);
        background-image: linear-gradient(155deg, rgba(45,212,191,0.04) 0%, rgba(255,255,255,0.02) 30%, transparent 60%);
        border-radius: var(--radius-xl);
        border: 1px solid var(--color-border);
        box-shadow: var(--shadow-sm), inset 0 1px 0 rgba(255,255,255,0.04);
        transition: {TRANSITIONS['normal']};
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
    }}
    .ui-card-hover:hover {{
        transform: translateY(-2px);
        box-shadow: var(--shadow-md);
        border-color: var(--color-border-light);
        background: var(--color-surface-hover);
    }}
    .ui-card-elevated {{
        border: 1px solid var(--color-border);
        box-shadow: var(--shadow-md);
        background: var(--color-surface_glass);
    }}
    .ui-card-outlined {{
        background: transparent;
        border: 1.5px solid var(--color-border);
        box-shadow: none;
    }}
    .ui-card-gradient {{
        background: linear-gradient(155deg, rgba(45, 212, 191, 0.22) 0%, rgba(14, 165, 233, 0.12) 50%, rgba(15, 23, 42, 0.4) 100%);
        border: 1px solid rgba(45, 212, 191, 0.35);
        color: var(--color-text-primary);
        box-shadow: var(--shadow-glow_primary), inset 0 1px 0 rgba(255,255,255,0.08);
    }}
    .ui-card-gradient * {{
        color: var(--color-text-primary) !important;
    }}

    /* ── Badges ── */
    .ui-badge {{
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 0.25rem 0.75rem;
        border-radius: var(--radius-full);
        font-size: var(--text-xs);
        font-weight: 600;
        border: 1px solid var(--color-border);
    }}
    .ui-badge-default {{ background: rgba(255,255,255,0.03); color: var(--color-text-secondary); }}
    .ui-badge-primary {{ background: rgba(45, 212, 191, 0.15); color: var(--color-primary); border-color: rgba(45, 212, 191, 0.3); }}
    .ui-badge-success {{ background: rgba(52, 211, 153, 0.15); color: #34d399; border-color: rgba(52, 211, 153, 0.3); }}
    .ui-badge-warning {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border-color: rgba(245, 158, 11, 0.3); }}
    .ui-badge-danger {{ background: rgba(248, 113, 113, 0.15); color: #f87171; border-color: rgba(248, 113, 113, 0.3); }}
    .ui-badge-info {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); }}

    /* ── Metric Card ── */
    .ui-metric-card {{
        background: var(--color-surface);
        background-image: linear-gradient(155deg, rgba(45,212,191,0.04) 0%, rgba(255,255,255,0.02) 25%, transparent 55%);
        border-radius: var(--radius-xl);
        padding: 1.5rem;
        border: 1px solid var(--color-border);
        box-shadow: var(--shadow-sm), inset 0 1px 0 rgba(255,255,255,0.04);
        transition: {TRANSITIONS['normal']};
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
    }}
    .ui-metric-card:hover {{
        transform: translateY(-2px);
        box-shadow: var(--shadow-md), inset 0 1px 0 rgba(255,255,255,0.06);
        border-color: rgba(45, 212, 191, 0.2);
        background-image: linear-gradient(155deg, rgba(45,212,191,0.06) 0%, rgba(255,255,255,0.03) 25%, transparent 55%);
    }}
    .ui-metric-value {{
        font-size: var(--text-3xl);
        font-weight: 700;
        color: var(--color-text-primary);
        line-height: 1.2;
    }}
    .ui-metric-label {{
        font-size: var(--text-sm);
        color: var(--color-text-secondary);
        margin-top: 4px;
    }}
    .ui-metric-change {{
        font-size: var(--text-xs);
        font-weight: 600;
        margin-top: 4px;
    }}
    .ui-metric-change-up {{ color: var(--color-success); }}
    .ui-metric-change-down {{ color: var(--color-danger); }}

    /* ── Empty State ── */
    .ui-empty-state {{
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 3rem 2rem;
        text-align: center;
        color: var(--color-text-muted);
    }}
    .ui-empty-state-icon {{
        font-size: 3rem;
        margin-bottom: 1rem;
        opacity: 0.4;
    }}
    .ui-empty-state-title {{
        font-size: var(--text-lg);
        font-weight: 600;
        color: var(--color-text-secondary);
        margin-bottom: 0.5rem;
    }}
    .ui-empty-state-desc {{
        font-size: var(--text-md);
        color: var(--color-text-muted);
        max-width: 400px;
    }}

    /* ── Skeleton ── */
    @keyframes shimmer {{
        0% {{ background-position: -200% 0; }}
        100% {{ background-position: 200% 0; }}
    }}
    .ui-skeleton {{
        background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.06) 50%, rgba(255,255,255,0.03) 75%);
        background-size: 200% 100%;
        animation: shimmer 1.5s infinite;
        border-radius: var(--radius-sm);
    }}
    .ui-skeleton-line {{ height: 16px; margin-bottom: 8px; }}
    .ui-skeleton-card {{ height: 120px; border-radius: var(--radius-xl); }}

    /* ── Progress Bar ── */
    .ui-progress-container {{
        width: 100%;
        height: 8px;
        background: rgba(255,255,255,0.06);
        border-radius: var(--radius-full);
        overflow: hidden;
        margin: 8px 0;
    }}
    .ui-progress-fill {{
        height: 100%;
        background: linear-gradient(90deg, var(--color-accent_orange), var(--color-accent_gold));
        border-radius: var(--radius-full);
        transition: width 0.3s ease;
        box-shadow: var(--shadow-glow_gold);
    }}

    /* ── Table ── */
    .ui-table-row:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
    .ui-table-row:hover {{ background: rgba(255,255,255,0.04); }}

    /* ── Difficulty ── */
    .diff-simple {{ color: var(--color-success); font-weight: 600; }}
    .diff-medium {{ color: #fbbf24; font-weight: 600; }}
    .diff-hard {{ color: #fb923c; font-weight: 600; }}
    .diff-extreme {{ color: var(--color-danger); font-weight: 600; }}

    /* ── Topic Icons (Duotone Fill Style) ── */
    .topic-icon-duotone {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 3.5rem;
        height: 3.5rem;
        border-radius: var(--radius-lg);
        background: linear-gradient(135deg, rgba(45, 212, 191, 0.15) 0%, rgba(14, 165, 233, 0.08) 100%);
        border: 1.5px solid rgba(45, 212, 191, 0.2);
        box-shadow: 0 4px 12px rgba(45, 212, 191, 0.1), inset 0 1px 0 rgba(255,255,255,0.08);
        transition: {TRANSITIONS['normal']};
        margin: 0 auto 0.75rem;
    }}
    .topic-icon-duotone i {{
        font-size: 1.5rem;
        background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}
    .ui-card-gradient:hover .topic-icon-duotone {{
        transform: scale(1.1) translateY(-2px);
        box-shadow: 0 6px 20px rgba(45, 212, 191, 0.2), inset 0 1px 0 rgba(255,255,255,0.1);
        border-color: rgba(45, 212, 191, 0.4);
    }}

    /* ── Main Header ── */
    .main-header {{
        background: linear-gradient(155deg, rgba(45, 212, 191, 0.12) 0%, rgba(14, 165, 233, 0.06) 40%, rgba(15, 23, 42, 0.3) 100%);
        padding: 2rem 2rem;
        border-radius: var(--radius-xl);
        margin-top: -2rem !important;
        margin-bottom: 1.5rem;
        color: var(--color-text-primary);
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(45, 212, 191, 0.25);
        box-shadow: var(--shadow-glow_primary), inset 0 1px 0 rgba(255,255,255,0.06);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
    }}
    .main-header::before {{
        content: "";
        position: absolute;
        top: -60%;
        right: -15%;
        width: 400px;
        height: 400px;
        background: radial-gradient(circle, rgba(45, 212, 191, 0.15) 0%, transparent 65%);
        border-radius: 50%;
    }}
    .main-header::after {{
        content: "";
        position: absolute;
        bottom: -40%;
        left: -10%;
        width: 300px;
        height: 300px;
        background: radial-gradient(circle, rgba(14, 165, 233, 0.08) 0%, transparent 65%);
        border-radius: 50%;
    }}
    .main-header h1 {{
        margin: 0 0 0.5rem 0;
        font-size: var(--text-2xl);
        font-weight: 700;
        color: var(--color-text-primary);
        position: relative;
        z-index: 1;
    }}
    .main-header p {{
        margin: 0;
        font-size: var(--text-md);
        color: var(--color-text-secondary);
        position: relative;
        z-index: 1;
    }}

    /* ── Sidebar collapsed fix ── */
    @keyframes stSidebarCollapsedZero {{
        0%, 100% {{
            width: 0px !important;
            min-width: 0px !important;
            max-width: 0px !important;
            flex-basis: 0px !important;
            padding: 0px !important;
            border: none !important;
        }}
    }}

    section[data-testid="stSidebar"][aria-expanded="false"] {{
        animation: stSidebarCollapsedZero 10s infinite;
    }}

    section[data-testid="stSidebar"][aria-expanded="false"] ~ div {{
        margin-left: 0px !important;
        width: 100% !important;
        max-width: 100% !important;
    }}

    /* ── Streamlit native overrides ── */
    .stCodeBlock {{ border-radius: var(--radius-xl) !important; background: rgba(0,0,0,0.3) !important; }}
    .stAlert {{ border-radius: var(--radius-xl) !important; border: 1px solid var(--color-border) !important; background: var(--color-surface_glass) !important; backdrop-filter: blur(20px); }}
    .stDataFrame {{ border-radius: var(--radius-xl) !important; border: 1px solid var(--color-border) !important; }}
    .st-expander {{ border-radius: var(--radius-xl) !important; border: 1px solid var(--color-border) !important; background: var(--color-surface) !important; }}
    
    /* Markdown / text colors */
    .stMarkdown p {{ color: var(--color-text-secondary); }}
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{ color: var(--color-text-primary); }}
    .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {{ color: var(--color-text-secondary); }}
    
    /* Divider */
    hr {{ border-color: var(--color-border) !important; margin: 1.5rem 0; }}
    
    /* Expander header */
    .streamlit-expanderHeader {{ color: var(--color-text-primary) !important; background: transparent !important; }}
    
    /* Selectbox dropdown */
    div[data-baseweb="popover"] div {{ background: var(--color-bg_secondary) !important; color: var(--color-text-primary) !important; border: 1px solid var(--color-border) !important; }}
    div[data-baseweb="popover"] div[role="listbox"] div[role="option"] {{ color: var(--color-text-primary) !important; }}
    div[data-baseweb="popover"] div[role="listbox"] div[role="option"]:hover {{ background: rgba(45, 212, 191, 0.1) !important; }}
    
    /* Multiselect tags */
    div[data-baseweb="tag"] {{ background: rgba(45, 212, 191, 0.15) !important; color: var(--color-primary) !important; border: 1px solid rgba(45, 212, 191, 0.3) !important; }}
    
    /* Slider */
    div[data-testid="stSlider"] div[data-baseweb="slider"] div[role="slider"] {{ background: var(--color-primary) !important; border-color: var(--color-primary) !important; box-shadow: var(--shadow-glow_primary); }}
    div[data-testid="stSlider"] div[data-baseweb="slider"] div {{ background: linear-gradient(90deg, var(--color-accent_orange), var(--color-accent_gold)) !important; }}
    
    /* Checkbox / radio */
    .stCheckbox label, .stRadio label {{ color: var(--color-text-secondary) !important; }}
    .stCheckbox label span[data-baseweb="checkbox"] > div:first-child {{ background: var(--color-primary) !important; border-color: var(--color-primary) !important; }}
    
    /* Toast / success / error */
    div[data-testid="stToast"] {{ background: var(--color-surface_glass) !important; border: 1px solid var(--color-border) !important; backdrop-filter: blur(20px); color: var(--color-text-primary) !important; }}
    
    footer {{ display: none; }}
    #MainMenu {{ display: none; }}
</style>
"""
    return css


def _inject_sidebar_resizer(st_module):
    js_code = """
<script>
(function() {
    var doc = window.parent.document;
    var SIDEBAR_SELECTOR = 'section[data-testid="stSidebar"]';
    var APP_CONTAINER_SELECTOR = '[data-testid="stAppViewContainer"]';
    var intervalId = null;
    var isRunning = false;
    var TICK_MS = 80;

    function getSidebar() {
        return doc.querySelector(SIDEBAR_SELECTOR);
    }

    function getSidebarFlexItem() {
        var sb = getSidebar();
        if (!sb) return null;
        var container = doc.querySelector(APP_CONTAINER_SELECTOR);
        if (!container) return null;
        var el = sb;
        while (el && el.parentElement !== container) {
            el = el.parentElement;
            if (!el) return null;
        }
        return el;
    }

    function isCollapsed() {
        var sb = getSidebar();
        return sb && sb.getAttribute('aria-expanded') === 'false';
    }

    function forceZero(el) {
        if (!el) return;
        var props = ['width', 'min-width', 'max-width', 'flex-basis'];
        props.forEach(function(prop) {
            if (el.style.getPropertyValue(prop) !== '0px') {
                el.style.setProperty(prop, '0px', 'important');
            }
        });
    }

    function restore(el) {
        if (!el) return;
        ['width', 'min-width', 'max-width', 'flex-basis'].forEach(function(prop) {
            el.style.removeProperty(prop);
        });
    }

    function tick() {
        if (!isCollapsed()) {
            stop();
            return;
        }
        forceZero(getSidebar());
        forceZero(getSidebarFlexItem());
    }

    function start() {
        if (isRunning) return;
        isRunning = true;
        // Streamlit sidebar collapse transition is 300ms; wait a tiny
        // bit so our forced zero-width does not fight the transform.
        setTimeout(function() {
            if (!isRunning) return;
            tick();
            intervalId = setInterval(tick, TICK_MS);
        }, 50);
    }

    function stop() {
        isRunning = false;
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
        restore(getSidebar());
        restore(getSidebarFlexItem());
    }

    function onStateChange() {
        isCollapsed() ? start() : stop();
    }

    function init() {
        var sb = getSidebar();
        if (!sb) {
            setTimeout(init, 300);
            return;
        }

        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(m) {
                if (m.attributeName === 'aria-expanded') {
                    onStateChange();
                }
            });
        });
        observer.observe(sb, { attributes: true, attributeFilter: ['aria-expanded'] });

        // Also watch style mutations as a safety net.
        var styleObs = new MutationObserver(function() {
            if (isCollapsed() && isRunning) tick();
        });
        styleObs.observe(sb, { attributes: true, attributeFilter: ['style'] });

        onStateChange();
    }

    if (doc.readyState === 'loading') {
        doc.addEventListener('DOMContentLoaded', function() {
            setTimeout(init, 200);
        });
    } else {
        setTimeout(init, 200);
    }
})();
</script>
"""
    st_module.components.v1.html(js_code, height=0)


def inject_theme():
    """Inject the global CSS into the current Streamlit session."""
    import streamlit as st
    st.markdown(get_global_css(), unsafe_allow_html=True)
    _inject_sidebar_resizer(st)


