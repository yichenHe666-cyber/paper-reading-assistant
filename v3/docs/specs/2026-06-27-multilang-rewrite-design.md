# 多语言重构设计 Spec — 核动力科研牛马 v2

> 版本：2026-06-27 · 状态：待审查 · 作者：重构工作组
> 源仓库：`/workspace`（Python/FastAPI + Streamlit，v0.3.0）
> 目标：将核心系统重写为 Go + Rust + TypeScript 多语言架构，根治三大历史痛点，并引入睡眠式记忆整合与自进化能力。

---

## 1. 背景与目标

### 1.1 现状
「核动力科研牛马」是一款面向计算机科学研究者的学术论文精读工具，当前为 Python 单体：FastAPI 后端（`app/`，约 50 个服务 / 16 路由 / 20+ 数据模型）+ Streamlit 前端（`streamlit_app/`，约 20 视图）+ SQLite。功能涵盖论文库管理、AI 研究助手、阅读工作台、概念网络、Obsidian 同步、智能体对话、知识库引擎、科研记忆系统、MCP 工具、沙箱、成本追踪等。

### 1.2 必须根治的三大痛点（用户原话）
1. **多 agent 模块从未测试成功过**。
2. **前端 UI 容易乱码**。
3. **从 GitHub 同步的论文，重启电脑后全部丢失、显示为 0**。

### 1.3 重构目标
- 将核心系统重写为 **Go 后端 + Rust 高性能模块 + TypeScript 前端**，彻底摆脱"一堆脚本"形态。
- 根治上述三大痛点。
- 引入 **OpenClaw 风格睡眠式记忆整合** 与 **Hermes 风格自进化能力**。
- 交付**可直接使用的稳定软件**（Docker 一键部署），而非 localhost 开发态演示。
- 新代码与旧 Python 代码物理隔离、分类清晰；代码有详尽注释与文件头概述；产出 spec、handoff、三轮审查与测试报告、安全漏洞审查。

### 1.4 非目标（首期不做）
- 论文阅读器（PDF 阅读器，`streamlit_app/views/pdf_reader.py` 及其后端 PDF 渲染链路）首期跳过，保留旧实现不动。
- 知识库引擎、Obsidian 同步、MCP 工具服务器、沙箱、概念图谱等非核心模块首期不重写，后续阶段迁移。
- 不引入 Redis、PostgreSQL/MySQL（见 §2.3 决策）。

---

## 2. 总体架构与技术栈

### 2.1 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                        浏览器 (用户)                          │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS / 静态资源
┌───────────────────────────▼──────────────────────────────────┐
│            前端  v2/frontend  (Vite + React + TS + Tailwind)   │
│   独立 SPA；构建产物由 Go 后端内嵌托管，或 nginx 容器托管       │
└───────────────────────────┬──────────────────────────────────┘
                            │ REST + SSE (显式 UTF-8)
┌───────────────────────────▼──────────────────────────────────┐
│             后端  v2/backend  (Go · 单二进制)                  │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────────┐ │
│  │ HTTP/API │ Agent    │ 记忆编排 │ 论文/主题 │ LLM 适配层    │ │
│  │ 路由层   │ Engine   │ (调用    │ 持久化   │ (Provider    │ │
│  │          │ (loop)   │  Rust)   │ (SQLite) │  能力矩阵)   │ │
│  └──────────┴──────────┴────┬─────┴──────────┴──────────────┘ │
│                              │ HTTP (localhost 内网)           │
└──────────────────────────────┼────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│        核心服务  v2/core  (Rust · 独立 HTTP 微服务)             │
│   向量化 / 记忆引擎 / 睡眠式记忆整合(Dreaming) / 相似度检索    │
└──────────────────────────────┬────────────────────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │   SQLite (WAL) + 数据卷      │
                │   路径绝对化，Docker 卷持久化 │
                └─────────────────────────────┘
```

### 2.2 技术选型
| 层 | 技术 | 说明 |
|---|---|---|
| 前端 | TypeScript + Vite + React + Tailwind CSS | 轻量 SPA，配 Go API 最自然；本地图标 `lucide-react`；显式 CJK 字体栈 |
| 后端 | Go (Gin) | 单二进制，内嵌前端静态资源；agent loop / API / 业务 / LLM 适配 |
| 核心服务 | Rust (axum) | 独立 HTTP 微服务：向量化、记忆引擎、睡眠整合；Go 通过 HTTP 调用 |
| 数据库 | SQLite (WAL 模式) | 路径绝对化 + Docker 卷持久化；首期不引入 Postgres/MySQL |
| 缓存 | Go 进程内 LRU + SQLite 持久化缓存 | 首期不引入 Redis；预留接口 |
| LLM | Ollama + DeepSeek v4 flash/pro | Provider 能力矩阵适配，按模型开关参数 |
| 部署 | Docker + docker-compose | 一键编排，面向新手提供部署文档 |

### 2.3 关键决策与理由
- **SQL 选 SQLite 而非 Postgres/MySQL**：痛点③根因是相对路径漂移（见 §4.2），将路径绝对化 + Docker 卷持久化即可根治；SQLite 零运维、单文件、易备份，最适合单机科研工具。Postgres/MySQL 对单机新手过重，需额外运维一个 DB 服务。
- **Redis 首期不上**：当前缓存需求（LLM 响应缓存、会话）用 Go 进程内 LRU + SQLite 持久化即可满足；单机没必要多跑 Redis。预留缓存接口，未来多实例再引入。
- **Rust 以独立 HTTP 服务而非 FFI 集成**：首期仅向量化/记忆引擎用 Rust，独立服务可独立构建/测试/部署，Go 通过 HTTP 调用，复杂度最低。FFI（cgo）性能最佳但跨平台构建复杂，首期不选。
- **新代码独立目录 `v2/`**：与现有 `app/`、`streamlit_app/` 物理隔离，避免与旧 Python 混杂；按 `backend/core/frontend/docs/deploy` 分类。

---

## 3. 目录结构

所有新代码置于 `v2/`，与旧 Python 代码完全分离。

```
/workspace/
├── app/                      # 旧 Python 后端（保留，不动）
├── streamlit_app/            # 旧 Streamlit 前端（保留，不动）
└── v2/                       # 新重写代码（独立目录）
    ├── backend/              # Go 后端
    │   ├── cmd/              # 入口 main.go
    │   ├── internal/
    │   │   ├── api/          # HTTP 路由与处理器
    │   │   ├── agent/        # agent loop / 技能 / 函数调用
    │   │   ├── llm/          # LLM provider 适配层 + 能力矩阵
    │   │   ├── memory/       # 记忆编排（调用 Rust core）
    │   │   ├── paper/        # 论文/主题同步与持久化
    │   │   ├── store/        # SQLite 存储层（路径绝对化）
    │   │   ├── config/       # 配置加载与校验
    │   │   └── cache/        # 进程内 LRU + 持久化缓存
    │   ├── go.mod
    │   └── Dockerfile
    ├── core/                 # Rust 高性能核心服务
    │   ├── src/
    │   │   ├── vector/       # 向量化
    │   │   ├── memory/       # 记忆引擎
    │   │   ├── dreaming/     # 睡眠式记忆整合（三阶段）
    │   │   └── http/         # axum HTTP 接口
    │   ├── Cargo.toml
    │   └── Dockerfile
    ├── frontend/             # TS 前端
    │   ├── src/
    │   │   ├── pages/        # 页面视图
    │   │   ├── components/   # 复用组件
    │   │   ├── api/          # API 客户端（显式 UTF-8）
    │   │   ├── stores/       # 状态管理（Zustand）
    │   │   └── styles/       # Tailwind + CJK 字体栈
    │   ├── package.json
    │   └── Dockerfile
    ├── docs/                 # 文档
    │   ├── specs/            # 本 spec 及后续设计文档
    │   ├── handoff.md        # 项目交接文档（交给下一个 AI）
    │   ├── docker-deploy.md  # Docker 部署指南（新手向）
    │   └── reviews/          # 三轮审查与测试报告、安全审查报告
    ├── deploy/               # 部署配置
    │   ├── docker-compose.yml
    │   └── .env.example
    └── scripts/              # 构建/迁移辅助脚本
```

---

## 4. 三大痛点：根因与修复方案

### 4.1 多 agent 模块从未成功

**根因（按致命度排序，均已在前置调研中定位到文件:行号）：**

1. **首要根因——强制注入非法 LLM 参数**：`app/services/llm_utils.py:18-25` 的 `_build_reasoning_kwargs` 对每次请求强制注入 `reasoning_effort="max"` 与 `extra_body.thinking.type="enabled"`。DeepSeek `deepseek-chat` 不支持这两个字段 → 400/422；且 `"max"` 甚至不是 OpenAI o 系列合法取值（合法为 `minimal/low/medium/high`）。该 kwargs 在 `_call_llm`/`_call_llm_stream`/`_call_llm_with_tools` 三处全部生效，没有任何一次 LLM 调用能绕过。
2. **流式在 auto 模式必崩**：`app/routes/chat.py:141-161` 的 SSE 端点把 `send_message(stream=True)` 当生成器迭代，但 auto 模式下 `chat_engine.py:44` 返回的是 dict（`_send_with_tools` 未实现流式），`for chunk in dict` 把字典 key（`message_id`/`content`/...）当 token 吐给前端。
3. **流式无异常处理**：`chat_engine.py:120-153` 的 `_send_stream` 无 try/except，LLM 中途失败则 SSE 断开、assistant 消息不落库。
4. **API key 默认空 + provider key 未文档化**：`config.py:15` 默认空；`llm_utils.py:259-284` 切非默认 provider 需 `XXX_API_KEY` 环境变量，`.env.example` 未列出 → 401。
5. **技能注册幂等性陷阱**：`init_db.py:134-144` 仅当 `skills` 表完全为空才注册内置技能，表里有一条非内置记录就永不注册 → `tools` 为空 → 技能路由形同虚设。
6. **无 agent loop**：`_send_with_tools` 仅"一次工具调用 + 一次最终回答"，无 `max_turns` 循环，无法多步推理。
7. **reasoning 模型空内容误判**：`llm_utils.py:59-63` 只判 `content` 为空即重试至失败，忽略 `reasoning_content`。
8. **零测试覆盖**：`tests/` 无任何 chat/skill/llm 用例。

**修复方案（Go 重写）：**

- **Provider 能力矩阵**：在 `backend/internal/llm` 建表驱动的 `ModelCapabilities`，按 provider/model 决定是否下发 `reasoning_effort`/`thinking` 等参数，并校验取值合法。Ollama / DeepSeek v4 flash/pro 各自登记能力。这是根治 400 的核心。
- **真正 agent loop**：`backend/internal/agent` 实现 `for turn < maxTurns { callWithTools; if noToolCalls { break }; execute; append }`，每轮带超时与 token 预算检查；`maxTurns` 可配（默认 8）。
- **流式统一抽象**：`send_message` 统一返回 `<-chan StreamEvent`（Go channel），事件类型含 `token`/`tool_call`/`tool_result`/`usage`/`error`/`done`；auto/normal/stream 三种路径返回类型一致，杜绝"dict 当生成器"。
- **流式异常落库**：流式路径 `defer recover` + error 事件，保证中途失败也落库或至少发 SSE `error`。
- **启动配置校验**：启动时校验 `LLM_API_KEY` 非空、provider preset 与 env key 对应关系；缺失则 fail-fast 并给出明确指引，而非运行时 401。
- **技能注册 upsert**：以 `slug` 维度 upsert，取代"整表为空才注册"。
- **契约测试先行**：用 mock LLM server（固定 JSON 响应）覆盖 normal / stream / with_tools / empty_content / bad_json 五条路径，作为重构前置门槛。
- **DeepSeek/Ollama 兼容**：工具调用走 OpenAI function calling 协议（DeepSeek 兼容）；Ollama 走其 native 工具协议或 OpenAI 兼容端点；按能力矩阵切换。

### 4.2 论文重启后丢失（显示为 0）

**根因：** 数据库路径为相对路径 `data/reading_assistant.db`（`app/config.py:7`），引擎在 import 期按相对路径构建（`app/database/session.py:5,10-11`），SQLite 按进程 cwd 解析。开机自启/快捷方式/IDE 运行时 cwd 一变，就打开一个全新空库，旧数据被孤立在另一个绝对路径下（PDF 同理落在相对目录）。已排除"init_db 删表""内存库""漏 commit""临时目录被清理"等嫌疑——纯属路径漂移。加重因素：`session.py:8` 会在任意 cwd 下创建 `data/` 并新建空库；设置页可改 DB 路径且无绝对化。

**修复方案（Go 重写）：**

- **路径绝对化**：`backend/internal/store` 与 `config` 在使用前将所有相对路径解析为绝对路径——基准为"可执行文件所在目录"或用户数据目录（如 `~/.nuclear-research-ox/`），不再依赖 cwd。
- **集中数据目录**：数据库、PDF、备份、日志统一置于该绝对数据目录下，启动时打印实际路径便于排查。
- **孤立数据迁移**：首次启动检测旧 Python 版本的孤立库（扫描常见 cwd 下的 `data/reading_assistant.db`），提示并支持一键导入，找回历史论文。
- **Docker 卷持久化**：数据目录挂载为 Docker 命名卷，容器重建不丢数据。
- **启动自检**：启动时校验数据目录可写、库文件可打开、论文计数 > 0 时与文件对账，异常告警。

### 4.3 前端 UI 乱码

**根因：** ①无 CJK 字体栈（`streamlit_app/assets/custom_theme.py:95` 仅拉丁字体）；②Font Awesome / Google Fonts 走 CDN，被墙或离线变方框；③84 处 `unsafe_allow_html=True` HTML 字符串拼接，转义不一致（badge/card/metric_card 完全不转义）；④assistant 的 Markdown 被 `html.escape` 成纯文本（`agent_chat.py:533,551,555`），用户看到字面量 `**加粗**`；⑤`badge()` 返回值被丢弃导致静默不显示；⑥`<script>` 注入与 CSS Hack 强耦合 Streamlit 内部 DOM；⑦API 编码隐式依赖 requests 探测，`resp.text` 可能 ISO-8859-1 真乱码。

**修复方案（TS 重写）：**

- **显式 CJK 字体栈**：全局 `font-family` 含 `"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans CN", sans-serif`。
- **本地图标库**：用 `lucide-react`（本地打包），杜绝运行时 CDN 依赖；emoji 谨慎使用或确保环境装 `noto-color-emoji`。
- **React 组件自动转义**：所有文本走 JSX `{variable}`，禁止 `dangerouslySetInnerHTML`；在组件 props 入口统一转义，避免遗漏/双重转义。
- **assistant Markdown 正确渲染**：user 消息纯文本，assistant 消息用 `react-markdown` + 受控 `rehype-raw` + 白名单 sanitize 渲染。
- **显式 UTF-8 API**：`fetch` 请求/响应显式 `Content-Type: application/json; charset=utf-8`，响应一律 `.json()`，错误信息走结构化 JSON 而非 `text[:200]`。
- **URL + 状态库导航**：用 query/path params + Zustand 集中管理导航状态，刷新可恢复，取代散落的 `session_state`。
- **杜绝脚本注入**：用原生 React 事件/状态实现交互，不依赖框架内部类名。

---

## 5. 记忆系统设计（OpenClaw 风格睡眠式整合）

借鉴 OpenClaw Dreaming（v2026.4.5）与五层记忆架构，在 Rust `core` 中实现。

### 5.1 五层记忆
| 层 | 存储 | 用途 | 生命周期 |
|---|---|---|---|
| 工作记忆 | 进程内（Go 侧上下文窗口） | 当前对话上下文 | 会话级 |
| 情景记忆 | SQLite + 向量 | 交互事件/经历 | 永久 |
| 长期记忆 | SQLite + 向量（MEMORY 等价表） | 事实/决策/人物/里程碑 | 永久 |
| 程序记忆 | SQLite（技能表） | 工作流/偏好/工具模式 | 永久 |
| 索引记忆 | SQLite（元数据/重要性分数/关系） | 检索与健康统计 | 永久 |

### 5.2 睡眠式记忆整合（Dreaming）
后台定时或手动触发，三阶段顺序执行（Light → REM → Deep）：

- **Light Sleep（浅睡）**：扫描近期短期记忆，Jaccard 相似度去重（阈值 0.9），暂存候选并记录强化信号。不写长期记忆。
- **REM Sleep**：回溯窗口内分析概念标签频率，提取主题，识别"候选真理"。不写长期记忆。
- **Deep Sleep（深睡）**：对候选按六信号加权评分——相关性 0.30 / 频率 0.24 / 查询多样性 0.15 / 时效性 0.15 / 整合度 0.10 / 概念丰富度 0.06——叠加 Light/REM 强化加成；候选须同时满足三阈值门槛才升级为长期记忆。**仅此阶段写入长期记忆**，确保噪音不污染。

### 5.3 可配置参数
- `recencyHalfLifeDays`：时效性半衰期，控制记忆衰减速度。
- `maxAgeDays`：超龄记忆不再 eligible 升级。
- `dreamIntervalHours`：自动梦境间隔（默认 24h，可手动 `/dream` 触发）。

### 5.4 Dream Diary
每次梦境产出可视化日志：审查了哪些记忆、哪些升级、哪些衰减、新建了哪些关联。前端提供页面查看，便于调试"为何忘记"。

### 5.5 Decision Ledger（决策账本）
结构化记录每个重大决策（日期、背景、理由、结果）。agent 遇到相似问题时先查账本，避免重复争论、防止 flip-flopping，沉淀"机构知识"。

### 5.6 与现有 Python 记忆模块的关系
旧 `memory_engine/memory_vectorizer/memory_reflector/memory_observer/memory_distiller` 的职责在 Rust `core` 中重新划分：vectorizer→`vector/`、reflector/observer/distiller→`dreaming/` 各阶段、engine→`memory/` 编排。Go 侧 `backend/internal/memory` 仅做编排与 HTTP 调用。

---

## 6. 自进化能力设计（Hermes 风格 GEPA 闭环）

借鉴 Hermes Agent（Nous Research）的闭环学习与 GEPA 自优化。

### 6.1 闭环学习循环
`Observe → Plan → Act → Learn`：
- 完成复杂任务后，agent 评估"什么有效、什么无效"。
- 将可复用方案提炼为**技能文件**（项目已有 skill 系统，正好增强），遵循开放格式（含上下文、步骤、结果、示例）。
- 技能在后续使用中持续改进；相似任务来时先检索相关技能复用，降低 token 与成本。

### 6.2 触发节奏
每约 N 次工具调用（默认 15）暂停评估会话，判断是否值得沉淀技能；也可手动触发。

### 6.3 GEPA 式 prompt 自优化
引入轻量 GEPA 风格优化：以"类反向传播"方式对 prompt/技能做少量评估（目标 100–500 次即收敛，远低于传统 RL），按效果反馈调整。首期实现"技能效果评估 + 增量改进"的最小闭环，不追求完整 GEPA 实现。

### 6.4 技能渐进式披露
- Level 0：概要（约 3000 tokens）注入提示。
- Level 1：完整内容按需加载。
- Level 2：深入参考材料。
按需加载相关技能，避免 prompt 膨胀。

### 6.5 安全缰绳
自进化不脱离人工控制：技能变更需可审查/可回滚；危险操作走指令审批；prompt 注入安全扫描；凭证不进技能文件。

---

## 7. 数据模型与 API 契约（首期）

首期重写覆盖的领域：会话/消息、技能、论文/主题、记忆（最小）、LLM 配置、系统健康。

### 7.1 关键表（SQLite，迁移自旧库并绝对化）
- `papers`、`topics`：迁移自旧库（含孤立数据找回）。
- `chat_sessions`、`chat_messages`：会话与消息（含 `reasoning_content`/`token_count`/`context_usage_pct`）。
- `skills`：技能（slug 唯一，upsert；含自进化字段：`usage_count`/`success_rate`/`level`/`version`/`last_improved_at`）。
- `memories`：记忆（含 `layer`/`importance_score`/`decay_state`/`embedding_id`）。
- `decision_ledger`：决策账本。
- `llm_calls`/`cost_logs`：LLM 调用与成本（迁移自旧库）。
- `llm_cache`：LLM 响应缓存（持久化）。

### 7.2 关键 API（REST + SSE，显式 UTF-8）
- `POST /api/chat/sessions`、`GET /api/chat/sessions/{id}`、`GET /api/chat/sessions/{id}/messages`
- `POST /api/chat/sessions/{id}/messages`（非流式）
- `POST /api/chat/sessions/{id}/messages/stream`（SSE，统一 StreamEvent）
- `GET/POST /api/skills`、`POST /api/skills/{slug}/evolve`（手动触发自进化）
- `GET /api/papers`、`POST /api/topics/fetch`（同步）、`POST /api/papers/migrate-legacy`（孤立数据导入）
- `POST /api/memory/dream`（手动触发梦境）、`GET /api/memory/dream-diary`
- `GET /api/system/health`（含数据目录、库可写性、论文计数自检）

> 完整字段与状态码在实现计划阶段细化为 OpenAPI。

---

## 8. LLM Provider 适配

- **支持**：Ollama（本地）、DeepSeek v4 flash、DeepSeek v4 pro，及任意 OpenAI 兼容端点。
- **能力矩阵**：登记每个 provider/model 是否支持 `tools`/`reasoning_effort`/`thinking`/流式，及 `reasoning_effort` 合法取值。
- **参数下发**：仅对支持者下发对应参数，并校验取值；DeepSeek chat 不下发 `reasoning_effort`/`thinking`。
- **启动校验**：配置的 provider 缺 key 时 fail-fast 并指引。
- **成本追踪**：沿用旧 `cost_tracker` 思路，按调用记录 token/成本，支持日预算上限。

---

## 9. 里程碑与范围

| 里程碑 | 内容 | 验收 |
|---|---|---|
| **M1** | Go 后端骨架 + 配置/路径绝对化 + SQLite 存储层 + 论文/主题同步与持久化 + LLM 适配层（能力矩阵）+ 契约测试框架 | 论文同步后重启（含模拟 cwd 变化）不丢；DeepSeek/Ollama 可发通；mock LLM 五路径测试通过 |
| **M2** | agent loop + 流式统一 channel + 技能 upsert + 自进化技能雏形（任务后提炼/复用） | 真实 DeepSeek/Ollama 下多轮工具调用成功；流式不崩；技能可沉淀复用 |
| **M3** | TS 前端框架 + 核心页面（对话/论文/主题/设置）+ UI 乱码根治 | CJK 字体正常、无方框、assistant Markdown 正确渲染、刷新状态不丢 |
| **M4** | Rust core：向量化 + 记忆引擎 + 睡眠式整合（三阶段）+ Dream Diary + Decision Ledger | 梦境可触发、长期记忆按评分升级、Dream Diary 可查 |
| **M5** | 三轮代码审查 + 测试报告 + 安全漏洞审查 + handoff 文档 + Docker 部署文档 + 稳定性打磨 | 三轮审查报告归档；关键路径测试通过；安全审查无高危；Docker 一键起；交付可运行软件 |

论文阅读器（PDF）首期跳过。

---

## 10. 工程规范

### 10.1 注释与文件头
- **每个源文件开头**必须有内容概述注释：说明该文件职责、关键类型/函数、依赖关系。
- **代码行注释**详细：复杂逻辑、业务规则、踩坑点、与旧实现的差异均需注释。
- Go/Rust/TS 各自遵循本语言注释惯例（Go 包注释、Rust 模块文档、TSDoc）。

### 10.2 文档产出
- `docs/specs/`：本 spec 及后续设计文档。
- `docs/handoff.md`：项目交接文档——架构总览、目录说明、各模块职责、构建与运行、数据流、已知问题与后续计划，便于交给下一个 AI。
- `docs/docker-deploy.md`：面向 Docker 新手的部署指南。
- `docs/reviews/`：三轮代码审查报告、测试报告、安全审查报告。

### 10.3 代码审查与测试（三轮）
- 第 1 轮：构建与契约——能否构建、契约测试是否覆盖五路径、路径绝对化是否生效。
- 第 2 轮：功能与稳定性——端到端关键流程（同步/对话/记忆）、异常与边界、流式中断落库。
- 第 3 轮：安全与可维护性——注入/路径遍历/凭证/依赖漏洞、注释完整性、命名与结构。
- 每轮产出报告（问题清单 + 修复确认），归档 `docs/reviews/`。

### 10.4 安全防护与漏洞审查
- 输入校验与转义、SQL 参数化、路径遍历防护、SSRF 缓解（GitHub/PDF 抓取）、凭证管理（key 不入日志/不入技能文件）、Docker 容器最小权限。
- 最终产出安全审查报告，列出发现与修复。

---

## 11. 稳定性与交付要求

> 用户明确要求：**系统稳定性搞好点，不要用 localhost 开发态敷衍，直接上可用的软件。**

- **交付形态**：Docker 一键部署的可运行软件，而非仅 `go run` / `npm run dev` 的开发态。
- **稳定性门槛**：关键流程（论文同步、对话、记忆）在真实 DeepSeek/Ollama 下端到端跑通；重启/容器重建不丢数据；流式中断可恢复或明确报错。
- **可观测**：启动打印实际数据目录、库路径、provider 状态；健康检查接口；错误信息可读且中文友好。
- **降级**：LLM 不可用时，论文浏览/搜索等非 AI 功能仍可用（沿用旧版理念）。

---

## 12. Docker 部署

### 12.1 编排
`deploy/docker-compose.yml` 编排三服务：
- `backend`（Go，内嵌前端静态资源，暴露端口）
- `core`（Rust，仅内网暴露给 backend）
- 数据卷（SQLite + PDF + 备份 + 日志，命名卷持久化）

### 12.2 新手部署文档
`docs/docker-deploy.md` 面向未用过 Docker 的用户，包含：装 Docker Desktop/Engine 步骤、`.env` 配置（LLM key、Ollama 地址）、`docker compose up -d` 启动、访问地址、数据在哪/怎么备份恢复、常见问题排查。

---

## 13. 风险与对策

| 风险 | 对策 |
|---|---|
| 范围过大无法一次完成 | 严格按 M1–M5 分阶段；每里程碑独立可验收 |
| DeepSeek/Ollama 工具协议差异 | Provider 能力矩阵 + 契约测试先行 |
| Rust 服务增加部署复杂度 | 独立服务但同机 Docker 编排；首期仅向量化/记忆 |
| 自进化失控/技能污染 | 人工审查 + 回滚 + 注入扫描 |
| 旧孤立数据找回失败 | 启动扫描 + 手动导入接口 + 文档指引 |

---

## 14. 待决（实现计划阶段细化）
- OpenAPI 完整字段与状态码。
- Rust core 与 backend 的 HTTP 契约（请求/响应 schema）。
- 自进化"效果评估"的具体指标与闭环判定。
- 前端页面完整清单与交互稿（M3 前细化）。

---

## 附录 A：调研来源
- OpenClaw Dreaming（睡眠式记忆整合三阶段、六信号评分、五层记忆、Decision Ledger）。
- Hermes Agent / GEPA（闭环学习、自进化技能、prompt 自优化、渐进式披露）。
- 三大痛点根因均定位至现有 Python 代码文件:行号（见 §4）。
