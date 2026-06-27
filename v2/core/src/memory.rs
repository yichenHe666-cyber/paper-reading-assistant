//! 记忆引擎：五层存储 CRUD + 相似度检索 + Decision Ledger。
//!
//! spec §5.1 五层记忆架构：
//!   - 工作记忆：进程内（Go 侧上下文窗口），不持久化，本模块不涉及；
//!   - 情景记忆：episodic，交互事件/经历，存 memories 表；
//!   - 长期记忆：long_term，事实/决策/人物/里程碑，存 memories 表（与 episodic 同表，layer 区分）；
//!   - 程序记忆：procedural，工作流/偏好/工具模式，复用 skills 表（Go 侧管理）；
//!   - 索引记忆：index，元数据/重要性分数/关系，存 memories 表（layer=index）。
//!
//! 检索策略：
//!   - 按 layer + 关键字 LIKE 检索（精确匹配）；
//!   - 按向量相似度检索（brute-force cosine，扫描 memory_vectors 全表，小规模足够）；
//!   - 前者快，后者准；上层（dreaming）用向量去重，agent 用关键字初筛 + 向量精排。

use std::sync::Arc;

use anyhow::Result;
use rusqlite::params;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::db::Db;
use crate::vector::{cosine_similarity, EmbeddingClient};

/// 记忆层级。对应 memories.layer 字段。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MemoryLayer {
    /// 情景记忆：交互事件/经历
    Episodic,
    /// 长期记忆：事实/决策/人物/里程碑
    LongTerm,
    /// 索引记忆：元数据/重要性分数/关系
    Index,
}

impl MemoryLayer {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Episodic => "episodic",
            Self::LongTerm => "long_term",
            Self::Index => "index",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "episodic" => Some(Self::Episodic),
            "long_term" => Some(Self::LongTerm),
            "index" => Some(Self::Index),
            _ => None,
        }
    }
}

/// 记忆条目。对应 memories 表一行。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Memory {
    pub id: String,
    pub layer: String,
    pub content: String,
    pub importance_score: f64,
    pub decay_state: String,
    pub embedding_id: String,
    pub created_at: String,
}

/// 创建记忆请求。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateMemoryRequest {
    pub layer: MemoryLayer,
    pub content: String,
    /// 重要性初值（0~1），缺省 0.5
    #[serde(default = "default_importance")]
    pub importance_score: f64,
}

fn default_importance() -> f64 {
    0.5
}

/// 相似度检索结果。
#[derive(Debug, Clone, Serialize)]
pub struct SimilarMemory {
    pub memory: Memory,
    pub similarity: f64,
}

/// 决策账本条目。对应 decision_ledger 表一行。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionEntry {
    pub id: String,
    pub context: String,
    pub decision: String,
    pub rationale: String,
    pub outcome: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateDecisionRequest {
    pub context: String,
    pub decision: String,
    #[serde(default)]
    pub rationale: String,
    #[serde(default)]
    pub outcome: String,
}

/// 记忆引擎。持有数据库与 embedding 客户端引用。
pub struct MemoryEngine {
    db: Arc<Db>,
    embedder: Arc<EmbeddingClient>,
}

impl MemoryEngine {
    pub fn new(db: Arc<Db>, embedder: Arc<EmbeddingClient>) -> Self {
        Self { db, embedder }
    }

    /// 创建一条记忆。可选生成 embedding 并存向量表（content 非空时自动生成）。
    pub async fn create(&self, req: CreateMemoryRequest) -> Result<Memory> {
        let id = Uuid::new_v4().to_string();
        let embedding_id = Uuid::new_v4().to_string();
        let layer = req.layer.as_str();

        // 写 memories 表
        self.db.with_conn(|conn| {
            conn.execute(
                "INSERT INTO memories (id, layer, content, importance_score, decay_state, embedding_id)
                 VALUES (?, ?, ?, ?, 'active', ?)",
                params![id, layer, req.content, req.importance_score, embedding_id],
            )
        })?;

        // 异步生成 embedding 并存向量表（失败不阻断主流程，仅日志告警）
        let content_clone = req.content.clone();
        let embedder = self.embedder.clone();
        let db = self.db.clone();
        let eid = embedding_id.clone();
        let mid = id.clone();
        tokio::spawn(async move {
            match embedder.embed(&content_clone).await {
                Ok(vec) => {
                    let serialized = serde_json::to_string(&vec).unwrap_or_default();
                    if let Err(e) = db.with_conn(|conn| {
                        conn.execute(
                            "INSERT INTO memory_vectors (id, memory_id, vector) VALUES (?, ?, ?)",
                            params![eid, mid, serialized],
                        )
                    }) {
                        tracing::warn!("写入向量失败: {}", e);
                    }
                }
                Err(e) => {
                    tracing::warn!("生成 embedding 失败（记忆已落库，向量缺失）: {}", e);
                }
            }
        });

        // 读取返回
        self.get(&id)?.ok_or_else(|| anyhow::anyhow!("记忆刚写入却读不到: {}", id))
    }

    /// 按 id 查询记忆。
    pub fn get(&self, id: &str) -> Result<Option<Memory>> {
        Ok(self.db.with_conn(|conn| {
            let mut stmt = conn.prepare(
                "SELECT id, layer, content, importance_score, decay_state, embedding_id, created_at
                 FROM memories WHERE id = ?",
            )?;
            let mut rows = stmt.query(params![id])?;
            rows.next()?.map(row_to_memory).transpose()
        })?)
    }

    /// 按层级列出记忆，按 importance_score 降序。limit<=0 表示不限制。
    pub fn list_by_layer(&self, layer: MemoryLayer, limit: i64) -> Result<Vec<Memory>> {
        let sql = if limit > 0 {
            "SELECT id, layer, content, importance_score, decay_state, embedding_id, created_at
             FROM memories WHERE layer = ? ORDER BY importance_score DESC LIMIT ?"
        } else {
            "SELECT id, layer, content, importance_score, decay_state, embedding_id, created_at
             FROM memories WHERE layer = ? ORDER BY importance_score DESC"
        };
        self.db.with_conn(|conn| {
            let mut stmt = conn.prepare(sql)?;
            let rows: Result<Vec<Memory>, rusqlite::Error> = if limit > 0 {
                stmt.query_map(params![layer.as_str(), limit], |row| row_to_memory(row))?
                    .collect()
            } else {
                stmt.query_map(params![layer.as_str()], |row| row_to_memory(row))?
                    .collect()
            };
            Ok(rows?)
        })
    }

    /// 关键字检索（content LIKE）。返回匹配的记忆。
    pub fn search_by_keyword(&self, keyword: &str, limit: i64) -> Result<Vec<Memory>> {
        let pat = format!("%{}%", keyword);
        self.db.with_conn(|conn| {
            let mut stmt = conn.prepare(
                "SELECT id, layer, content, importance_score, decay_state, embedding_id, created_at
                 FROM memories WHERE content LIKE ? ORDER BY importance_score DESC LIMIT ?",
            )?;
            let rows: Result<Vec<Memory>, rusqlite::Error> = stmt
                .query_map(params![pat, limit], |row| row_to_memory(row))?
                .collect();
            Ok(rows?)
        })
    }

    /// 向量相似度检索（brute-force cosine）。
    ///
    /// 流程：对查询文本生成 embedding → 扫描 memory_vectors 全表 → 计算余弦相似度 → 取 top_k。
    /// 小规模记忆（<1万条）足够；后续可换 sqlite-vss 或外挂 Qdrant。
    pub async fn search_by_vector(&self, query: &str, top_k: usize) -> Result<Vec<SimilarMemory>> {
        let qvec = self.embedder.embed(query).await?;
        let candidates: Vec<(String, String, Vec<f32>)> = self.db.with_conn(|conn| {
            let mut stmt = conn.prepare("SELECT id, memory_id, vector FROM memory_vectors")?;
            let rows: Result<Vec<(String, String, Vec<f32>)>, rusqlite::Error> = stmt
                .query_map([], |row| {
                    let id: String = row.get(0)?;
                    let mid: String = row.get(1)?;
                    let v_json: String = row.get(2)?;
                    let v: Vec<f32> = serde_json::from_str(&v_json).unwrap_or_default();
                    Ok((id, mid, v))
                })?
                .collect();
            Ok(rows?)
        })?;

        let mut scored: Vec<SimilarMemory> = Vec::new();
        for (_vid, mid, v) in candidates {
            let sim = cosine_similarity(&qvec, &v) as f64;
            if let Ok(Some(m)) = self.get(&mid) {
                scored.push(SimilarMemory { memory: m, similarity: sim });
            }
        }
        scored.sort_by(|a, b| b.similarity.partial_cmp(&a.similarity).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(top_k);
        Ok(scored)
    }

    /// 升级记忆到 long_term 层，并刷新 importance_score 与 decay_state。
    /// 用于 dreaming Deep Sleep 阶段。
    pub fn promote_to_long_term(&self, id: &str, new_score: f64) -> Result<()> {
        self.db.with_conn(|conn| {
            conn.execute(
                "UPDATE memories SET layer='long_term', importance_score=?, decay_state='promoted'
                 WHERE id=?",
                params![new_score, id],
            )
        })?;
        Ok(())
    }

    /// 标记记忆为衰减（不删除，仅更新 decay_state）。
    pub fn mark_decaying(&self, id: &str) -> Result<()> {
        self.db.with_conn(|conn| {
            conn.execute(
                "UPDATE memories SET decay_state='decaying' WHERE id=?",
                params![id],
            )
        })?;
        Ok(())
    }

    /// 删除记忆（含其向量）。
    pub fn delete(&self, id: &str) -> Result<()> {
        self.db.with_conn(|conn| {
            conn.execute("DELETE FROM memory_vectors WHERE memory_id=?", params![id])?;
            conn.execute("DELETE FROM memories WHERE id=?", params![id])?;
            Ok(())
        })
    }

    // --- Decision Ledger ---

    /// 记录一条决策到账本。
    pub fn add_decision(&self, req: CreateDecisionRequest) -> Result<DecisionEntry> {
        let id = Uuid::new_v4().to_string();
        self.db.with_conn(|conn| {
            conn.execute(
                "INSERT INTO decision_ledger (id, context, decision, rationale, outcome)
                 VALUES (?, ?, ?, ?, ?)",
                params![id, req.context, req.decision, req.rationale, req.outcome],
            )
        })?;
        self.get_decision(&id)?.ok_or_else(|| anyhow::anyhow!("决策刚写入却读不到"))
    }

    /// 按 id 查询决策。
    pub fn get_decision(&self, id: &str) -> Result<Option<DecisionEntry>> {
        Ok(self.db.with_conn(|conn| {
            let mut stmt = conn.prepare(
                "SELECT id, context, decision, rationale, outcome, created_at
                 FROM decision_ledger WHERE id = ?",
            )?;
            let mut rows = stmt.query(params![id])?;
            rows.next()?.map(row_to_decision).transpose()
        })?)
    }

    /// 列出最近的决策，按 created_at 降序。limit<=0 表示不限制。
    pub fn list_decisions(&self, limit: i64) -> Result<Vec<DecisionEntry>> {
        let sql = if limit > 0 {
            "SELECT id, context, decision, rationale, outcome, created_at
             FROM decision_ledger ORDER BY rowid DESC LIMIT ?"
        } else {
            "SELECT id, context, decision, rationale, outcome, created_at
             FROM decision_ledger ORDER BY rowid DESC"
        };
        self.db.with_conn(|conn| {
            let mut stmt = conn.prepare(sql)?;
            let rows: Result<Vec<DecisionEntry>, rusqlite::Error> = if limit > 0 {
                stmt.query_map(params![limit], |row| row_to_decision(row))?.collect()
            } else {
                stmt.query_map([], |row| row_to_decision(row))?.collect()
            };
            Ok(rows?)
        })
    }
}

// --- 行映射辅助函数 ---

fn row_to_memory(row: &rusqlite::Row) -> rusqlite::Result<Memory> {
    Ok(Memory {
        id: row.get(0)?,
        layer: row.get(1)?,
        content: row.get(2)?,
        importance_score: row.get(3)?,
        decay_state: row.get(4)?,
        embedding_id: row.get(5)?,
        created_at: row.get(6)?,
    })
}

fn row_to_decision(row: &rusqlite::Row) -> rusqlite::Result<DecisionEntry> {
    Ok(DecisionEntry {
        id: row.get(0)?,
        context: row.get(1)?,
        decision: row.get(2)?,
        rationale: row.get(3)?,
        outcome: row.get(4)?,
        created_at: row.get(5)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use crate::db::Db;

    fn test_db() -> Db {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let db = Db::open(tmp.path().to_str().unwrap()).unwrap();
        // 建 memories 与 decision_ledger 表（模拟 Go 后端已建）
        db.with_conn(|conn| {
            conn.execute_batch(
                "CREATE TABLE memories (
                    id TEXT PRIMARY KEY, layer TEXT NOT NULL, content TEXT NOT NULL,
                    importance_score REAL DEFAULT 0, decay_state TEXT DEFAULT 'active',
                    embedding_id TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE decision_ledger (
                    id TEXT PRIMARY KEY, context TEXT, decision TEXT NOT NULL,
                    rationale TEXT, outcome TEXT, created_at TEXT DEFAULT (datetime('now'))
                );",
            )
            .unwrap();
        });
        db.ensure_dream_diary_table().unwrap();
        db
    }

    fn test_embedder() -> Arc<EmbeddingClient> {
        let cfg = Config {
            core_host: "127.0.0.1".into(),
            core_port: 0,
            db_path: ":memory:".into(),
            embedding_provider: "ollama".into(),
            embedding_model: "test".into(),
            embedding_api_base: "http://127.0.0.1:1".into(), // 不可达，测试会失败但不阻断主流程
            embedding_api_key: "".into(),
            embedding_timeout_secs: 1,
            recency_half_life_days: 7.0,
            max_age_days: 30,
        };
        Arc::new(EmbeddingClient::new(&cfg))
    }

    #[tokio::test]
    async fn test_create_and_get_memory() {
        let db = Arc::new(test_db());
        let eng = MemoryEngine::new(db, test_embedder());
        let m = eng
            .create(CreateMemoryRequest {
                layer: MemoryLayer::Episodic,
                content: "用户问了一个分布式系统问题".into(),
                importance_score: 0.8,
            })
            .await
            .unwrap();
        assert_eq!(m.layer, "episodic");
        assert_eq!(m.decay_state, "active");
        assert!((m.importance_score - 0.8).abs() < 1e-9);

        let got = eng.get(&m.id).unwrap().unwrap();
        assert_eq!(got.content, "用户问了一个分布式系统问题");
    }

    #[tokio::test]
    async fn test_list_by_layer() {
        let db = Arc::new(test_db());
        let eng = MemoryEngine::new(db, test_embedder());
        for i in 0..3 {
            eng.create(CreateMemoryRequest {
                layer: MemoryLayer::Episodic,
                content: format!("记忆 {}", i),
                importance_score: 0.1 * (i as f64),
            })
            .await
            .unwrap();
        }
        let list = eng.list_by_layer(MemoryLayer::Episodic, 0).unwrap();
        assert_eq!(list.len(), 3);
        // 按 importance_score DESC，最高分在前
        assert!((list[0].importance_score - 0.2).abs() < 1e-9);
    }

    #[tokio::test]
    async fn test_search_by_keyword() {
        let db = Arc::new(test_db());
        let eng = MemoryEngine::new(db, test_embedder());
        eng.create(CreateMemoryRequest {
            layer: MemoryLayer::Episodic,
            content: "MapReduce 论文精读".into(),
            importance_score: 0.5,
        })
        .await
        .unwrap();
        eng.create(CreateMemoryRequest {
            layer: MemoryLayer::Episodic,
            content: "GFS 论文笔记".into(),
            importance_score: 0.7,
        })
        .await
        .unwrap();

        let hits = eng.search_by_keyword("论文", 10).unwrap();
        assert_eq!(hits.len(), 2);
        // 按 importance DESC，GFS 在前
        assert!(hits[0].content.contains("GFS"));
    }

    #[tokio::test]
    async fn test_promote_and_decay() {
        let db = Arc::new(test_db());
        let eng = MemoryEngine::new(db, test_embedder());
        let m = eng
            .create(CreateMemoryRequest {
                layer: MemoryLayer::Episodic,
                content: "候选真理".into(),
                importance_score: 0.5,
            })
            .await
            .unwrap();
        eng.promote_to_long_term(&m.id, 0.95).unwrap();
        let got = eng.get(&m.id).unwrap().unwrap();
        assert_eq!(got.layer, "long_term");
        assert_eq!(got.decay_state, "promoted");
        assert!((got.importance_score - 0.95).abs() < 1e-9);

        eng.mark_decaying(&m.id).unwrap();
        let got2 = eng.get(&m.id).unwrap().unwrap();
        assert_eq!(got2.decay_state, "decaying");
    }

    #[tokio::test]
    async fn test_decision_ledger_crud() {
        let db = Arc::new(test_db());
        let eng = MemoryEngine::new(db, test_embedder());
        let d = eng
            .add_decision(CreateDecisionRequest {
                context: "选型讨论".into(),
                decision: "用 SQLite 而非 Postgres".into(),
                rationale: "单机零运维".into(),
                outcome: "简化部署".into(),
            })
            .unwrap();
        assert_eq!(d.decision, "用 SQLite 而非 Postgres");

        let list = eng.list_decisions(0).unwrap();
        assert_eq!(list.len(), 1);
    }

    #[tokio::test]
    async fn test_delete_memory_cascades_vector() {
        let db = Arc::new(test_db());
        let eng = MemoryEngine::new(db.clone(), test_embedder());
        let m = eng
            .create(CreateMemoryRequest {
                layer: MemoryLayer::Episodic,
                content: "待删除".into(),
                importance_score: 0.5,
            })
            .await
            .unwrap();
        // 手动塞一条向量（避免依赖真实 embedding）
        db.with_conn(|conn| {
            conn.execute(
                "INSERT INTO memory_vectors (id, memory_id, vector) VALUES (?, ?, ?)",
                params![m.embedding_id, m.id, "[0.1, 0.2]"],
            )
            .unwrap();
        });
        let cnt: i64 = db
            .with_conn(|conn| {
                conn.query_row("SELECT COUNT(*) FROM memory_vectors WHERE memory_id=?", params![m.id], |r| r.get(0))
            })
            .unwrap();
        assert_eq!(cnt, 1);

        eng.delete(&m.id).unwrap();
        let got = eng.get(&m.id).unwrap();
        assert!(got.is_none());
        let cnt2: i64 = db
            .with_conn(|conn| {
                conn.query_row("SELECT COUNT(*) FROM memory_vectors WHERE memory_id=?", params![m.id], |r| r.get(0))
            })
            .unwrap();
        assert_eq!(cnt2, 0);
    }
}
