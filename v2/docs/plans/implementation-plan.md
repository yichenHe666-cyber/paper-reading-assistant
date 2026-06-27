# 实现计划 — 核动力科研牛马 v2 多语言重构

> 关联 spec：`v2/docs/specs/2026-06-27-multilang-rewrite-design.md`
> 策略：分 M1–M5 推进，每里程碑独立可验收；每文件头概述 + 详细行注释；三轮审查与安全审查在 M5 统一进行并归档报告。

---

## M1 — Go 后端骨架 + 持久化 + LLM 适配（痛点②③基础）

**目标**：可构建运行的 Go 单二进制，论文同步后重启不丢，DeepSeek/Ollama 可发通。

| # | 任务 | 关键文件 | 依赖 |
|---|---|---|---|
| 1 | 项目骨架 | `backend/go.mod`、`backend/cmd/main.go` | — |
| 2 | 配置加载 + 路径绝对化 + 启动校验 | `backend/internal/config/*.go` | 1 |
| 3 | SQLite 存储层（WAL + 迁移 + 绝对路径） | `backend/internal/store/*.go` | 2 |
| 4 | 论文/主题同步与持久化 + 孤立数据迁移 | `backend/internal/paper/*.go` | 3 |
| 5 | LLM 适配层 + provider 能力矩阵 + 成本追踪 | `backend/internal/llm/*.go` | 2 |
| 6 | API 路由（论文/主题/健康/LLM 配置） | `backend/internal/api/*.go` | 4,5 |
| 7 | 契约测试（mock LLM 五路径） | `backend/internal/llm/*_test.go` | 5 |

**验收**：
- `go build ./...` 通过；`go run` 启动后访问健康接口返回数据目录绝对路径。
- 论文同步后，模拟 cwd 变化重启，论文计数不变（路径绝对化生效）。
- mock LLM 五路径（normal/stream/with_tools/empty_content/bad_json）测试全绿。
- 真实 DeepSeek/Ollama 至少完成一次非流式调用。

---

## M2 — agent loop + 流式 + 技能 + 自进化雏形（痛点①）

| # | 任务 | 关键文件 | 依赖 |
|---|---|---|---|
| 1 | StreamEvent 抽象 + 统一 channel | `backend/internal/agent/stream.go` | M1.5 |
| 2 | agent loop（max_turns + 超时 + 预算） | `backend/internal/agent/loop.go` | 1 |
| 3 | 技能 upsert + 注册 | `backend/internal/agent/skill.go`、`backend/internal/store/skills.go` | M1.3 |
| 4 | 函数调用执行 + 工具协议适配 | `backend/internal/agent/tools.go` | 2,3 |
| 5 | 流式异常落库 + SSE 处理器 | `backend/internal/agent/chat.go`、`backend/internal/api/chat.go` | 2 |
| 6 | 自进化雏形：任务后提炼技能 + 复用 | `backend/internal/agent/evolve.go` | 3,4 |

**验收**：真实 DeepSeek/Ollama 下多轮工具调用成功；流式不崩且中断落库；技能可沉淀并在相似任务复用。

---

## M3 — TS 前端 + UI 乱码根治（痛点③）

| # | 任务 | 关键文件 | 依赖 |
|---|---|---|---|
| 1 | Vite+React+TS+Tailwind 骨架 + CJK 字体栈 | `frontend/src/main.tsx`、`styles/*` | — |
| 2 | API 客户端（显式 UTF-8 + 类型化） | `frontend/src/api/*` | M1.6 |
| 3 | 状态管理（Zustand）+ 路由 | `frontend/src/stores/*`、`App.tsx` | 2 |
| 4 | 对话页（assistant Markdown 渲染 + SSE） | `frontend/src/pages/chat.tsx` | M2.5 |
| 5 | 论文/主题/设置页 | `frontend/src/pages/*` | 2 |
| 6 | 本地图标（lucide）+ 组件库 | `frontend/src/components/*` | 1 |

**验收**：CJK 字体正常无方框；assistant Markdown 正确渲染；刷新状态不丢；对话流式可用。

---

## M4 — Rust core：向量化 + 记忆 + 睡眠整合

| # | 任务 | 关键文件 | 依赖 |
|---|---|---|---|
| 1 | Rust axum 骨架 + HTTP 契约 | `core/src/http.rs`、`Cargo.toml` | — |
| 2 | 向量化（Ollama/OpenAI embedding 适配） | `core/src/vector.rs` | 1 |
| 3 | 记忆引擎 + 五层存储 | `core/src/memory.rs` | M1.3 |
| 4 | 睡眠整合三阶段（Light/REM/Deep + 六信号评分） | `core/src/dreaming.rs` | 2,3 |
| 5 | Dream Diary + Decision Ledger 接口 | `core/src/http.rs` | 4 |
| 6 | Go 侧记忆编排（调用 core） | `backend/internal/memory/*.go` | M2,4 |

**验收**：梦境可触发；长期记忆按评分升级；Dream Diary 可查。

---

## M5 — 三轮审查 + 测试 + 安全 + handoff + Docker

| # | 任务 | 产出 |
|---|---|---|
| 1 | 第1轮：构建与契约审查 | `docs/reviews/round1-build-contract.md` |
| 2 | 第2轮：功能与稳定性审查 | `docs/reviews/round2-function-stability.md` |
| 3 | 第3轮：安全与可维护性审查 | `docs/reviews/round3-security-maintainability.md` |
| 4 | 安全漏洞审查 | `docs/reviews/security-audit.md` |
| 5 | Docker 编排 + 新手部署文档 | `deploy/docker-compose.yml`、`docs/docker-deploy.md` |
| 6 | 项目交接文档 | `docs/handoff.md` |
| 7 | 稳定性打磨 + 端到端验证 | 可运行软件 |

**验收**：三轮报告归档；关键路径测试通过；安全无高危；`docker compose up -d` 一键起；交付可运行软件。

---

## 执行顺序与依赖
M1 → M2 → M3（M3.4 依赖 M2）→ M4（依赖 M1/M2）→ M5。
M3 与 M4 部分可并行（前端不依赖 Rust core）。

## 风险控制
- 每里程碑结束做一次构建+测试自检，不绿不进下一阶段。
- 痛点修复优先：M1 即解决痛点②（路径），M2 解决痛点①（agent），M3 解决痛点③（UI）。
- 论文阅读器（PDF）全程跳过。
