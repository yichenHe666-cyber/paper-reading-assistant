<!--
文件概述：核动力科研牛马 v2 项目交接文档（handoff）。
面向"接手维护的下一个开发者"，目标是让其在不读全部源码的前提下快速上手：
  - 理解项目定位、三大痛点修复状态与当前完成里程碑；
  - 掌握 Go / Rust / TypeScript 三层架构与数据流；
  - 能在本地搭建开发环境、跑测试、一键 Docker 部署；
  - 清楚每个核心模块的职责与关键实现位置；
  - 知道数据库表清单、Go/Rust 共享 SQLite 的注意事项；
  - 明确已知限制与后续待办（按优先级排序）；
  - 理解关键设计决策的取舍理由。

关联文档：
  - 设计 spec：`v2/docs/specs/2026-06-27-multilang-rewrite-design.md`
  - 实现计划：`v2/docs/plans/implementation-plan.md`
  - 部署指南（新手向，待补）：`v2/docs/docker-deploy.md`
  - 审查报告（待归档）：`v2/docs/reviews/`

阅读建议：先读第 1-3 章建立全局认知，再按需查阅第 5 章模块细节；接手第一件事建议
按第 4 章搭好本地环境并跑通第 7 章的测试，确认基线绿后再动业务代码。
-->

# 核动力科研牛马 v2 — 项目交接文档

> 版本：2026-06-27 · 维护者：重构工作组 → 接手开发者
> 源仓库：`/workspace`（Python/FastAPI + Streamlit，v0.3.0，保留不动）
> 新代码根目录：`/workspace/v2/`

---

## 1. 项目概述

### 1.1 一句话定位
「核动力科研牛马 v2」是一款面向计算机科学研究者的**学术论文精读工具**，本仓库为其多语言重构版——将原 Python 单体重写为 **Go 后端 + Rust 核心服务 + TypeScript 前端**，并引入睡眠式记忆整合与自进化能力，交付 Docker 一键部署的可运行软件。

### 1.2 三大痛点修复状态
原 v0.3.0 用户反馈的三个致命痛点，在 v2 中的修复状态如下：

| 痛点 | 原根因（v0.3.0） | v2 修复方案 | 修复层 | 状态 |
|---|---|---|---|---|
| ① 多 agent 模块从未成功 | `llm_utils.py` 强制注入 `reasoning_effort="max"` 致 400；流式把 dict 当生成器；无 agent loop；零测试 | Provider 能力矩阵 + 真 agent loop + 统一 `StreamEvent` channel + 契约测试 | Go `internal/llm`、`internal/agent` | 已修复 |
| ② 论文重启后丢失（显示为 0） | 数据库路径为相对路径 `data/reading_assistant.db`，按 cwd 解析，cwd 一变即开空库 | 路径绝对化（`config.go` `resolvePaths`）+ 集中数据目录 + Docker 命名卷持久化 | Go `internal/config`、`internal/store`、`deploy/` | 已修复 |
| ③ 前端 UI 乱码 | 无 CJK 字体栈；CDN 字体被墙；84 处 `unsafe_allow_html` 转义不一致；assistant Markdown 被 `html.escape` 成纯文本 | 显式 CJK 字体栈 + 本地图标 `lucide-react` + `react-markdown` 受控渲染 + 显式 UTF-8 API | `frontend/src/` | 已修复 |

### 1.3 当前完成里程碑（M1-M5）
按实现计划分五个里程碑推进，当前代码层面均已落地：

| 里程碑 | 内容 | 代码位置 | 验收状态 |
|---|---|---|---|
| **M1** | Go 骨架 + 路径绝对化 + SQLite 存储层 + 论文/主题同步 + LLM 适配（能力矩阵）+ 契约测试 | `backend/internal/{config,store,paper,llm}` | 代码完成 |
| **M2** | agent loop + 流式统一 channel + 技能 upsert + 自进化雏形 | `backend/internal/agent` | 代码完成 |
| **M3** | TS 前端框架 + 核心页面 + UI 乱码根治 | `frontend/src/{pages,components,api,stores}` | 代码完成 |
| **M4** | Rust core：向量化 + 记忆引擎 + 睡眠整合三阶段 + Dream Diary + Decision Ledger | `core/src/{vector,memory,dreaming,http,db}` | 代码完成 |
| **M5** | 三轮审查 + 测试报告 + 安全审查 + handoff + Docker 部署 + 稳定性打磨 | `deploy/`、`docs/` | **部分完成**：Docker 编排与 handoff 已就绪；三轮审查报告与安全审查报告**尚未归档**（见 §9） |

> 说明：M5 的代码与部署交付已就绪，但 spec §10.3 要求的三轮审查报告、安全审查报告尚未在 `docs/reviews/` 落地——这是接手者需优先补齐的工程治理项（见 §9 待办 P0）。

---

## 2. 架构总览

### 2.1 三层职责
| 层 | 语言 / 框架 | 职责 | 入口 |
|---|---|---|---|
| 前端 `v2/frontend` | TypeScript + Vite + React 18 + Tailwind 3 | SPA 用户界面；显式 UTF-8 API 客户端；SSE 流式渲染；assistant Markdown 受控渲染 | `frontend/src/main.tsx` |
| 后端 `v2/backend` | Go 1.25 + Gin | 单二进制 HTTP 服务；agent loop；LLM 适配（能力矩阵）；论文/主题持久化；记忆编排（代理 Rust core）；技能与自进化；成本与缓存 | `backend/cmd/api/main.go` |
| 核心服务 `v2/core` | Rust（edition 2021）+ axum 0.7 | 独立 HTTP 微服务：向量化、五层记忆引擎、睡眠式整合三阶段、Dream Diary、Decision Ledger | `core/src/main.rs` |

### 2.2 数据流
请求从浏览器到 SQLite 的完整路径：

```
浏览器
  │  HTTPS / 静态资源
  ▼
nginx (frontend 容器, :8080)          ← 唯一对外端口
  │  REST + SSE (显式 UTF-8)
  ▼
Go 后端 (backend 容器, :8000)         ← 仅本机/内网
  │  ├─ 业务逻辑 / agent loop / LLM 调用 / 论文同步
  │  └─ 记忆相关请求经 HTTP 转发 ↓
  ▼
Rust core (core 容器, :8788)          ← 仅 compose 内网，不 publish
  │  向量化 / 记忆 CRUD / 梦境整合
  ▼
SQLite (WAL) + 数据卷 nro-data        ← Go 与 Rust 共享同一 .db 文件
```

要点：
- 前端构建产物由 frontend 容器的 nginx 托管，并反代 `/api/*` 到 backend。
- backend 是业务中枢，所有 `/api/memory/*` 路由是 Rust core 的**代理**（见 `backend/internal/memory/client.go`），前端不直连 core。
- core 不暴露公网端口（compose 中仅 `expose: 8788`），只有 backend 能访问。
- Go 与 Rust 共享同一个 SQLite 文件（`/data/db/reading_assistant.db`），靠 WAL 模式实现多进程并发读 + 单写。

### 2.3 SQLite 共享模型
- **建表分工**：Go `store.Migrate` 建业务表（`topics`/`papers`/`chat_*`/`skills`/`memories`/`decision_ledger`/`llm_calls`/`llm_cache`）；Rust `db.rs` `ensure_dream_diary_table` 补建 `dream_diary` 与 `memory_vectors`。两侧均用 `CREATE TABLE IF NOT EXISTS`，幂等不冲突。
- **读写分工**：`memories` 表 Go 侧只读（编排时查询），写入由 Rust 负责；`dream_diary`/`memory_vectors` 仅 Rust 读写；其余表由 Go 独占。
- **并发**：Go 用 `modernc.org/sqlite`（纯 Go 驱动，`SetMaxOpenConns(1)`）；Rust 用 `rusqlite`（`bundled`，`Mutex<Connection>`）。两者通过 WAL + `busy_timeout=15000` 协调，单写多读，core 仅被单实例 backend 调用，冲突可控。

---

## 3. 目录结构

`v2/` 下各目录职责（与旧 Python 代码 `app/`、`streamlit_app/` 物理隔离）：

```
v2/
├── backend/                 # Go 后端（单二进制）
│   ├── cmd/api/main.go      # 入口：加载 config → open db → migrate → server.Run
│   ├── internal/
│   │   ├── config/          # 配置加载 + 路径绝对化 + 启动校验（痛点②核心）
│   │   ├── store/           # SQLite 连接/WAL/迁移 + 各表 DAO（sessions/skills/store）
│   │   ├── paper/           # GitHub 同步 + 论文/主题持久化 + 旧库迁移
│   │   ├── llm/             # LLM 客户端 + Provider 能力矩阵 + 成本/缓存（痛点①核心）
│   │   ├── agent/           # agent loop + 流式 + 工具 + 技能 + 自进化（痛点①核心）
│   │   ├── memory/          # Rust core 的 HTTP 客户端（记忆/梦境代理）
│   │   └── server/          # gin 路由装配 + 各 handler
│   ├── go.mod / go.sum
│   └── (Dockerfile 在 deploy/)
├── core/                    # Rust 核心服务（独立 HTTP 微服务）
│   ├── src/
│   │   ├── main.rs / lib.rs # 入口与模块导出
│   │   ├── config.rs        # core 配置（embedding/记忆参数）
│   │   ├── db.rs            # SQLite 连接 + dream_diary/memory_vectors 建表
│   │   ├── vector.rs        # 向量化（Ollama/OpenAI embedding）+ cosine
│   │   ├── memory.rs        # 五层记忆 CRUD + 相似度检索 + Decision Ledger
│   │   ├── dreaming.rs      # 睡眠整合三阶段 + 六信号评分 + Dream Diary
│   │   └── http.rs          # axum 路由
│   ├── Cargo.toml / Cargo.lock
│   └── (Dockerfile 在 deploy/)
├── frontend/                # TS 前端（Vite + React + Tailwind）
│   ├── src/
│   │   ├── main.tsx / App.tsx
│   │   ├── pages/           # ChatPage / LibraryPage / SettingsPage
│   │   ├── components/      # Markdown / ErrorBoundary / Toast / Feedback
│   │   ├── api/             # client.ts（显式 UTF-8 + SSE）/ types.ts / index.ts
│   │   ├── stores/          # Zustand：chat / library / ui
│   │   └── styles/          # Tailwind + CJK 字体栈
│   ├── package.json / pnpm-lock.yaml
│   └── (Dockerfile 在 deploy/)
├── deploy/                  # 部署配置
│   ├── docker-compose.yml   # 三服务编排
│   ├── .env.example         # 环境变量模板
│   ├── Dockerfile.backend / Dockerfile.core / Dockerfile.frontend
├── docs/                    # 文档
│   ├── specs/               # 设计 spec
│   ├── plans/               # 实现计划
│   ├── handoff.md           # 本文件
│   └── reviews/             # 审查报告（待归档，见 §9）
└── scripts/                 # 构建/迁移辅助脚本
```

---

## 4. 本地开发环境搭建

### 4.1 前置依赖
| 依赖 | 版本要求 | 说明 |
|---|---|---|
| Go | 1.25+ | `backend/go.mod` 声明 `go 1.25.0`，低于此版本无法编译 |
| Rust | 1.82+（stable） | `core/Cargo.toml` 用 `edition 2021` + axum 0.7 / tokio 1 / rusqlite 0.32，建议最新 stable |
| Node.js | 20+ | 前端用 Vite 5 / React 18 / TypeScript 5.6；包管理器用 pnpm（仓库含 `pnpm-lock.yaml`） |
| Ollama | 任意近期版本 | 本地 LLM 与 embedding 默认后端；拉取 `qwen2.5:7b` 与 `nomic-embed-text` |
| Docker（可选） | Docker + Compose v2 | 仅在需要一键部署时安装；本地开发可不装 |

### 4.2 启动顺序（本地三终端开发）
三个服务需同时运行，建议按依赖顺序启动：

1. **启动 Ollama**（提供 LLM 与 embedding）：
   ```
   ollama serve
   ollama pull qwen2.5:7b
   ollama pull nomic-embed-text
   ```
2. **启动 Rust core**（提供记忆/向量化/梦境）：
   ```
   cd v2/core
   NRO_DATA_DIR=/tmp/nro-data \
   EMBEDDING_API_BASE=http://localhost:11434 \
   cargo run
   # 默认监听 127.0.0.1:8788
   ```
3. **启动 Go backend**：
   ```
   cd v2/backend
   LLM_PROVIDER=ollama \
   LLM_API_BASE=http://localhost:11434/v1 \
   LLM_MODEL=qwen2.5:7b \
   OLLAMA_BASE_URL=http://localhost:11434 \
   CORE_BASE_URL=http://127.0.0.1:8788 \
   NRO_DATA_DIR=/tmp/nro-data \
   go run ./cmd/api
   # 默认监听 127.0.0.1:8000
   ```
4. **启动前端 dev server**：
   ```
   cd v2/frontend
   pnpm install
   pnpm dev
   # 默认 http://localhost:5173，经 vite proxy 转发 /api 到 :8000
   ```

> 注意：本地开发时 Go 与 Rust 必须指向**同一个 `NRO_DATA_DIR`**，否则两者打开不同 SQLite 文件，记忆相关功能会查不到数据。

### 4.3 关键环境变量
完整清单见 `deploy/.env.example`，本地开发最常用的如下：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `NRO_DATA_DIR` | 可执行文件同级 `data/` | 数据根目录（绝对路径）；Go/Rust 必须一致 |
| `SERVER_HOST` / `SERVER_PORT` | `127.0.0.1` / `8000` | Go 监听地址 |
| `LLM_PROVIDER` | `deepseek` | `ollama` / `deepseek` / `openai-compat` |
| `LLM_API_BASE` | `https://api.deepseek.com/v1` | OpenAI 兼容基址 |
| `LLM_API_KEY` | 空 | ollama 可空；其他 provider 缺失则启动 fail-fast |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 服务地址 |
| `DAILY_LLM_BUDGET_USD` | `3.0` | 日预算（美元）—— 配置项已存在，**强制拦截尚未实现**，见 §9 |
| `CORE_BASE_URL` / `CORE_TIMEOUT` | `http://127.0.0.1:8788` / `60` | Rust core 地址与超时 |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` / `EMBEDDING_API_BASE` | `ollama` / `nomic-embed-text` / `http://localhost:11434` | Rust core embedding 配置 |
| `GITHUB_TOKEN` / `DEFAULT_GITHUB_REPO` | 空 / `papers-we-love/papers-we-love` | 论文同步；匿名限 60/hour，有 token 5000/hour |
| `RECENCY_HALF_LIFE_DAYS` / `MAX_AGE_DAYS` | `30` / `365` | 记忆时效性半衰期与超龄阈值（spec §5.3） |
| `VITE_API_BASE` | 空 | 前端 API 基址；空则走相对路径由 vite proxy 转发 |

### 4.4 常见问题
- **启动报 `LLM_API_KEY 未配置`**：`config.go` `Validate()` 对非 ollama provider 强制要求 key。改用 `LLM_PROVIDER=ollama` 或填入 key。
- **论文同步后重启消失**：确认 `NRO_DATA_DIR` 为绝对路径且未随终端 cwd 变化；`/api/health` 返回的 `data_dir` 即实际数据目录。
- **记忆/梦境接口 502**：Rust core 未启动或 `CORE_BASE_URL` 指向错误。backend 对 core 是懒连接，仅在首次请求时暴露 502。
- **前端中文方框**：确认浏览器装了 CJK 字体；字体栈见 `frontend/src/styles/index.css`。
- **Go 编译卡在下载 modernc.org/sqlite**：纯 Go 驱动体积较大，首次 `go mod download` 较慢，属正常。
- **Rust 编译报 bundled sqlite 失败**：`rusqlite` 用 `bundled` feature 自带 C 源码，需 `cc`；Linux 装 `build-essential`，macOS 装 Xcode Command Line Tools。

---

## 5. 核心模块说明

### 5.1 Go agent loop（痛点①运行时层修复）
位置：`backend/internal/agent/`，核心文件 `loop.go`、`stream.go`、`chat.go`。

**StreamEvent 统一 channel**（`stream.go`）：所有流式路径统一返回 `<-chan StreamEvent`，事件类型枚举如下，杜绝旧版"dict 当生成器"：

| 事件类型 | 含义 | 关键字段 |
|---|---|---|
| `token` | 模型生成的一段文本 | `content` |
| `tool_call` | 模型决定调用工具 | `tool_name` / `tool_args` / `tool_call_id` |
| `tool_result` | 工具执行结果 | `tool_name` / `tool_result` |
| `usage` | 本轮 token 用量 | `usage` |
| `error` | 流程错误（收到即结束） | `content` / `turn` |
| `done` | 正常结束（最后一个事件） | `turn` |

**agent loop 主循环**（`loop.go` `Agent.Run`）：
```
for turn < maxTurns {
    检查 ctx 取消 / token 预算
    callOnce(messages)              // 带 5xx 单轮重试
    if 无 tool_calls { emit tokens; emit done; break }
    for each tool_call { 执行; emit tool_result; append tool 消息 }
    // 带工具结果进入下一轮
}
```

关键常量（`loop.go`）：
- `DefaultMaxTurns = 8`：最大轮数，覆盖"列主题→搜论文→取详情→综合回答"类多步任务。
- `DefaultPerTurnTimeout = 90 * time.Second`：单轮 LLM 调用超时，兼容推理模型思考时间。
- `DefaultTokenBudget = 40000`：整个 loop 的 token 上限，超限 emit error 终止，防失控烧钱。

**流式异常落库**（`chat.go` `tapAndPersist`）：转发 agent 事件给 SSE handler 的同时累积 assistant 文本；channel 关闭时（无论 `done` 还是 `error`）都把累积内容落库——即便中途出错，用户下次进会话也能看到不完整的回答而非空白。`defer recover` 兜底 panic，不抛到 HTTP 层。

> 已知简化（见 §9）：当前 LLM 调用是非流式（`client.go` 标注"M2 扩展流式"未做），`emitTokens` 按行分块模拟流式体验，非真逐 token 流。

### 5.2 LLM Provider 能力矩阵（痛点①协议层根治）
位置：`backend/internal/llm/provider.go`。

旧版 `llm_utils.py` 对所有模型无条件注入 `reasoning_effort="max"` + `thinking.type="enabled"`，DeepSeek-chat 不接受 → 每次 400。修复方案是表驱动的 `Capabilities`，按 `(provider, model)` 声明支持哪些推理参数，请求构造时**只下发被声明支持的参数**：

| (provider/model) | SupportsReasoningEffort | SupportsThinkingParam | ReturnsReasoningContent |
|---|---|---|---|
| `deepseek/deepseek-chat` | false | false | false |
| `deepseek/deepseek-v4-flash` | false | false | false |
| `deepseek/deepseek-reasoner` | false | false | true |
| `deepseek/deepseek-v4-pro` | false | false | true |
| `openai/o1` `o3` `o1-mini` `o3-mini` | true | false | false |
| 未登记模型 | false（安全兜底） | false | false |

查找策略（`Lookup`）：精确匹配 → provider 默认零能力 → 全零兜底，**绝不 panic**，未知模型默认不下发任何推理参数，从根本上杜绝"硬塞参数致 400"。

配套：
- `cost.go`：每次成功调用写入 `llm_calls` 表（token/成本），由 `server.go` 注入 `DBRecorder`。
- `cache.go`：相同请求命中 `llm_cache` 表，替代 Redis（spec §2.3 决策）。
- 启动校验：`config.go` `Validate()` 对非 ollama provider 缺 key 时 fail-fast 并给出指引，而非运行时 401。

### 5.3 路径绝对化（痛点②根治）
位置：`backend/internal/config/config.go` `resolvePaths()`。

旧版根因是相对路径 `data/reading_assistant.db` 按 cwd 解析，开机自启/快捷方式/IDE 运行时 cwd 一变就开空库。`resolvePaths` 将所有数据路径统一绝对化，基准优先级：

1. 环境变量 `NRO_DATA_DIR`（最高，便于 Docker 卷挂载）；
2. 可执行文件同级 `data/` 目录（默认，单机绿色部署）；
3. 用户主目录 `~/.nuclear-research-ox/`（兜底）。

派生子路径均为绝对路径：`DBPath = DataDir/db/reading_assistant.db`、`LogDir`、`BackupDir`，并 `MkdirAll` 确保存在。`store.Open` 收到的 `dbPath` 已是绝对路径，本层不再处理相对路径。

配套保障：
- **孤立数据迁移**：`backend/internal/paper/migration.go` 扫描常见 cwd 下的旧 Python 库，`POST /api/migrate-legacy` 一键导入。
- **Docker 卷持久化**：`deploy/docker-compose.yml` 用命名卷 `nro-data` 挂载到 `/data`，容器重建不丢数据。
- **启动自检**：`/api/health` 返回实际数据目录绝对路径，便于排查。

### 5.4 Rust 记忆引擎（五层 + 六信号 + 三阶段睡眠 + Dream Diary）
位置：`core/src/memory.rs`、`core/src/dreaming.rs`、`core/src/db.rs`、`core/src/vector.rs`。

**五层记忆**（spec §5.1，`memory.rs`）：

| 层 | 存储 | 用途 | 实现 |
|---|---|---|---|
| 工作记忆 | 进程内（Go 侧上下文窗口） | 当前对话上下文 | 会话级，不持久化 |
| 情景记忆 | `memories` 表（`layer=episodic`） | 交互事件/经历 | Rust 写入 |
| 长期记忆 | `memories` 表（`layer=long_term`） | 事实/决策/人物/里程碑 | Rust 梦境升级写入 |
| 程序记忆 | `skills` 表（Go 管理） | 工作流/偏好/工具模式 | Go 写入 |
| 索引记忆 | `memories` 表（`layer=index`） | 元数据/重要性/关系 | Rust 写入 |

**六信号评分**（`dreaming.rs` Deep Sleep 阶段，权重见常量）：

| 信号 | 权重 | 含义 |
|---|---|---|
| 相关性 relevance | 0.30 | 与已有长期记忆的关键字重叠率（Jaccard 最大值） |
| 频率 frequency | 0.24 | 在 episodic 中出现次数（log2 归一化） |
| 查询多样性 diversity | 0.15 | created_at 离散度近似 |
| 时效性 recency | 0.15 | 半衰期衰减 `0.5^(age/half_life)` |
| 整合度 integration | 0.10 | 与已晋升长期记忆的连接数 |
| 概念丰富度 richness | 0.06 | 内容长度 / 唯一词数 |

总分 = 各信号加权和 + Light/REM 强化加成。升级须**同时满足三阈值**：`total >= 0.5` 且 `frequency >= 2` 且 `recency >= 0.3`，且未超龄（`max_age_days`）。

**三阶段睡眠**（`dreaming.rs` `Dreamer::dream`，顺序执行）：
1. **Light Sleep**：扫描近期 episodic，Jaccard 相似度去重（阈值 0.9），相似项合并为候选并累积强化信号。不写长期记忆。
2. **REM Sleep**：全局词频分析，提取主题词（top 5），增强候选频率与主题命中率强化。不写长期记忆。
3. **Deep Sleep**：六信号评分 + 三阈值判定，**仅此阶段**调用 `promote_to_long_term` 写入长期记忆；极低分（`total < 0.2`）标记 `decaying`。超龄候选静默不处理。

> 关键修正：`tokenize` 对 CJK 字符**逐字成 token**（`is_cjk` 判定），否则中文连续字会被 `is_alphanumeric` 累加成一个大 token，使 Jaccard 与相关性评分对中文论文场景失效。

**Dream Diary**（`db.rs` `dream_diary` 表 + `dreaming.rs`）：每次梦境按 `light`/`rem`/`deep`/`done` 四阶段各写一行，共享同一 `run_id`。`list_diary` 默认只返回 `stage='done'` 的汇总行，中间阶段可凭 `run_id` 关联查询。前端据此可视化"审查了哪些记忆、哪些升级、哪些衰减"。

**Decision Ledger**（`memory.rs` `decision_ledger` 表）：结构化记录每个重大决策（context/decision/rationale/outcome），agent 遇相似问题先查账本避免重复争论。

### 5.5 前端 SSE 流式 + Markdown 渲染（痛点③根治）
位置：`frontend/src/api/client.ts`、`frontend/src/components/Markdown.tsx`。

**SSE 流式**（`client.ts` `sendMessageStream`）：
- `EventSource` 不支持 POST，故用 `fetch` + `ReadableStream` 手写 SSE 解析。
- 请求头显式 `Content-Type: application/json; charset=utf-8`，响应用 `TextDecoder('utf-8')` 显式解码，杜绝 ISO-8859-1 误判（旧版 `resp.text` 真乱码根因）。
- 按 `\n\n` 切分 SSE 事件块，解析 `data:` 行为 `StreamEvent` JSON；返回 `AbortController` 供前端中断。
- 非 2xx 走结构化 `{error}` 而非 `text[:200]`。

**Markdown 渲染**（`Markdown.tsx`）：
- user 消息纯文本（不渲染 Markdown，避免用户输入 `**` 被解释）。
- assistant 消息用 `react-markdown` + `remark-gfm`（表格/任务列表）+ `rehype-raw`（允许内联 HTML）+ `rehype-sanitize`（白名单过滤，防 XSS）。`rehype-raw` 必须在 `rehype-sanitize` 之前。
- sanitize schema 放宽常见结构性标签与 `className`，**禁止 `script`/`style`/`iframe`**。
- 旧版 `html.escape` 把 `**加粗**` 显示成字面量，新版正确渲染。

**其他 UI 乱码根治项**：
- 全局 CJK 字体栈：`"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans CN", sans-serif`（`styles/index.css`）。
- 本地图标 `lucide-react`（本地打包），杜绝运行时 CDN 依赖。
- React 组件自动转义，禁止 `dangerouslySetInnerHTML`。
- Zustand 集中管理导航状态，刷新可恢复。

---

## 6. 数据库

### 6.1 表清单
数据库文件：`<DataDir>/db/reading_assistant.db`（SQLite，WAL 模式）。

| 表 | 建表方 | 用途 | 关键字段 |
|---|---|---|---|
| `topics` | Go | 论文主题分类 | `id`, `name`, `name_cn`, `paper_count` |
| `papers` | Go | 论文元数据 | `id`, `title`, `authors`, `year`, `topic_id`, `pdf_url`, `read_status` |
| `chat_sessions` | Go | 对话会话 | `id`, `title`, `skill_mode`, `enabled_skill_ids`, `total_tokens` |
| `chat_messages` | Go | 对话消息 | `id`, `session_id`, `role`, `content`, `reasoning_content`, `tool_calls`, `token_count` |
| `skills` | Go | 技能（含自进化字段） | `slug`(unique), `level`, `usage_count`, `success_rate`, `version` |
| `memories` | Go 建表 / Rust 读写 | 五层记忆 | `id`, `layer`, `content`, `importance_score`, `decay_state`, `embedding_id` |
| `decision_ledger` | Go 建表 / Rust 读写 | 决策账本 | `id`, `context`, `decision`, `rationale`, `outcome` |
| `llm_calls` | Go | LLM 调用与成本追踪 | `provider`, `model`, `prompt_tokens`, `completion_tokens`, `cost_usd` |
| `llm_cache` | Go | LLM 响应持久化缓存（替代 Redis） | `cache_key`, `response` |
| `dream_diary` | Rust | 梦境整合日志（四阶段） | `run_id`, `stage`, `reviewed_count`, `promoted_count`, `decayed_count`, `details_json` |
| `memory_vectors` | Rust | embedding 向量存储 | `id`, `memory_id`, `vector`(JSON 数组) |

### 6.2 WAL 共享与 Go/Rust 共存注意事项
- **WAL 模式**：Go `store.Open` 与 Rust `db.rs` `open` 均执行 `PRAGMA journal_mode=WAL`，支持多进程并发读 + 单写。Rust 额外设 `PRAGMA busy_timeout=15000`，遇锁等待 15s 而非立即报错。
- **外键**：两侧均 `PRAGMA foreign_keys=ON`。
- **连接池**：Go `SetMaxOpenConns(1)`（SQLite 单写，多连接反增锁竞争）；Rust 用 `Mutex<Connection>` 单连接串行化。
- **Mutex 中毒恢复**：Rust `db.rs` `lock()` 用 `unwrap_or_else(|e| e.into_inner())` 显式恢复中毒锁，避免上次 panic 后二次 panic 连锁瘫痪服务。
- **绝对不要**让 Go 与 Rust 指向不同 `NRO_DATA_DIR`——这是本地开发最易踩的坑，会导致记忆相关功能查不到数据。
- **备份**：直接复制 `.db` 文件即可（WAL 模式下建议先 `PRAGMA wal_checkpoint(TRUNCATE)` 或同时复制 `-wal`/`-shm`）。Go 服务正常退出时 `server.Run` 会执行 checkpoint，避免 `-wal` 残留。
- **迁移幂等**：所有建表用 `CREATE TABLE IF NOT EXISTS`，绝不删表——旧版数据丢失纯因路径漂移而非建表逻辑，本版保持这一约定。

---

## 7. 测试

### 7.1 如何跑测试
三种语言各自的测试命令：

```
# Go 后端测试（含契约测试：mock LLM 五路径）
cd v2/backend && go test ./...

# Rust core 测试
cd v2/core && cargo test

# 前端类型检查（无独立单测框架，用 tsc 保证类型安全）
cd v2/frontend && pnpm typecheck
```

Go 契约测试（`backend/internal/llm/client_test.go`）用 mock LLM server 覆盖 spec §4.1 要求的五条路径：normal / stream / with_tools / empty_content / bad_json，是 M1 的前置门槛。

### 7.2 测试覆盖现状
- **Go**：`agent`（loop/chat/evolve）、`llm`（client/契约五路径）、`paper`（github/migration/repository）、`store`（sessions/skills/store）、`server`（server/chat_handlers）均有 `*_test.go`。
- **Rust**：`memory.rs` 与 `dreaming.rs` 内嵌 `#[cfg(test)]` 模块，覆盖记忆 CRUD、列表、关键字检索、升级/衰减、决策账本、梦境空/高频场景、tokenize（ASCII/CJK）、Jaccard、recency 计算。
- **前端**：无运行时单测，靠 `tsc --noEmit` 类型检查 + 手工端到端验证。

### 7.3 已知盲区
- `backend/internal/server/memory_handlers.go`（`/api/memory/*` 代理 Rust core 的 handler）**无 server 级测试**，仅 `memory/client_test.go` 覆盖了 Go 侧 client。Rust core 异常时 backend 的降级/错误响应路径未验证。
- 前端无自动化测试，SSE 流式、Markdown 渲染、状态恢复均靠手工验证。
- 端到端测试（真实 DeepSeek/Ollama 下同步→对话→记忆全链路）未脚本化，依赖人工跑通。
- 流式中断落库的边界场景（如客户端在 tool_call 中途断开）有代码路径但缺针对性用例。

---

## 8. 部署

### 8.1 Docker Compose 一键起
编排文件：`deploy/docker-compose.yml`，三服务 + 一命名卷 + 一内网。

```
cd v2
cp deploy/.env.example deploy/.env   # 按需填写 LLM key 等
docker compose -f deploy/docker-compose.yml up -d --build
```

启动后访问 `http://<宿主>:8080`（frontend nginx 唯一对外端口）。

### 8.2 服务与端口映射
| 服务 | 容器端口 | 宿主映射 | 说明 |
|---|---|---|---|
| `frontend` (nginx) | 8080 | `8080:8080` | 唯一对外端口，反代 `/api/*` 到 backend |
| `backend` (Go) | 8000 | `127.0.0.1:8000:8000` | 仅本机暴露，外网访问走 nginx |
| `core` (Rust) | 8788 | 不 publish（仅 `expose`） | 仅 compose 内网 backend 可访问 |

健康检查：backend `wget http://127.0.0.1:8000/api/health`，core `wget http://127.0.0.1:8788/health`，均 30s 间隔。

### 8.3 数据卷
- 命名卷 `nro-data` 挂载到 backend 与 core 的 `/data`，二者共享同一 SQLite 文件。
- 容器重建不丢数据（痛点②部署层保障）。
- 备份：`docker run --rm -v nro-data:/d -v $PWD:/o alpine tar czf /o/nro-data-backup.tgz -C /d .`

### 8.4 `.env` 配置
完整模板见 `deploy/.env.example`，必填项：
- `LLM_PROVIDER` / `LLM_API_BASE` / `LLM_MODEL`（ollama 可不填 key）。
- `EMBEDDING_*`（Rust core 用，默认 ollama + nomic-embed-text）。
- `GITHUB_TOKEN`（可选，匿名限流 60/hour）。
- `RECENCY_HALF_LIFE_DAYS` / `MAX_AGE_DAYS`（记忆参数）。

compose 中 backend 通过 `host.docker.internal:host-gateway` 访问宿主 Ollama（`extra_hosts` 配置）。

### 8.5 路由清单（Go backend，前缀 `/api`）
| 方法 | 路径 | 所属 | 说明 |
|---|---|---|---|
| GET | `/health` | M1 | 健康检查，返回数据目录绝对路径 |
| GET | `/topics` | M1 | 列出全部主题 |
| GET | `/topics/:id/papers` | M1 | 列出某主题下论文 |
| GET | `/papers/:id` | M1 | 查询单篇论文 |
| PATCH | `/papers/:id/status` | M1 | 更新论文阅读状态 |
| POST | `/sync` | M1 | 触发 GitHub 仓库同步 |
| POST | `/migrate-legacy` | M1 | 触发旧库迁移（找回历史数据） |
| POST | `/chat/sessions` | M2 | 新建会话 |
| GET | `/chat/sessions` | M2 | 列出会话 |
| GET | `/chat/sessions/:id` | M2 | 查询会话详情 |
| GET | `/chat/sessions/:id/messages` | M2 | 列出会话消息 |
| POST | `/chat/sessions/:id/messages` | M2 | 非流式发消息 |
| POST | `/chat/sessions/:id/messages/stream` | M2 | SSE 流式发消息 |
| POST | `/chat/evolve` | M2 | 手动触发会话自进化 |
| GET | `/skills` | M2 | 列出全部技能 |
| POST | `/skills` | M2 | 创建/更新技能（upsert） |
| DELETE | `/skills/:slug` | M2 | 删除技能 |
| POST | `/skills/:slug/evolve` | M2 | 查询技能自进化统计 |
| POST | `/memory` | M4 | 创建记忆（代理 core） |
| GET | `/memory/:id` | M4 | 查询记忆 |
| DELETE | `/memory/:id` | M4 | 删除记忆（含向量级联） |
| GET | `/memory/search` | M4 | 关键字检索 |
| POST | `/memory/search-vector` | M4 | 向量相似度检索 |
| POST | `/memory/dream` | M4 | 触发梦境整合 |
| GET | `/memory/dream-diary` | M4 | 列出 Dream Diary |
| GET | `/memory/dream-diary/:id` | M4 | 查询单条 Dream Diary |
| POST | `/memory/decision` | M4 | 记录决策到账本 |
| GET | `/memory/decisions` | M4 | 列出决策 |

### 8.6 路由清单（Rust core，无前缀，仅内网）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/memory` | 创建记忆（异步生成 embedding） |
| GET | `/memory/:id` | 查询记忆 |
| DELETE | `/memory/:id` | 删除记忆（含向量级联） |
| GET | `/memory/search` | 关键字检索（`?keyword=&limit=`） |
| POST | `/memory/search-vector` | 向量相似度检索（body: `{query, top_k}`） |
| POST | `/dream` | 触发梦境（Light → REM → Deep） |
| GET | `/dream-diary` | 列出 Dream Diary（`?limit=`） |
| GET | `/dream-diary/:id` | 查询单条 Dream Diary |
| POST | `/decision` | 记录决策到账本 |
| GET | `/decisions` | 列出决策（`?limit=`） |

> 注意：Go 的 `/api/memory/*` 与 core 的 `/memory/*` 路径几乎对应，Go 层仅做代理转发；前端永远只调 Go 的 `/api/*`。

---

## 9. 已知限制与后续待办

按优先级排序，P0 为接手后应优先处理项。

### P0（工程治理，spec 要求但未归档）
1. **三轮审查报告与安全审查报告未归档**：`docs/reviews/` 目录尚不存在。spec §10.3/§10.4 要求三轮审查（构建契约 / 功能稳定性 / 安全可维护性）+ 安全漏洞审查，均需补齐报告文件。建议按 spec §10.3 的审查清单逐项执行并归档 `round1-build-contract.md` / `round2-function-stability.md` / `round3-security-maintainability.md` / `security-audit.md`。
2. **新手部署文档 `docs/docker-deploy.md` 缺失**：spec §12.2 要求面向未用过 Docker 的用户撰写部署指南（装 Docker 步骤、`.env` 配置、启动、数据备份恢复、常见问题），当前仅有 `deploy/.env.example`，需补文档。

### P1（功能缺口，影响 spec 验收）
3. **自动梦境定时器未实现**：spec §5.3 规定 `dreamIntervalHours`（默认 24h）自动触发梦境，当前仅支持手动 `POST /api/memory/dream`。Rust core 与 Go backend 均无定时调度器，需引入（如 tokio 定时任务或 Go 侧 cron）。
4. **日预算未强制**：`DAILY_LLM_BUDGET_USD` 配置项已存在（默认 3.0），但调用前未做日累计成本拦截。`llm/cost.go` 只记录不拦截，需补"查询当日累计 → 超预算拒绝调用"逻辑。
5. **`memory_handlers` 无 server 级测试**：`/api/memory/*` 代理 handler 在 Rust core 异常时的降级/错误响应路径未覆盖（见 §7.3）。

### P2（已知简化，影响体验但不阻塞）
6. **LLM 流式为模拟流式**：`client.go` 标注"M2 扩展流式"未落地，`agent/loop.go` `emitTokens` 按行分块吐出最终回答，非真逐 token 流。需实现 OpenAI SSE 流式解析，改 `callOnce` 为流式收集。
7. **tool 消息历史重建简化**：`chat.go` `buildLLMMessages` 重建历史时跳过 `role=tool` 消息（注释标注"M2 阶段简化处理"），多轮工具调用的完整上下文在会话恢复后会丢失，需按 `tool_call_id` 完整重建。
8. **向量检索 brute-force cosine**：`memory.rs` `search_by_vector` 全表扫描计算相似度，小规模（<1万条）足够，规模增长后需换 `sqlite-vss` 或外挂 Qdrant。
9. **GEPA 完整实现未做**：`evolve.go` 仅实现"技能效果评估 + 增量改进"最小闭环（spec §6.3），未做类反向传播的 prompt 自优化。
10. **自进化"效果评估"指标未细化**：spec §14 待决项，当前 `success_rate` 仅按"无 error 且有内容"粗判，需更精细的评估指标与闭环判定。

### P3（范围外，后续阶段迁移）
11. **论文阅读器（PDF）首期跳过**：spec §1.4/§9 明确不做，保留旧 `streamlit_app/views/pdf_reader.py` 不动。
12. **非核心模块未迁移**：知识库引擎、Obsidian 同步、MCP 工具服务器、沙箱、概念图谱首期不重写（spec §1.4），后续阶段迁移。

---

## 10. 关键设计决策记录

### 10.1 为何选 SQLite 不选 Postgres/MySQL
痛点②的根因是**相对路径漂移**而非数据库本身能力不足。将路径绝对化 + Docker 卷持久化即可根治，引入 Postgres/MySQL 对单机科研工具过重——需额外运维一个 DB 服务、备份复杂、新手部署门槛高。SQLite 零运维、单文件、易复制备份，最适合单机场景。spec §2.3 明确：单机没必要多跑一个 DB 服务。

### 10.2 为何 Rust 独立服务不 FFI
首期仅向量化/记忆引擎/梦境整合用 Rust。独立 HTTP 服务可独立构建/测试/部署，Go 通过 localhost HTTP 调用，复杂度最低；FFI（cgo）性能最佳但跨平台构建复杂、调试困难、Go 与 Rust 生命周期耦合，首期不选。代价是进程间 HTTP 序列化开销，但记忆/梦境非高频路径，可接受。spec §2.3：未来若性能瓶颈再考虑 FFI。

### 10.3 为何 axum 不 actix
axum 基于 tokio/tower 生态，与 `tower-http`（CORS/trace）天然集成，类型安全的 `State` 提取器与 `axum::extract::Path`/`Query`/`Json` 让 handler 签名自文档化；actix-web 自带 actor 模型对纯 HTTP 微服务过重，且与 tokio 生态有重叠。rusqlite + axum + tokio 是当前 Rust 微服务主流组合，社区文档与示例最多。spec §2.2 选型表确认 axum。

### 10.4 为何 Redis 首期不上
当前缓存需求（LLM 响应缓存、会话）用 Go 进程内 LRU + SQLite 持久化（`llm_cache` 表）即可满足，单机没必要多跑 Redis。预留缓存接口，未来多实例再引入。spec §2.3。

### 10.5 为何新代码独立 `v2/` 目录
与旧 Python 代码（`app/`、`streamlit_app/`）物理隔离，避免混杂；按 `backend/core/frontend/docs/deploy` 分类，职责清晰。旧代码保留不动，便于对照与回滚，也方便孤立数据迁移逻辑扫描旧 cwd。spec §2.3。

### 10.6 为何 Go 用纯 Go 驱动 modernc.org/sqlite 不用 cgo 版
`modernc.org/sqlite` 是纯 Go 实现的 SQLite，无 cgo 依赖，跨平台编译与 Docker 构建简单（静态二进制）；`mattn/go-sqlite3` 需 cgo，交叉编译麻烦。代价是性能略低，但单机科研工具足够。注意驱动注册名是 `sqlite`（非 `sqlite3`），二者不可混用。见 `backend/internal/store/store.go` 注释。

### 10.7 为何流式统一用 channel 不用回调
旧版 `send_message` 在 auto 模式返回 dict、stream 模式返回生成器，调用方 `for chunk in dict` 把 dict key 当 token 吐给前端，是 agent 崩溃的次要根因。Go 的 `<-chan StreamEvent` 让所有路径（正常/工具/错误）返回类型一致，channel 关闭即结束，天然支持 `ctx` 取消与 `range` 消费，杜绝类型歧义。见 `backend/internal/agent/stream.go`。

---

## 附录：接手者快速上手清单

1. 读本文档第 1-3 章建立全局认知。
2. 按 §4 搭建本地环境，跑通 Ollama + core + backend + frontend 四件套。
3. 按 §7 跑 `go test ./...` / `cargo test` / `pnpm typecheck`，确认基线绿。
4. 手工验证三大痛点修复：同步论文后改 cwd 重启看是否丢失（痛点②）；用 ollama 跑一轮带工具的对话（痛点①）；检查中文渲染与 Markdown（痛点③）。
5. 按 §9 P0 补齐审查报告与部署文档，再按 P1 补自动梦境定时器与日预算强制。
6. 改动业务代码前，先读对应模块的文件头概述注释（每个源文件开头均有职责说明）。

— 文档结束 —
