# 📖 核动力科研牛马

> Papers We Love | AI 导航 | Obsidian 笔记联动

一款面向计算机科学研究者的**学术论文精读工具**，集成 AI 深度研究、Obsidian 笔记同步、概念网络可视化等功能，帮助你系统性地阅读、理解和关联学术论文。

---

## ✨ 核心功能

### 📚 论文库管理
- 一键同步 [Papers We Love](https://github.com/papers-we-love/papers-we-love) 仓库的经典论文
- 按主题分类浏览，支持全文搜索
- 论文元数据自动解析（标题、作者、年份、摘要）

### 🤖 AI 研究助手
- 基于 GPT Researcher 的自主深度研究引擎
- 支持快速摘要 / 深度分析 / 资源报告等多种模式
- 自动搜索多个来源，生成带引用的研究报告
- 可关联特定论文，获取针对性研究背景

### 📖 阅读工作台
- 四阶段精读流程：预读 → 结构拆解 → 深度精读 → 批判审视
- AI 辅助生成论文摘要、结构分析、概念解释
- 阅读笔记自动保存，支持快照对比

### 🧠 概念网络
- 自动提取论文中的核心概念
- 构建概念之间的关系图谱
- 可视化展示知识关联

### 📝 Obsidian 笔记同步
- 双向同步论文笔记到 Obsidian Vault
- 自动生成 Markdown 格式的概念卡片
- 专业词汇表导出

### 📊 阅读统计
- 阅读进度追踪（未读 / 精读中 / 已读 / 重读）
- LLM 调用成本监控
- 主题分布统计

---

## 🏗️ 项目架构

```
openclaw002/
├── app/                          # FastAPI 后端
│   ├── config.py                 # 配置管理 (pydantic-settings)
│   ├── main.py                   # FastAPI 应用入口
│   ├── database/                 # 数据库层 (SQLAlchemy + SQLite)
│   ├── models/                   # 数据模型
│   ├── routes/                   # API 路由
│   │   ├── papers.py             # 论文管理
│   │   ├── reading.py            # 阅读记录
│   │   ├── research.py           # AI 研究
│   │   ├── obsidian.py           # Obsidian 同步
│   │   ├── recommend.py          # 智能推荐
│   │   ├── topics.py             # 主题分类
│   │   ├── wiki.py               # 概念百科
│   │   └── system.py             # 系统状态
│   ├── services/                 # 业务逻辑层
│   │   ├── llm_service_base.py   # LLM 服务基类
│   │   ├── llm_navigator.py      # AI 导航
│   │   ├── llm_drafter.py        # AI 起草
│   │   ├── llm_concept_mapper.py # 概念映射
│   │   ├── llm_vocabulary.py     # 词汇提取
│   │   ├── research_service.py   # 研究服务
│   │   ├── obsidian_writer.py    # Obsidian 写入
│   │   ├── github_fetcher.py     # GitHub 数据源
│   │   ├── paper_parser.py       # 论文解析
│   │   ├── paper_recommender.py  # 论文推荐
│   │   ├── cost_tracker.py       # 成本追踪
│   │   └── ...                   # 更多服务
│   └── tools/
│       └── mcp_server.py         # MCP 工具服务器
│
├── streamlit_app/                # Streamlit 前端
│   ├── main.py                   # 应用入口 & 导航
│   ├── assets/
│   │   └── custom_theme.py       # 自定义主题
│   ├── components/               # UI 组件
│   │   ├── card.py               # 卡片组件
│   │   ├── badge.py              # 徽章组件
│   │   ├── icon.py               # 图标组件
│   │   ├── metric_card.py        # 指标卡片
│   │   └── empty_state.py        # 空状态占位
│   ├── views/                    # 页面视图
│   │   ├── home_content.py       # 首页
│   │   ├── reading_workbench.py  # 阅读工作台
│   │   ├── research_assistant.py # AI 研究助手
│   │   ├── concept_graph.py      # 概念网络
│   │   ├── obsidian_panel.py     # Obsidian 面板
│   │   ├── recommend.py          # 智能推荐
│   │   ├── stats.py              # 阅读统计
│   │   ├── settings.py           # 系统设置
│   │   └── ...                   # 更多页面
│   └── utils/
│       └── api_client.py         # 后端 API 客户端
│
├── start_app.py                  # 一键启动脚本
├── .env.example                  # 环境变量模板
└── .gitignore
```

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- pip

### 安装与启动

1. **克隆仓库**

```bash
git clone https://github.com/YOUR_USERNAME/openclaw002.git
cd openclaw002
```

2. **创建虚拟环境**

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

3. **配置环境变量**

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 LLM API Key：

```ini
# 必填：LLM 配置 (支持 OpenAI 兼容接口)
LLM_API_KEY=sk-your-key-here

# 可选：使用 DeepSeek 等其他 OpenAI 兼容服务
LLM_PROVIDER=DeepSeek
LLM_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

> 💡 没有 API Key 也可以启动，论文浏览和搜索功能不受影响，仅 AI 功能需要 LLM。

4. **一键启动**

```bash
python start_app.py
```

脚本会自动：
- 安装 Python 依赖
- 启动 FastAPI 后端（端口 8000）
- 启动 Streamlit 前端（端口 8501）
- 打开浏览器

5. **开始使用**

首次使用请点击首页的「同步论文库」按钮，从 Papers We Love 仓库拉取论文数据。

---

## ⚙️ 配置说明

### LLM 配置

本项目支持任何 OpenAI 兼容的 API 接口：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LLM_PROVIDER` | DeepSeek | LLM 提供商名称 |
| `LLM_API_BASE` | https://api.deepseek.com/v1 | API 基础地址 |
| `LLM_API_KEY` | - | API 密钥（必填） |
| `LLM_MODEL` | deepseek-chat | 模型名称 |
| `LLM_MAX_TOKENS` | 4096 | 最大 token 数 |
| `LLM_TEMPERATURE` | 0.3 | 生成温度 |
| `DAILY_LLM_BUDGET_USD` | 3.0 | 每日 LLM 预算上限（美元） |

### Obsidian 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `OBSIDIAN_VAULT_PATH` | C:\Users\Public\Documents | Obsidian Vault 路径 |

### 数据源配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEFAULT_GITHUB_REPO` | papers-we-love/papers-we-love | 论文数据源仓库 |

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Streamlit |
| **后端** | FastAPI + Uvicorn |
| **数据库** | SQLite (SQLAlchemy ORM) |
| **LLM** | OpenAI API (兼容接口) |
| **AI 研究** | GPT Researcher |
| **笔记同步** | Obsidian Markdown |
| **数据源** | GitHub (Papers We Love) |

---

## 📋 API 文档

启动后端后，访问以下地址查看自动生成的 API 文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 📄 License

MIT License

---

## 🙏 致谢

- [Papers We Love](https://github.com/papers-we-love/papers-we-love) - 优质学术论文集合
- [GPT Researcher](https://github.com/assafelovic/gpt-researcher) - AI 研究引擎
- [FastAPI](https://fastapi.tiangolo.com/) - 高性能 Web 框架
- [Streamlit](https://streamlit.io/) - 数据应用框架
