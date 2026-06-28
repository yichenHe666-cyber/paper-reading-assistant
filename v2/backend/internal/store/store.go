// Package store 提供 SQLite 持久化层。
//
// 文件概述：store.go 负责 SQLite 连接管理（Open）、表结构迁移（Migrate）与基础查询。
//
// 关键设计：
//   - 数据库路径由 config 层绝对化后传入，本层不再处理相对路径（痛点②修复）。
//   - 启用 WAL 模式提升并发读写性能。
//   - 使用纯 Go 驱动 modernc.org/sqlite，避免 cgo 依赖，便于跨平台编译与 Docker 构建。
//   - Migrate 采用 CREATE TABLE IF NOT EXISTS + 幂等 ALTER，绝不删除已有数据
//     （旧 Python 版 init_db 同样不删表，数据丢失纯因路径漂移而非建表逻辑）。
package store

import (
	"database/sql"
	"fmt"
	"log"

	// 注册纯 Go 的 SQLite 驱动，import 别名供 database/sql 使用。
	// 注意：modernc.org/sqlite v1.x 注册的驱动名为 "sqlite"（非 "sqlite3"），
	// "sqlite3" 是 mattn/go-sqlite3（cgo 版）的驱动名，二者不可混用。
	_ "modernc.org/sqlite"
)

// Open 打开（必要时创建）SQLite 数据库文件并启用 WAL 模式。
// dbPath 必须为绝对路径（由 config 层保证）。
func Open(dbPath string) (*sql.DB, error) {
	// 驱动名 "sqlite" 来自 modernc.org/sqlite；DSN 用文件路径。
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("打开数据库失败: %w", err)
	}
	// SQLite 单写多读，连接池设置避免锁竞争
	db.SetMaxOpenConns(1)

	// 启用 WAL 模式：提升读写并发，降低写入锁阻塞
	if _, err := db.Exec("PRAGMA journal_mode=WAL;"); err != nil {
		db.Close()
		return nil, fmt.Errorf("启用 WAL 失败: %w", err)
	}
	// 外键约束开启
	if _, err := db.Exec("PRAGMA foreign_keys=ON;"); err != nil {
		db.Close()
		return nil, fmt.Errorf("启用外键约束失败: %w", err)
	}
	return db, nil
}

// columnExists 检查指定表是否已包含某列。
// 用于 ALTER TABLE ADD COLUMN 的幂等检查（SQLite 的 ADD COLUMN 不支持 IF NOT EXISTS）。
func columnExists(db *sql.DB, table, column string) (bool, error) {
	// 注意：table 参数均为内部硬编码常量，不存在 SQL 注入风险；
	// 且 PRAGMA 语句不支持参数绑定，故用 fmt.Sprintf 拼接。
	rows, err := db.Query(fmt.Sprintf("PRAGMA table_info(%s);", table))
	if err != nil {
		return false, err
	}
	defer rows.Close()
	for rows.Next() {
		var (
			cid     int
			name    string
			ctype   string
			notnull int
			dflt    sql.NullString
			pk      int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			return false, err
		}
		if name == column {
			return true, nil
		}
	}
	return false, rows.Err()
}

// addColumnIfMissing 幂等地为表添加列：列已存在则跳过，否则执行 ALTER TABLE ADD COLUMN。
// columnDef 形如 "TEXT DEFAULT ''" 或 "INTEGER DEFAULT 0"。
func addColumnIfMissing(db *sql.DB, table, column, columnDef string) error {
	exists, err := columnExists(db, table, column)
	if err != nil {
		return fmt.Errorf("检查列 %s.%s 失败: %w", table, column, err)
	}
	if exists {
		return nil
	}
	log.Printf("迁移：为表 %s 新增列 %s %s", table, column, columnDef)
	stmt := fmt.Sprintf("ALTER TABLE %s ADD COLUMN %s %s;", table, column, columnDef)
	if _, err := db.Exec(stmt); err != nil {
		return fmt.Errorf("ALTER TABLE %s ADD COLUMN %s 失败: %w", table, column, err)
	}
	return nil
}

// Migrate 创建/升级表结构。全部使用 IF NOT EXISTS，幂等且不破坏已有数据。
func Migrate(db *sql.DB) error {
	// topics：论文主题分类（对应 Papers We Love 仓库顶层目录）
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS topics (
	id          TEXT PRIMARY KEY,            -- 主题 id（由目录名生成）
	name        TEXT NOT NULL,               -- 原始目录名
	name_cn     TEXT DEFAULT '',             -- 中文名称
	paper_count INTEGER DEFAULT 0,           -- 该主题下论文数
	created_at  TEXT DEFAULT (datetime('now'))
);`); err != nil {
		return fmt.Errorf("建表 topics 失败: %w", err)
	}

	// papers：论文元数据
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS papers (
	id            TEXT PRIMARY KEY,          -- 稳定 id（topic/slug 派生）
	title         TEXT NOT NULL,             -- 标题
	authors       TEXT DEFAULT '',           -- 作者（逗号分隔）
	year          INTEGER,                   -- 发表年份
	topic_id      TEXT,                      -- 所属主题
	pdf_url       TEXT DEFAULT '',           -- PDF 下载地址
	doi           TEXT DEFAULT '',           -- DOI
	abstract      TEXT DEFAULT '',           -- 摘要
	read_status   TEXT DEFAULT 'unread',     -- 阅读状态：unread/reading/done/reread
	obsidian_path TEXT DEFAULT '',           -- Obsidian 笔记路径
	created_at    TEXT DEFAULT (datetime('now')),
	FOREIGN KEY (topic_id) REFERENCES topics(id)
);`); err != nil {
		return fmt.Errorf("建表 papers 失败: %w", err)
	}

	// papers 表的增量字段：论文来源/分类/阅读统计等。
	// SQLite 的 ALTER TABLE ADD COLUMN 不支持 IF NOT EXISTS，需先查 pragma table_info 判断列是否存在，
	// 旧库已有数据时不会重置已有行——新增列自动取 DEFAULT 值。
	// 注意：保留原有 topic_id 等字段不动，只做增量升级。
	paperColumns := []struct {
		name string
		def  string
	}{
		{"source", "TEXT DEFAULT ''"},
		{"venue", "TEXT DEFAULT ''"},
		{"level", "TEXT DEFAULT ''"},
		{"paper_type", "TEXT DEFAULT ''"},
		{"sub_domain", "TEXT DEFAULT ''"},
		{"difficulty_score", "INTEGER DEFAULT 5"},
		{"tags", "TEXT DEFAULT '[]'"},
		{"ai_classified", "INTEGER DEFAULT 0"},
		{"company", "TEXT DEFAULT ''"},
		{"github_repo", "TEXT DEFAULT ''"},
		{"last_read_at", "TEXT DEFAULT ''"},
		{"total_read_seconds", "INTEGER DEFAULT 0"},
		// arxiv_id 不在任务明确列出的字段清单内，但 idx_papers_arxiv_id 索引依赖该列，
		// 故一并补齐（若已存在则跳过），否则建索引会失败。
		{"arxiv_id", "TEXT DEFAULT ''"},
	}
	for _, c := range paperColumns {
		if err := addColumnIfMissing(db, "papers", c.name, c.def); err != nil {
			return err
		}
	}

	// chat_sessions：智能体对话会话
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS chat_sessions (
	id               TEXT PRIMARY KEY,
	title            TEXT DEFAULT '',
	skill_mode       TEXT DEFAULT 'auto',    -- auto/manual/hybrid
	enabled_skill_ids TEXT DEFAULT '[]',     -- JSON 数组
	total_tokens     INTEGER DEFAULT 0,
	message_count    INTEGER DEFAULT 0,
	created_at       TEXT DEFAULT (datetime('now')),
	updated_at       TEXT DEFAULT (datetime('now'))
);`); err != nil {
		return fmt.Errorf("建表 chat_sessions 失败: %w", err)
	}

	// chat_messages：对话消息
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS chat_messages (
	id                 TEXT PRIMARY KEY,
	session_id         TEXT NOT NULL,
	role               TEXT NOT NULL,        -- user/assistant/system/tool
	content            TEXT DEFAULT '',
	reasoning_content  TEXT DEFAULT '',      -- 推理模型专属
	tool_calls         TEXT DEFAULT '',      -- JSON：函数调用
	tool_call_id       TEXT DEFAULT '',
	token_count        INTEGER DEFAULT 0,
	context_usage_pct  REAL DEFAULT 0,
	created_at         TEXT DEFAULT (datetime('now')),
	FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);`); err != nil {
		return fmt.Errorf("建表 chat_messages 失败: %w", err)
	}

	// skills：技能（含自进化字段，见 spec §6）
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS skills (
	id               TEXT PRIMARY KEY,
	slug             TEXT UNIQUE NOT NULL,   -- 唯一标识，用于 upsert
	name             TEXT NOT NULL,
	description      TEXT DEFAULT '',
	content          TEXT DEFAULT '',        -- 技能 prompt/指令内容
	enabled          INTEGER DEFAULT 1,
	level            INTEGER DEFAULT 0,      -- 渐进式披露层级：0/1/2
	usage_count      INTEGER DEFAULT 0,      -- 使用次数（自进化评估）
	success_rate     REAL DEFAULT 0,         -- 成功率
	version          INTEGER DEFAULT 1,      -- 技能版本
	last_improved_at TEXT DEFAULT '',
	created_at       TEXT DEFAULT (datetime('now'))
);`); err != nil {
		return fmt.Errorf("建表 skills 失败: %w", err)
	}

	// memories：五层记忆（见 spec §5.1）
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS memories (
	id              TEXT PRIMARY KEY,
	layer           TEXT NOT NULL,           -- episodic/long_term/procedural/index
	content         TEXT NOT NULL,
	importance_score REAL DEFAULT 0,         -- 重要性评分（梦境整合用）
	decay_state     TEXT DEFAULT 'active',   -- active/decaying/promoted
	embedding_id    TEXT DEFAULT '',         -- 关联向量 id（Rust core 侧）
	created_at      TEXT DEFAULT (datetime('now'))
);`); err != nil {
		return fmt.Errorf("建表 memories 失败: %w", err)
	}

	// decision_ledger：决策账本（见 spec §5.5）
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS decision_ledger (
	id         TEXT PRIMARY KEY,
	context    TEXT DEFAULT '',
	decision   TEXT NOT NULL,
	rationale  TEXT DEFAULT '',
	outcome    TEXT DEFAULT '',
	created_at TEXT DEFAULT (datetime('now'))
);`); err != nil {
		return fmt.Errorf("建表 decision_ledger 失败: %w", err)
	}

	// llm_calls / cost_logs：LLM 调用与成本追踪（沿用旧 cost_tracker 思路）
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS llm_calls (
	id              TEXT PRIMARY KEY,
	provider        TEXT,
	model           TEXT,
	prompt_tokens   INTEGER DEFAULT 0,
	completion_tokens INTEGER DEFAULT 0,
	total_tokens    INTEGER DEFAULT 0,
	cost_usd        REAL DEFAULT 0,
	created_at      TEXT DEFAULT (datetime('now'))
);`); err != nil {
		return fmt.Errorf("建表 llm_calls 失败: %w", err)
	}

	// llm_cache：LLM 响应持久化缓存（替代 Redis，见 spec §2.3）
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS llm_cache (
	cache_key TEXT PRIMARY KEY,              -- 请求指纹
	response  TEXT NOT NULL,                 -- 缓存的响应 JSON
	created_at TEXT DEFAULT (datetime('now'))
);`); err != nil {
		return fmt.Errorf("建表 llm_cache 失败: %w", err)
	}

	// sources：论文数据源登记（arxiv/openalex/acl/company 等）
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS sources (
	id              TEXT PRIMARY KEY,
	name            TEXT NOT NULL,
	source_type     TEXT NOT NULL,
	enabled         INTEGER DEFAULT 1,
	last_synced_at  TEXT DEFAULT '',
	sync_count      INTEGER DEFAULT 0,
	config          TEXT DEFAULT '{}'
);`); err != nil {
		return fmt.Errorf("建表 sources 失败: %w", err)
	}

	// paper_tags：论文-标签多对多关联（与 papers.tags JSON 列互补，便于按标签检索）
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS paper_tags (
	paper_id        TEXT NOT NULL,
	tag             TEXT NOT NULL,
	PRIMARY KEY (paper_id, tag)
);`); err != nil {
		return fmt.Errorf("建表 paper_tags 失败: %w", err)
	}

	// reading_history：论文阅读会话记录（start/end/duration，支撑阅读时长统计）
	if _, err := db.Exec(`
CREATE TABLE IF NOT EXISTS reading_history (
	id               TEXT PRIMARY KEY,
	paper_id         TEXT NOT NULL,
	start_time       TEXT NOT NULL,
	end_time         TEXT DEFAULT '',
	duration_seconds INTEGER DEFAULT 0,
	FOREIGN KEY (paper_id) REFERENCES papers(id)
);`); err != nil {
		return fmt.Errorf("建表 reading_history 失败: %w", err)
	}

	// 索引：加速按来源/级别/子领域/类型/arxiv_id 检索论文，以及按论文检索阅读历史。
	// CREATE INDEX IF NOT EXISTS 自身幂等，无需额外检查。
	indexes := []string{
		`CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);`,
		`CREATE INDEX IF NOT EXISTS idx_papers_level ON papers(level);`,
		`CREATE INDEX IF NOT EXISTS idx_papers_sub_domain ON papers(sub_domain);`,
		`CREATE INDEX IF NOT EXISTS idx_papers_paper_type ON papers(paper_type);`,
		`CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);`,
		`CREATE INDEX IF NOT EXISTS idx_reading_history_paper ON reading_history(paper_id);`,
	}
	for _, idx := range indexes {
		if _, err := db.Exec(idx); err != nil {
			return fmt.Errorf("创建索引失败 (%s): %w", idx, err)
		}
	}

	return nil
}
