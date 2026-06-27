# 安全漏洞审查报告 — 核动力科研牛马 v2

> 审查日期：2026-06-27 · 视角：OWASP Top 10 + 跨层态势
> 范围：Go 后端、Rust core、前端、Docker 部署配置

## 总体评级

**中危**（初审高危，经修复后降为中危）

初审为高危的主因是 API 无鉴权 + 默认监听 `0.0.0.0`。已将默认 Host 改为 `127.0.0.1` 并补齐 Docker 部署（core 不映射公网端口、非 root 容器、数据卷），致命暴露面消除。剩余中危项为公网部署前需补的鉴权与限流。

## 已修复漏洞

| ID | 类型 | 严重度 | 位置 | 修复 |
|---|---|---|---|---|
| S1 | 认证缺失（暴露面收敛） | 高→中 | `config.go` Host 默认 `0.0.0.0` | 默认改 `127.0.0.1`，外网访问走 nginx 反代；Docker 中 core 仅 expose 不 publish |
| S2 | Docker 部署产物缺失 | 高→已修复 | `v2/deploy/` 全无 | 补齐 3 个 Dockerfile + compose + .env.example，非 root 用户、core 不映射公网端口 |
| S5(部分) | 信息泄露（sourcemap） | 中→已修复 | `vite.config.ts` | 生产 sourcemap 改 false |
| S5(部分) | 信息泄露（错误体截断） | 中→已修复 | `vector.rs`、`http.rs` | 上游响应体截断至 200 字符 |

## 仍存在的漏洞（需公网部署前修复）

| ID | 类型 | 严重度 | 位置 | 说明与修复建议 |
|---|---|---|---|---|
| S1-残留 | API 鉴权缺失 | 中 | `server.go` 仅 `gin.Recovery()` | 同网段/本机场景可接受（Host 已限 127.0.0.1）；公网部署必须加 token/Basic Auth 中间件 |
| S3 | 每日 LLM 预算未强制 | 中 | `config.go` 有 `DailyBudgetUSD` 但代码不检查 | 在 `llm.Client` 或 agent 层聚合当日成本，超预算拒绝并 429 |
| S4 | GitHub Token 滥用 | 中 | `handlers.go` 接受任意 owner/repo | 白名单仅允许 `cfg.GitHub.DefaultRepo`，拒绝任意值 |
| S5-残留 | 错误信息泄露 | 中 | handlers 把 `err.Error()` 直接回客户端 | 5xx 统一返回笼统消息 + 日志 ID；`/health` 路径脱敏或需鉴权 |
| S6 | SSE 资源耗尽 | 中 | `chat_handlers.go` 无并发上限 | 限流中间件 + 全局并发上限 + 单 IP 连接数上限 |
| S7 | CSRF | 低 | 无 CSRF 防护 | 当前强制 JSON Content-Type 意外挡住；未来加 CORS 时需补 SameSite Cookie + token |
| S8 | migrate-legacy 无鉴权可触发 | 低 | `handlers.go` | 该端点加鉴权，或仅启动时自动跑一次 |
| S9 | 安全响应头缺失 | 低 | `server.go` | 加 `X-Content-Type-Options`/`CSP`/`X-Frame-Options`/`Referrer-Policy` |
| S11 | LLM 空密钥仍发 Bearer | 低 | `llm/client.go` | apiKey 为空时跳过 Authorization 头 |
| S12 | upsertSkill 未校验 slug | 低 | `chat_handlers.go` | 复用 `validateDraft` 的 slug 校验 |
| S13 | Rust core 监听可改公网 | 低 | `config.rs` | 强制 `127.0.0.1` 或加 token 校验 |

## 干净面（无漏洞）

以下常规漏洞类型经逐一核对确认不存在：

- **SQL 注入**：Go/Rust 全部 SQL 用参数化（`?`/`params![]`），无字符串拼 SQL
- **命令注入**：全仓库无 `os/exec`/`exec.Command`
- **前端 XSS**：无 `dangerouslySetInnerHTML`/`eval`/`innerHTML`；Markdown 经 `rehype-sanitize` 白名单
- **路径遍历**：文件操作路径来自 config 绝对化或内部生成，无用户输入直传文件系统
- **依赖安全**：版本较新（gin 1.12、modernc/sqlite 1.53、axum 0.7、reqwest 0.12 rustls、react 18.3、vite 5.4），reqwest 用 rustls 且 default-features=false（良好）；未跑 govulncheck/cargo-audit/npm audit，建议 CI 补上

## 部署安全

Docker 部署配置（`deploy/`）的安全措施：

- 三服务均以非 root 用户运行（app/nginx）
- Rust core 仅 `expose` 不 `ports`，不映射到宿主，仅 compose 内网可达
- backend 端口绑定 `127.0.0.1:8000`，不暴露公网
- 数据卷 `nro-data` 命名卷，容器重建不丢数据
- 健康检查配置齐全

## 修复优先级建议

公网部署前必须完成：S1-残留（鉴权）、S3（预算）、S6（SSE 限流）。
本机/内网使用可接受当前状态，但建议尽快补 S9（安全头）与 S4（GitHub 白名单）。
