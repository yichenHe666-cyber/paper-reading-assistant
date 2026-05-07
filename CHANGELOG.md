# 更新日志

## [v0.3.0] — 2026-05-07

### ✨ 新增模块

#### 智能体对话系统
- 新增智能体对话引擎 `chat_engine.py`，支持多轮上下文感知对话
- 新增 `agent_chat.py` 前端视图，提供类似 ChatGPT 的交互界面
- 支持技能模式自动切换（auto/manual）
- 支持流式输出（SSE）
- 上下文管理与压缩：`context_manager.py` + `context_compressor.py`，支持 sliding_window / summary / hybrid 三种压缩策略

#### 知识库引擎
- 新增完整知识库系统：`knowledge_engine/` 五个核心模块
  - `extractor.py` — 知识提取
  - `concept_linker.py` — 概念链接
  - `graph_builder.py` — 知识图谱构建
  - `wiki_compiler.py` — Wiki 编译
  - `context_query.py` — 上下文查询
- 新增知识库 API 路由和前端视图
- 支持自动提取与去重

#### 科研记忆系统
- 新增多组件记忆引擎：
  - `memory_engine.py` — 记忆主引擎
  - `memory_entity_engine.py` — 实体引擎
  - `memory_vectorizer.py` — 向量化（支持 auto/ollama/openai）
  - `memory_observer.py` — 记忆观察器（自动合并与去重）
  - `memory_reflector.py` — 记忆反思器（LLM 驱动的推理合并）
  - `memory_distiller.py` — 记忆蒸馏
- 支持语义搜索、关键词搜索、实体搜索三维权重融合
- 记忆面板前端视图

#### 技能管理
- 新增 `skill_manager.py` + `skill_executor.py` 技能管理引擎
- 技能 CRUD 路由和前端管理界面
- 支持技能模板导入/导出

#### 工作空间管理
- 新增 `workspace_service.py` + `sandbox_service.py`
- 工作空间 CRUD、沙盒执行与超时控制
- 前端工作空间管理视图

#### 文档解析器集合
- 新增 `document_parser/` 统一解析框架：
  - `pdf_parser.py` — PyMuPDF 解析 + 乱码检测
  - `docx_parser.py` — python-docx 解析
  - `epub_parser.py` — ebooklib 解析
  - `markdown_parser.py` — 原生 Markdown 解析
  - `latex_parser.py` — 正则提取 LaTeX 内容
- `models.py` — 统一的解析结果数据模型

#### 其他新增模块
- 搜索路由 `search_router.py` + 搜索质量评估 `search_quality.py`
- 规则管理系统：`rule_service.py` + `rules.py` 路由 + 前端编辑器
- 函数调用路由 `function_caller.py` + 命令路由 `command_router.py`
- ClawHub 客户端集成 `clawhub_client.py`
- PDF 下载器 `pdf_fetcher.py` + PDF 链接解析器 `pdf_resolver.py`
- 增量同步 `incremental_sync.py`
- 数据质量检查 `data_quality.py`
- 备份服务 `backup.py`（自动备份数据库）

### 🔧 修复的问题

#### UI 组件错误
- **badge() 参数错误**：修复 `badge()` 函数不支持 `size` 参数的问题。`rule_editor.py` 和 `workspace_manager.py` 中误传了 `size="xs"`，导致 `TypeError: badge() got an unexpected keyword argument 'size'`。已将 4 处调用移除无效参数。
- **icon() 在原生组件中显示原始 HTML**：`icon()` 返回的 HTML 字符串被放在 `st.selectbox`、`st.info()`、`st.success()` 等不支持 HTML 渲染的组件中，导致显示 `<i class="fas fa-pen" ...>` 原始标签。已将 4 处修复为 emoji 替代（`settings.py`、`recommend.py`、`obsidian_panel.py`）。

#### 日志系统全面修复
- **无文件持久化**：日志仅输出到控制台和 SQLite，进程崩溃后日志完全丢失。新增 `RotatingFileHandler` 写入 `logs/paper_reader.log`。
- **无日志轮转**：日志文件无限增长。新增按大小轮转机制（默认 5MB，保留 5 个历史文件）。
- **无级别配置**：日志级别硬编码为 `INFO`。新增 `LOG_LEVEL` 环境变量支持。
- **无 shutdown 事件**：系统关闭无任何记录。新增 `@app.on_event("shutdown")` 记录关闭时间。
- **异常无堆栈跟踪**：所有 `logger.warning("...: %s", e)` 不含调用栈。7 处关键异常点改用 `logger.exception()` 自动附加完整 traceback。
- **极端情况容错**：新增 `_StderrFallbackHandler`，文件日志写入失败时自动降级到 stderr。
- **文件操作无日志**：笔记写入、配置修改、备份创建均无声。新增 5 处关键 I/O 路径日志记录。

#### 其他修复
- 更新 `app/main.py` 中多处版本号统一为 v0.3.0（原 API 返回 v0.2.0、print 语句 v0.2.0 等）

### 📦 配置变更
- `config.py` 新增日志配置项：`LOG_LEVEL`、`LOG_DIR`、`LOG_FILE_MAX_BYTES`、`LOG_FILE_BACKUP_COUNT`
- `.env.example` 新增日志配置段注释说明
- 全面扩展 `config.py` 配置项（记忆系统、知识库、沙盒、LLM 推理强度等）

### 🧪 测试
- 新增 `tests/test_logging.py` — 20 个测试用例覆盖日志配置、级别过滤、文件轮转、异常追溯、stderr fallback
- 新增 `tests/test_snapshot_manager.py` — 快照管理测试
- 新增 `tests/test_knowledge_api.py` — 知识库 API 测试
- 新增 `tests/test_knowledge_engine.py` — 知识引擎测试
- 新增 `tests/test_document_parser.py` — 文档解析器测试（含乱码检测）
