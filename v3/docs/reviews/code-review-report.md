# 三轮代码审查报告 — 核动力科研牛马 v2

> 审查日期：2026-06-27 · 审查范围：v2/backend、v2/core、v2/frontend 全量源码
> 审查方法：三轮并行只读审查（Go 后端 / Rust core / 前端+跨层安全），随后对致命与高危项做稳定性打磨并回归测试。

## 审查结论

| 层 | 初审评分 | 修复后状态 |
|---|---|---|
| Go 后端 | 6.5 / 10 | 致命×1 + 高×2 已修复，回归全绿 |
| Rust core | 6.0 / 10 | 致命×1 + 高×4 已修复，19 测试全绿 |
| 前端 | 6.5 / 10 | 高×2 已修复，tsc+build 零错误 |
| 安全 | 高危 | 致命暴露面（Host 默认 0.0.0.0）已修复，剩余项见安全报告 |

## 第一轮：Go 后端

### 已修复项

| 严重度 | 位置 | 问题 | 修复 |
|---|---|---|---|
| 致命 | `agent/loop.go` | `resp.Choices[0]` 未检查长度，LLM 返回空 choices 时 panic 崩溃整个进程 | 取下标前判 `len==0` 并发 error 事件 return |
| 高 | `agent/loop.go`、`agent/chat.go` | channel 发送裸 `ch<-ev`，SSE 客户端断开时缓冲满永久阻塞，Run+tapAndPersist 双 goroutine 泄漏 | 所有内部 send 改 `select{case ch<-ev: case <-ctx.Done(): return}`，tapAndPersist 传入 ctx |
| 高 | `server/server.go`、`cmd/api/main.go` | `router.Run` 无 Read/Write/Idle Timeout，慢速攻击风险；无优雅关闭，`log.Fatalf` 跳过 `defer db.Close()` | 自建 `http.Server` 设超时（SSE 300s）+ SIGINT/SIGTERM Shutdown + 正常退出走 defer |
| 高 | `config/config.go` | `Host` 默认 `0.0.0.0`，API 无鉴权暴露公网 | 默认改 `127.0.0.1`，需外网走反代 |
| 中 | `agent/chat.go` | 流式 assistant 落库错误被 `_ =` 吞掉 | 改为 `log.Printf` 记录失败 |

### spec 痛点修复到位性

痛点①（多 agent）：Provider 能力矩阵、真 agent loop、StreamEvent channel、技能 upsert、流式异常落库均已落地。

痛点③（论文重启丢失）：路径绝对化（`resolvePaths` 三级优先级 NRO_DATA_DIR > exe 同级 > home）、旧库迁移、health 返回绝对路径均已落地。

### 仍存在的限制（非阻塞）

- 非真流式：先等整段 LLM 响应再分块 emit token，用户在 LLM 思考期看不到 token（M2 可接受，后续接 SSE 流式解析）
- `reasoning_content` 未独立 emit/落库（reasoner 模型场景待完善）
- `llm_cache` 无 TTL/LRU 淘汰，会无界增长
- 日预算 `DailyBudgetUSD` 配置存在但未强制检查
- `memory_handlers.go` 11 个端点无 server 级 HTTP 测试（仅 client 层有契约测试）
- `config` 包无单元测试

## 第二轮：Rust core

### 已修复项

| 严重度 | 位置 | 问题 | 修复 |
|---|---|---|---|
| 致命 | `db.rs` | `Mutex::lock().unwrap()` 中毒后二次 panic 连锁瘫痪 | `lock().unwrap_or_else(\|e\| e.into_inner())` 显式恢复中毒锁 |
| 高 | `dreaming.rs` | `tokenize` 对 CJK 累加成一个大 token，Jaccard 与相关性评分对中文失效 | 新增 `is_cjk` 判断，CJK 逐字成 token |
| 高 | `dreaming.rs` | Dream Diary 阶段标签错位一档（light 行写占位、rem 行存 light 结果） | 每阶段执行完毕后按真实阶段名写日志 |
| 高 | `dreaming.rs`、`config.rs` | `max_age_days`（spec §5.3）完全未实现，超龄记忆照常参评 | `deep_sleep` 评分前按 age_days > max_age 过滤，超龄不升级不衰减 |
| 高 | `memory.rs` | `search_by_vector` N+1 查询（每候选单独 `get`），1 万向量产生 1 万次锁获取 | 改单条 JOIN SQL 一次取回记忆+向量 |
| 高 | `vector.rs` | Ollama 用已废弃 `/api/embeddings` 端点，新版 404 | 改用 `/api/embed`，404 时回退旧端点，兼容新旧响应字段 |
| 中 | `dreaming.rs` | `compute_recency` 未来时间 age<0 导致 recency>1 扭曲评分 | `recency.clamp(0.0, 1.0)` |
| 中 | `db.rs` | `busy_timeout=5000` 偏短 | 提升到 15000 |
| 中 | `vector.rs`、`http.rs` | 错误信息把上游响应体原样回传客户端，信息泄露 | 截断响应体至 200 字符 |

### spec §5 合规性

六信号权重（0.30+0.24+0.15+0.15+0.10+0.06=1.00）、三阈值门槛（score>=0.5 且 frequency>=2 且 recency>=0.3）、Jaccard 阈值 0.9、半衰期公式、Light→REM→Deep 顺序、仅 Deep 写 long_term——均已正确实现。`maxAgeDays` 修复后合规。`dreamIntervalHours`（自动梦境）首期仅手动触发，未实现定时器。

### 仍存在的限制

- `with_conn` 同步阻塞 async 运行时（小规模够用，大规模需 `spawn_blocking` 或异步池）
- `memory.create` 的 embedding `tokio::spawn` 任务 detached，进程关停时可能丢失向量
- `delete` 不在事务里（第二步失败留孤儿记忆）
- `http.rs` 无鉴权（依赖不暴露公网端口）
- `tower-http` cors/trace feature 引入但未挂 layer

## 第三轮：前端 + 跨层安全

### 前端已修复项

| 严重度 | 位置 | 问题 | 修复 |
|---|---|---|---|
| 高 | `pages/ChatPage.tsx` | `MessageInput` 卸载无 cleanup，SSE controller 丢失，后端 agent loop 空跑烧 token + 卸载后 setState | `useEffect` cleanup 在卸载/切会话时 `abortRef.current?.abort()` |
| 中 | 全项目 | 无 Error Boundary，子组件渲染异常整应用白屏 | 新增 `ErrorBoundary` 组件包裹路由区 |
| 中 | `vite.config.ts` | `sourcemap: true` 生产产物泄露原始 TS 源码 | 改 `false` |
| 低 | `App.tsx` | 死代码 useEffect（`void location; void navigate`）、未知路由静默进对话页 | 删除死代码，加 `NotFound` 页 |

### 痛点②（UI 乱码）修复评估：彻底

CJK 字体栈三层注入、无 CDN 依赖（lucide-react 本地打包）、显式 UTF-8 API、Markdown 经 rehype-sanitize 白名单、无 `dangerouslySetInnerHTML`——全部到位。

### 痛点③ 前端侧评估：达标

URL 为真相源（`/chat/:sessionId`）、刷新可恢复（useEffect 按 URL 重载）、Zustand 不 persist 但靠 API 重取即可恢复。

### 仍存在的前端限制

- `useChatStore()` 无 selector 订阅整个 store，流式时性能差（每个 token 重渲染）
- `streamingMsgId` 模块级全局变量，流式中切会话可能状态错乱
- 移动端侧边栏隐藏无替代入口
- `SettingsPage` 用浏览器原生 `confirm()`

## 修复验证

修复后全量回归测试结果：

```
Go:   go vet ./... 零警告
      go test -count=1 ./... 全绿（agent/llm/memory/paper/server/store 6 包）
Rust: cargo test --lib  19 passed; 0 failed
      cargo build        编译通过
前端: tsc --noEmit       零错误
      vite build         成功（524KB / gzip 166KB）
```

## 未修复项汇总（按优先级）

| 优先级 | 项 | 说明 |
|---|---|---|
| P0 | API 鉴权 | 当前仅 Host 改 127.0.0.1，无 token 中间件；公网暴露需补 |
| P0 | 日预算强制 | `DailyBudgetUSD` 未检查，可被烧光 |
| P1 | 自动梦境定时器 | spec §5.3 `dreamIntervalHours` 未实现 |
| P1 | memory_handlers server 级测试 | 11 端点仅 client 层测试 |
| P1 | 真流式 | 当前伪流式（整段返回再切块） |
| P2 | llm_cache 淘汰 | 无 TTL/LRU，无界增长 |
| P2 | reasoning_content 落库 | reasoner 模型场景 |
| P2 | DB 索引 | papers.topic_id 等无索引 |
| P3 | 移动端侧边栏 | 小屏无入口 |
| P3 | store selector 细化 | 流式性能 |
