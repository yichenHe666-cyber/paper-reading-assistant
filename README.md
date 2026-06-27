# 核动力科研牛马 v3

学术论文精读工具 — Go + Rust + TypeScript 多语言架构。

## 架构

```
前端 (TypeScript)     ↕ HTTP/SSE
Go 后端               ↕ HTTP (127.0.0.1)
Rust 核心 (记忆引擎 + 梦境巩固)
```

- **前端** (`v3/frontend/`)：React 18 + Vite 5 + Zustand + TailwindCSS
- **后端** (`v3/backend/`)：Gin + SQLite WAL + Agent Loop + LLM Client
- **核心** (`v3/core/`)：Axum + 向量检索 + 五层记忆引擎 + 睡眠梦境巩固

## 快速开始

```bash
# 1. 启动 Rust 核心
cd v3/core && cargo run --release

# 2. 启动 Go 后端
cd v3/backend && go run ./cmd/api

# 3. 启动前端
cd v3/frontend && pnpm install && pnpm dev
```

详见 `v3/docs/handoff.md` 和 `v3/docs/docker-deploy.md`。

## Docker 部署

```bash
cd v3/deploy
cp .env.example .env  # 编辑配置
docker compose up -d
```

## 文档

| 文档 | 路径 |
|---|---|
| 交接文档 | `v3/docs/handoff.md` |
| 设计规格 | `v3/docs/specs/2026-06-27-multilang-rewrite-design.md` |
| 代码审查报告 | `v3/docs/reviews/code-review-report.md` |
| 安全审查报告 | `v3/docs/reviews/security-audit.md` |
| 测试报告 | `v3/docs/reviews/test-report.md` |
| Docker 部署指南 | `v3/docs/docker-deploy.md` |
| M5 交付汇总报告 | `v3/docs/m5-delivery-report/m5-delivery-report.html` |

## 测试

```bash
# Go: 79 项
cd v3/backend && go test ./...

# Rust: 19 项
cd v3/core && cargo test

# 前端
cd v3/frontend && npx tsc --noEmit && npx vite build
```
