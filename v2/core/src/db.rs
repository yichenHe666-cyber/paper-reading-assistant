//! SQLite 数据库连接与 dream_diary 表管理。
//!
//! 与 Go 后端共用同一 SQLite 文件：
//!   - Go store.Migrate 已建 memories / decision_ledger 表，本模块只读；
//!   - 本模块启动时补建 dream_diary 表（spec §5.4），仅 Rust 写入；
//!   - 启用 WAL 与外键（Go 侧已启用，但本连接独立设置以保险）。
//!
//! 并发模型：rusqlite::Connection 非线程安全，用 Mutex 包裹。
//! SQLite 单写多读 + WAL，并发度有限但够用（core 仅被 Go 单实例调用）。

use std::sync::Mutex;

use anyhow::Result;
use rusqlite::Connection;

/// 数据库句柄。Connection 包裹在 Mutex 中以满足 Send + Sync。
#[derive(Debug)]
pub struct Db {
    conn: Mutex<Connection>,
}

impl Db {
    /// 打开 SQLite 文件并启用 WAL + 外键。
    pub fn open(path: &str) -> Result<Self> {
        let conn = Connection::open(path)?;
        conn.execute_batch(
            "PRAGMA journal_mode=WAL;\
             PRAGMA foreign_keys=ON;\
             PRAGMA busy_timeout=5000;",
        )?;
        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    /// 补建 dream_diary 表（spec §5.4）与 memory_vectors 表（向量存储）。
    ///
    /// dream_diary：记录每次梦境整合的日志——审查了哪些记忆、哪些升级、哪些衰减、新建了哪些关联。
    /// 前端 Dream Diary 页面据此展示，便于调试"为何忘记"。
    ///
    /// memory_vectors：存储 embedding 向量（与 memories.embedding_id 关联）。
    /// 首期不引入专门向量库，向量与元数据同存 SQLite，相似度检索用 brute-force cosine。
    pub fn ensure_dream_diary_table(&self) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS dream_diary (
                id              TEXT PRIMARY KEY,
                run_id          TEXT NOT NULL DEFAULT '', -- 同一次梦境的关联 id（light/rem/deep/done 共用）
                started_at      TEXT NOT NULL,
                finished_at     TEXT,
                stage           TEXT NOT NULL,         -- light / rem / deep / done
                reviewed_count  INTEGER DEFAULT 0,     -- 审查的记忆数
                promoted_count  INTEGER DEFAULT 0,     -- 升级为长期记忆数
                decayed_count   INTEGER DEFAULT 0,     -- 衰减数
                summary         TEXT DEFAULT '',       -- 本次梦境摘要
                details_json    TEXT DEFAULT ''        -- 详细日志 JSON（候选列表/评分/原因）
            );
            CREATE INDEX IF NOT EXISTS idx_dream_diary_run_id ON dream_diary(run_id);
            CREATE TABLE IF NOT EXISTS memory_vectors (
                id              TEXT PRIMARY KEY,       -- 与 memories.embedding_id 一致
                memory_id       TEXT NOT NULL,          -- 关联 memories.id
                vector          TEXT NOT NULL,          -- JSON 数组 [f32]
                created_at      TEXT DEFAULT (datetime('now'))
            );",
        )?;
        Ok(())
    }

    /// 获取连接的闭包式访问，避免外部直接 lock。
    pub fn with_conn<F, T>(&self, f: F) -> T
    where
        F: FnOnce(&Connection) -> T,
    {
        let conn = self.conn.lock().unwrap();
        f(&conn)
    }
}

// 用于 axum State 的派生
// 手动 impl Clone 不现实（Mutex 不可 Clone），通过 Arc<Db> 共享。
