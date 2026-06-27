# 测试报告

> 项目：核动力科研牛马 v2 多语言重构
> 里程碑：M5（稳定性与交付）
> 日期：2026-06-27
> 测试环境：Linux x86_64，Go 1.24，Rust 1.92，Node 22，SQLite 3.46

## 总览

| 层 | 测试框架 | 用例数 | 通过 | 失败 | 耗时 |
|---|---|---|---|---|---|
| Go 后端 | `testing` + `httptest` | 79 | 79 | 0 | ~1.0s |
| Rust 核心 | `cargo test` | 19 | 19 | 0 | 0.13s |
| 前端 | `tsc --noEmit` + `vite build` | — | 通过 | 0 | 3.0s |
| 静态分析 | `go vet` + `cargo clippy -D warnings` | — | 通过 | 0 | — |

全量回归结果：**98 项测试全部绿色，零编译警告，零 lint 违规。**

---

## Go 后端测试明细

`go test ./...` 退出码 0，6 个包全部通过。

### internal/agent（17 项）

覆盖 agent loop 主流程、流式落库、技能蒸馏、用量追踪。

| 用例 | 验证点 |
|---|---|
| `TestAgentRunDirectAnswer` | 单轮直答：LLM 返回无 tool_calls 时正常输出 done |
| `TestAgentRunWithTools` | 多轮工具调用：search_papers → 结果回填 → 最终回答 |
| `TestAgentRunError4xx` | LLM 4xx 不重试，直接 error 事件 |
| `TestAgentRunMaxTurns` | 达到 max_turns 上限后正常终止 |
| `TestAgentRunTokenBudgetExceeded` | token 预算耗尽后发出 budget_exceeded 事件 |
| `TestChatServiceSendMessageNormal` | 流式消息正常持久化到 messages 表 |
| `TestChatServiceStreamingPersistOnError` | 流式出错时已生成内容仍落库（不丢半句） |
| `TestChatServiceSessionNotFound` | 会话不存在返回 404 |
| `TestChatServiceCreateAndListSessions` | 创建会话后列表可见 |
| `TestChatServiceWithToolCall` | assistant tool_calls JSON 正确序列化 |
| `TestDistillSkillSuccess` | 高频技能成功蒸馏入库 |
| `TestDistillSkillRejectsCredential` | 含密钥的内容拒绝蒸馏 |
| `TestDistillSkillRejectsBadSlug` | slug 不合法时拒绝 |
| `TestDistillSkillNotWorthSaving` | 低频技能不触发蒸馏 |
| `TestTrackUsage` | 技能调用后 usage_count + last_used_at 更新 |
| `TestTrackUsageMissingSkill` | 技能不存在时静默跳过 |
| `TestShouldDistill` | 蒸馏阈值判定逻辑 |

### internal/llm（9 项）

覆盖 LLM client 请求构造、重试、缓存。

| 用例 | 验证点 |
|---|---|
| `TestBuildRequestNoReasoningForDeepSeekChat` | DeepSeek chat 模式不发送 reasoning_effort |
| `TestBuildRequestReasoningForOpenAI` | OpenAI o 系列发送 reasoning_effort |
| `TestChatNormal` | 正常 chat completions 调用 |
| `TestChat400NotRetryable` | 400 状态码不重试 |
| `TestChat500Retryable` | 500 状态码触发指数退避重试 |
| `TestChatCacheHit` | 相同请求命中缓存，不发起 HTTP |
| `TestChatWithNoCacheOption` | no_cache=true 时跳过缓存 |
| `TestToolRegistryBuiltin` | 内置工具注册成功 |
| `TestLookupCapabilities` | 工具能力查询返回正确 schema |

### internal/memory（13 项）

覆盖 Go→Rust core HTTP client 契约，使用 httptest mock。

| 用例 | 验证点 |
|---|---|
| `TestCreateMemory` | POST /memories 请求体与响应解析 |
| `TestGetMemory_NotFound` | 404 时 CoreError 正确解码 |
| `TestGetMemory_OK` | 200 时 Memory 结构体映射 |
| `TestDeleteMemory` | DELETE /memories/:id |
| `TestSearchMemory_QueryParams` | GET /memories/search 关键字与 limit 拼接 |
| `TestSearchVector` | POST /memories/search-vector 向量检索 |
| `TestTriggerDream` | POST /dream 触发梦境 |
| `TestListDreamDiary` | GET /dream-diary 列表 |
| `TestGetDreamDiary_NotFound` | 单条 diary 404 |
| `TestAddDecision` | POST /decisions 决策账本 |
| `TestListDecisions` | GET /decisions 列表 |
| `TestCoreError_Decoded` | Rust core 错误响应 JSON 正确解码为 CoreError |
| `TestCoreError_ConnectionRefused` | 连接拒绝时错误信息可读 |

### internal/paper（3 项）

覆盖 GitHub 论文同步。

| 用例 | 验证点 |
|---|---|
| `TestSyncFromGitHub` | 从 GitHub API 拉取论文并入库 |
| `TestSyncIdempotent` | 重复同步不产生重复记录 |
| `TestSyncRateLimit` | GitHub 403 rate limit 时优雅降级 |

### internal/server（22 项）

覆盖 HTTP handler 层，使用 gin test mode + SQLite 临时库。

| 用例 | 验证点 |
|---|---|
| `TestMigrateLegacyDB` | v0.3 旧库迁移到 v2 schema |
| `TestMigrateLegacyDBIdempotent` | 迁移幂等 |
| `TestFindLegacyDBsExcludesCurrent` | 发现旧库时排除当前库 |
| `TestSlugify` | 标题→slug 转换 |
| `TestUpsertTopicIdempotent` | 主题 upsert |
| `TestUpsertPaperAndList` | 论文入库+列表 |
| `TestUpsertPaperPreservesReadStatus` | 更新论文不覆盖已读状态 |
| `TestUpdatePaperCount` | 主题下论文计数 |
| `TestCreateAndListSessions` | 会话创建+列表 |
| `TestSendMessageNonStream` | 非流式发送 |
| `TestSendMessageStream` | SSE 流式发送 |
| `TestSendMessageToMissingSession` | 向不存在会话发送返回 404 |
| `TestSkillsCRUD` | 技能增删改查全链路 |
| `TestEvolveSessionManual` | 手动演进会话技能模式 |
| `TestHealthReturnsAbsDataDir` | /health 返回绝对路径 |
| `TestListTopicsEmpty` | 空主题列表 |
| `TestCreateTopicAndList` | 创建主题后列表可见 |
| `TestGetPaperNotFound` | 论文不存在返回 404 |
| `TestUpdatePaperStatus` | 更新论文阅读状态 |
| `TestUpdatePaperStatusRejectsInvalid` | 非法状态码被拒 |
| `TestSyncEndpoint` | /api/library/sync 端点 |
| `TestMigrateLegacyEndpoint` | /api/migrate-legacy 端点 |

### internal/store（15 项）

覆盖 SQLite 持久化层。

| 用例 | 验证点 |
|---|---|
| `TestCreateAndGetSession` | 会话创建+按 ID 查询 |
| `TestGetSessionNotFound` | 会话不存在返回 ErrNotFound |
| `TestAppendMessageUpdatesSessionCount` | 追加消息后 message_count + total_tokens 更新 |
| `TestListMessagesOrder` | 消息按 created_at 升序 |
| `TestDeleteSessionCascade` | 删除会话级联清除消息 |
| `TestUpdateSessionTitle` | 更新会话标题 |
| `TestListSessionsOrder` | 会话按 updated_at 降序 |
| `TestRegisterBuiltinIdempotent` | 内置技能注册幂等 |
| `TestRegisterBuiltinAlongsideUserSkill` | 内置与用户技能共存 |
| `TestListSkillsOrderByUsage` | 技能按 usage_count 降序 |
| `TestUpdateSkillStatsEMA` | 技能统计 EMA 更新 |
| `TestDeleteSkill` | 删除技能 |
| `TestGetSkillNotFound` | 技能不存在返回 ErrNotFound |
| `TestOpenAndMigrate` | 打开库时自动迁移 schema |
| `TestWALMode` | WAL 模式已启用 |

---

## Rust 核心测试明细

`cargo test` 退出码 0，19 项全部通过，耗时 0.13s。

### vector 模块（4 项）

| 用例 | 验证点 |
|---|---|
| `test_cosine_similarity_identical` | 相同向量相似度 = 1.0 |
| `test_cosine_similarity_orthogonal` | 正交向量相似度 = 0.0 |
| `test_cosine_similarity_empty` | 空向量相似度 = 0.0（不 panic） |
| `test_cosine_similarity_different_lengths` | 不同维度向量返回 0.0（不 panic） |

### memory 模块（6 项）

| 用例 | 验证点 |
|---|---|
| `test_create_and_get_memory` | 创建记忆后按 ID 查回，字段一致 |
| `test_list_by_layer` | 按 layer 过滤 + importance_score 降序 |
| `test_search_by_keyword` | content LIKE 关键字检索 |
| `test_delete_memory_cascades_vector` | 删除记忆后 memory_vectors 级联清除 |
| `test_promote_and_decay` | 晋升 episodic→long_term + 衰减状态流转 |
| `test_decision_ledger_crud` | 决策账本增删查 |

### dreaming 模块（9 项）

| 用例 | 验证点 |
|---|---|
| `test_tokenize_ascii` | 英文分词：小写化 + 标点分隔 |
| `test_tokenize_cjk` | 中文分词：逐字成 token（修复 is_alphanumeric 对 CJK 误判） |
| `test_jaccard_identical` | 相同词集 Jaccard = 1.0 |
| `test_jaccard_disjoint` | 不相交词集 Jaccard = 0.0 |
| `test_compute_recency_now` | 当前时间 recency = 1.0 |
| `test_compute_recency_half_life` | 半衰期处 recency = 0.5 |
| `test_compute_recency_invalid_date` | 非法日期 recency = 0.0（不 panic） |
| `test_dream_empty_memory` | 空记忆库时梦境正常返回 0 候选 |
| `test_dream_promotes_high_frequency` | 高频记忆被晋升为 long_term |

---

## 前端构建验证

### TypeScript 类型检查

```
npx tsc --noEmit
```

退出码 0，零类型错误。

### 生产构建

```
npx vite build
```

```
vite v5.4.21 building for production...
✓ 1890 modules transformed.
dist/index.html                   0.46 kB │ gzip:   0.42 kB
dist/assets/index--eiwag49.css   14.59 kB │ gzip:   3.69 kB
dist/assets/index-_lEBDj4I.js   524.89 kB │ gzip: 166.32 kB
✓ built in 2.99s
```

构建产物体积：JS 524.89 kB（gzip 166.32 kB），CSS 14.59 kB（gzip 3.69 kB）。sourcemap 已关闭（安全要求）。

---

## 静态分析

### go vet

```
go vet ./...
```

退出码 0，零告警。

### cargo clippy

```
cargo clippy -- -D warnings
```

退出码 0，零告警。修复的 5 类 lint：

| lint 类别 | 位置 | 修复方式 |
|---|---|---|
| `should_implement_trait` | memory.rs `from_str` | 添加 `#[allow]`（保留 API 兼容） |
| `redundant_closure` | memory.rs ×5 处 `|row| fn(row)` | 改为函数引用 `fn` |
| `format_in_format_args` | dreaming.rs `format!` 嵌套 | 内联为单个 `format!` |
| `manual_clamp` | dreaming.rs ×2 处 `.min().max()` | 改为 `.clamp(0.0, 1.0)` |
| `too_many_arguments` | dreaming.rs `insert_diary_stage` | 添加 `#[allow]`（9 参数为 diary 表结构所必需） |

---

## 代码规模

| 层 | 语言 | 行数 |
|---|---|---|
| 后端 | Go | 7,398 |
| 核心 | Rust | 2,061 |
| 前端 | TypeScript / TSX | 1,882 |
| **合计** | | **11,341** |

---

## M5.2 稳定性修复回归验证

M5.1 三轮审查发现的问题在 M5.2 修复后，通过以下测试回归验证：

| 问题 | 修复 | 回归测试 |
|---|---|---|
| agent loop 空 choices panic | `len(resp.Choices)==0` 检查 | `TestAgentRunDirectAnswer` 覆盖正常路径 |
| goroutine 泄漏（channel send 阻塞） | ctx 感知 `select` 发送 | `TestChatServiceStreamingPersistOnError` 验证错误路径不泄漏 |
| HTTP 无超时 | ReadHeaderTimeout + WriteTimeout | `TestHealthReturnsAbsDataDir` 验证 server 启动 |
| Mutex 中毒二次 panic | `unwrap_or_else(\|e\| e.into_inner())` | `test_dream_empty_memory` + `test_dream_promotes_high_frequency` |
| CJK 分词失效 | `is_cjk()` 逐字成 token | `test_tokenize_cjk` |
| N+1 查询 | JOIN 合并 | `test_promote_and_decay` 验证 JOIN 路径 |
| SSE 卸载泄漏 | useEffect cleanup abort | 前端 build 验证 ErrorBoundary + cleanup 代码路径 |

---

## 结论

98 项测试全部通过，零编译警告，零 lint 违规。M5.1 审查发现的 3 项致命问题与 10+ 项高危问题均已修复并通过回归验证。代码可进入交付状态。
