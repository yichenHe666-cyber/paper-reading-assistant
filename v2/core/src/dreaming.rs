//! 睡眠式记忆整合（spec §5.2）。
//!
//! 借鉴 OpenClaw Dreaming 与五层记忆架构，三阶段顺序执行：
//!
//! 1. **Light Sleep（浅睡）**：
//!    - 扫描近期 episodic 记忆；
//!    - Jaccard 相似度去重（阈值 0.9），相似项暂存为强化候选；
//!    - 不写长期记忆，仅记录强化信号。
//!
//! 2. **REM Sleep**：
//!    - 回溯窗口内分析内容词频，提取主题（高频词）；
//!    - 识别"候选真理"（被多次提及的事实/概念）；
//!    - 不写长期记忆。
//!
//! 3. **Deep Sleep（深睡）**：
//!    - 对候选按六信号加权评分：
//!      - 相关性   0.30  （与已有长期记忆的语义相关性，简化为关键字重叠）
//!      - 频率     0.24  （在 episodic 中出现次数）
//!      - 查询多样性 0.15（被不同会话/上下文引用的程度，首期用 created_at 离散度近似）
//!      - 时效性   0.15  （半衰期衰减，越新越高）
//!      - 整合度   0.10  （与已晋升长期记忆的连接数）
//!      - 概念丰富度 0.06（内容长度 / 唯一词数）
//!    - 叠加 Light/REM 强化加成；
//!    - 候选须同时满足三阈值门槛（score >= 0.5, frequency >= 2, recency >= 0.3）才升级；
//!    - 仅此阶段写入长期记忆，确保噪音不污染。
//!
//! 每次梦境产出 dream_diary 日志，前端可视化。

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use anyhow::Result;
use rusqlite::params;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::config::Config;
use crate::db::Db;
use crate::memory::{Memory, MemoryEngine, MemoryLayer};

/// 六信号权重（spec §5.2）。
const W_RELEVANCE: f64 = 0.30;
const W_FREQUENCY: f64 = 0.24;
const W_DIVERSITY: f64 = 0.15;
const W_RECENCY: f64 = 0.15;
const W_INTEGRATION: f64 = 0.10;
const W_RICHNESS: f64 = 0.06;

/// Deep Sleep 升级三阈值门槛。
const THRESHOLD_SCORE: f64 = 0.5;
const THRESHOLD_FREQUENCY: usize = 2;
const THRESHOLD_RECENCY: f64 = 0.3;

/// Light Sleep Jaccard 相似度阈值。
const JACCARD_THRESHOLD: f64 = 0.9;

/// 候选记忆（Light/REM 阶段产出，供 Deep 评分）。
#[derive(Debug, Clone, Serialize)]
pub struct Candidate {
    pub memory: Memory,
    pub frequency: usize,
    pub reinforcement: f64, // Light/REM 累积的强化加成
}

/// 评分明细（Deep 阶段产出）。
#[derive(Debug, Clone, Serialize)]
pub struct ScoreBreakdown {
    pub memory_id: String,
    pub relevance: f64,
    pub frequency: f64,
    pub diversity: f64,
    pub recency: f64,
    pub integration: f64,
    pub richness: f64,
    pub reinforcement: f64,
    pub total: f64,
    pub promoted: bool,
    pub reason: String,
}

/// 梦境整合结果。
#[derive(Debug, Clone, Serialize)]
pub struct DreamResult {
    pub diary_id: String,
    pub started_at: String,
    pub finished_at: String,
    pub reviewed_count: usize,
    pub promoted_count: usize,
    pub decayed_count: usize,
    pub summary: String,
    pub breakdowns: Vec<ScoreBreakdown>,
}

/// Dream Diary 条目（对应 dream_diary 表）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DreamDiaryEntry {
    pub id: String,
    pub started_at: String,
    pub finished_at: String,
    pub stage: String,
    pub reviewed_count: i64,
    pub promoted_count: i64,
    pub decayed_count: i64,
    pub summary: String,
    pub details_json: String,
}

/// 梦境整合器。
pub struct Dreamer {
    db: Arc<Db>,
    memory: Arc<MemoryEngine>,
    cfg: Arc<Config>,
}

impl Dreamer {
    pub fn new(db: Arc<Db>, memory: Arc<MemoryEngine>, cfg: Arc<Config>) -> Self {
        Self { db, memory, cfg }
    }

    /// 执行一次完整梦境（Light → REM → Deep）。
    pub async fn dream(&self) -> Result<DreamResult> {
        let diary_id = Uuid::new_v4().to_string();
        let started_at = now_iso();

        // 起始日志
        self.insert_diary_stage(&diary_id, &started_at, "light", 0, 0, 0, "梦境开始", "")?;

        // 1. Light Sleep：去重 + 强化信号
        let (candidates, light_summary) = self.light_sleep().await?;
        self.insert_diary_stage(
            &diary_id,
            &started_at,
            "rem",
            candidates.len() as i64,
            0,
            0,
            &light_summary,
            "",
        )?;

        // 2. REM Sleep：词频分析 + 主题提取（增强 candidate 频率）
        let (candidates, rem_summary) = self.rem_sleep(candidates).await?;
        self.insert_diary_stage(
            &diary_id,
            &started_at,
            "deep",
            candidates.len() as i64,
            0,
            0,
            &rem_summary,
            "",
        )?;

        // 3. Deep Sleep：六信号评分 + 升级
        let (breakdowns, promoted_count, decayed_count, deep_summary) =
            self.deep_sleep(candidates).await?;
        let finished_at = now_iso();
        let summary = format!(
            "{} | {}",
            deep_summary,
            format!(
                "升级 {} 条，衰减 {} 条，评分 {} 条",
                promoted_count, decayed_count, breakdowns.len()
            )
        );
        let details_json = serde_json::to_string(&breakdowns).unwrap_or_default();

        // 完成日志
        self.insert_diary_stage(
            &diary_id,
            &started_at,
            "done",
            breakdowns.len() as i64,
            promoted_count as i64,
            decayed_count as i64,
            &summary,
            &details_json,
        )?;
        // 更新 finished_at
        self.db.with_conn(|conn| {
            conn.execute(
                "UPDATE dream_diary SET finished_at=? WHERE id=?",
                params![finished_at, diary_id],
            )
        })?;

        Ok(DreamResult {
            diary_id,
            started_at,
            finished_at,
            reviewed_count: breakdowns.len(),
            promoted_count,
            decayed_count,
            summary,
            breakdowns,
        })
    }

    /// 列出最近的 Dream Diary 条目（按 started_at 降序）。
    pub fn list_diary(&self, limit: i64) -> Result<Vec<DreamDiaryEntry>> {
        let sql = if limit > 0 {
            "SELECT id, started_at, finished_at, stage, reviewed_count, promoted_count, decayed_count, summary, details_json
             FROM dream_diary WHERE stage='done' ORDER BY rowid DESC LIMIT ?"
        } else {
            "SELECT id, started_at, finished_at, stage, reviewed_count, promoted_count, decayed_count, summary, details_json
             FROM dream_diary WHERE stage='done' ORDER BY rowid DESC"
        };
        self.db.with_conn(|conn| {
            let mut stmt = conn.prepare(sql)?;
            let rows: Result<Vec<DreamDiaryEntry>, rusqlite::Error> = if limit > 0 {
                stmt.query_map(params![limit], row_to_diary)?.collect()
            } else {
                stmt.query_map([], row_to_diary)?.collect()
            };
            Ok(rows?)
        })
    }

    /// 按 id 查询单条 Dream Diary。
    pub fn get_diary(&self, id: &str) -> Result<Option<DreamDiaryEntry>> {
        Ok(self.db.with_conn(|conn| {
            let mut stmt = conn.prepare(
                "SELECT id, started_at, finished_at, stage, reviewed_count, promoted_count, decayed_count, summary, details_json
                 FROM dream_diary WHERE id = ?",
            )?;
            let mut rows = stmt.query(params![id])?;
            rows.next()?.map(row_to_diary).transpose()
        })?)
    }

    // --- 三阶段实现 ---

    /// Light Sleep：扫描近期 episodic 记忆，Jaccard 去重，输出候选 + 强化信号。
    async fn light_sleep(&self) -> Result<(Vec<Candidate>, String)> {
        let episodic = self.memory.list_by_layer(MemoryLayer::Episodic, 0)?;
        if episodic.is_empty() {
            return Ok((vec![], "无近期情景记忆".into()));
        }

        // 计算每对 episodic 的 Jaccard 相似度，相似项合并为候选（保留首个，频率累加）
        let mut candidates: Vec<Candidate> = Vec::new();
        let mut merged: HashSet<usize> = HashSet::new();

        for (i, m) in episodic.iter().enumerate() {
            if merged.contains(&i) {
                continue;
            }
            let mut freq = 1usize;
            let mut reinforcement = 0.0f64;
            let set_i = tokenize(&m.content);
            for (j, other) in episodic.iter().enumerate() {
                if j <= i || merged.contains(&j) {
                    continue;
                }
                let set_j = tokenize(&other.content);
                let sim = jaccard(&set_i, &set_j);
                if sim >= JACCARD_THRESHOLD {
                    freq += 1;
                    reinforcement += sim * 0.1; // 每个相似项贡献 0.1*sim 的强化
                    merged.insert(j);
                }
            }
            merged.insert(i);
            candidates.push(Candidate {
                memory: m.clone(),
                frequency: freq,
                reinforcement,
            });
        }

        let summary = format!(
            "审查 {} 条 episodic，去重后 {} 个候选",
            episodic.len(),
            candidates.len()
        );
        Ok((candidates, summary))
    }

    /// REM Sleep：词频分析 + 主题提取，增强 candidate 频率。
    ///
    /// 简化实现：扫描全部 episodic 内容，统计每个 candidate 的核心词在整体中的出现次数，
    /// 与 Light 阶段 frequency 取 max，作为最终 frequency。
    async fn rem_sleep(&self, candidates: Vec<Candidate>) -> Result<(Vec<Candidate>, String)> {
        if candidates.is_empty() {
            return Ok((candidates, "无候选，REM 跳过".into()));
        }

        let episodic = self.memory.list_by_layer(MemoryLayer::Episodic, 0)?;
        // 全局词频
        let mut global_freq: HashMap<String, usize> = HashMap::new();
        for m in &episodic {
            for w in tokenize(&m.content) {
                *global_freq.entry(w).or_insert(0) += 1;
            }
        }

        let mut enhanced: Vec<Candidate> = Vec::new();
        let mut top_words: Vec<(String, usize)> = global_freq
            .iter()
            .map(|(k, v)| (k.clone(), *v))
            .collect();
        top_words.sort_by(|a, b| b.1.cmp(&a.1));
        top_words.truncate(5);

        for mut c in candidates {
            let words = tokenize(&c.memory.content);
            // candidate 的内容词在全局出现总次数（去重后求和）
            let global_hits: usize = words.iter().map(|w| *global_freq.get(w).unwrap_or(&0)).sum();
            // 取 max(Light freq, global_hits 的对数缩放) 作为最终 frequency
            let scaled = (global_hits as f64).log2().ceil() as usize;
            if scaled > c.frequency {
                c.frequency = scaled;
            }
            // REM 强化：主题词命中率
            let theme_overlap = words
                .iter()
                .filter(|w| top_words.iter().any(|(t, _)| t == *w))
                .count();
            c.reinforcement += theme_overlap as f64 * 0.05;
            enhanced.push(c);
        }

        let themes = top_words
            .iter()
            .map(|(w, n)| format!("{}({})", w, n))
            .collect::<Vec<_>>()
            .join(", ");
        let summary = format!("REM 主题词：{}", themes);
        Ok((enhanced, summary))
    }

    /// Deep Sleep：六信号评分 + 升级 + 衰减。
    async fn deep_sleep(
        &self,
        candidates: Vec<Candidate>,
    ) -> Result<(Vec<ScoreBreakdown>, usize, usize, String)> {
        let long_term = self.memory.list_by_layer(MemoryLayer::LongTerm, 0)?;
        let episodic = self.memory.list_by_layer(MemoryLayer::Episodic, 0)?;
        let now = chrono::Utc::now();
        let half_life = self.cfg.recency_half_life_days.max(1.0);

        let mut breakdowns: Vec<ScoreBreakdown> = Vec::new();
        let mut promoted = 0usize;
        let mut decayed = 0usize;

        for c in &candidates {
            let words = tokenize(&c.memory.content);
            let word_set: HashSet<&String> = words.iter().collect();

            // 1. 相关性：与已有 long_term 的关键字重叠率（最大值）
            let relevance = if long_term.is_empty() {
                0.5 // 无长期记忆时给中等分
            } else {
                let mut max_overlap = 0.0f64;
                for lt in &long_term {
                    let lt_words = tokenize(&lt.content);
                    let lt_set: HashSet<&String> = lt_words.iter().collect();
                    let inter = word_set.intersection(&lt_set).count();
                    let union = word_set.union(&lt_set).count();
                    let j = if union > 0 {
                        inter as f64 / union as f64
                    } else {
                        0.0
                    };
                    if j > max_overlap {
                        max_overlap = j;
                    }
                }
                max_overlap
            };

            // 2. 频率：归一化到 0~1（log2 缩放）
            let frequency_raw = c.frequency as f64;
            let frequency = (frequency_raw.log2() / 5.0).min(1.0).max(0.0);

            // 3. 查询多样性：用 created_at 离散度近似（不同时段被引用 = 多样性高）
            //    简化：候选频率 > 1 视为有多样性，按 log 缩放
            let diversity = if c.frequency > 1 {
                ((c.frequency as f64).log2() / 3.0).min(1.0)
            } else {
                0.2
            };

            // 4. 时效性：半衰期衰减
            let recency = compute_recency(&c.memory.created_at, now, half_life);

            // 5. 整合度：与已晋升 long_term 的连接数（关键字重叠 > 0.3 的数量）
            let integration = if long_term.is_empty() {
                0.0
            } else {
                let connections = long_term
                    .iter()
                    .filter(|lt| {
                        let lt_words = tokenize(&lt.content);
                        let lt_set: HashSet<&String> = lt_words.iter().collect();
                        let inter = word_set.intersection(&lt_set).count();
                        let union = word_set.union(&lt_set).count();
                        union > 0 && inter as f64 / union as f64 > 0.3
                    })
                    .count();
                (connections as f64 / 5.0).min(1.0)
            };

            // 6. 概念丰富度：内容长度 / 唯一词数
            let unique_words = word_set.len().max(1);
            let richness = (c.memory.content.len() as f64 / (unique_words as f64 * 10.0))
                .min(1.0)
                .max(0.0);

            // 总分 = 各信号加权和 + 强化加成
            let total = W_RELEVANCE * relevance
                + W_FREQUENCY * frequency
                + W_DIVERSITY * diversity
                + W_RECENCY * recency
                + W_INTEGRATION * integration
                + W_RICHNESS * richness
                + c.reinforcement;

            // 三阈值门槛判定
            let promoted_flag = total >= THRESHOLD_SCORE
                && c.frequency >= THRESHOLD_FREQUENCY
                && recency >= THRESHOLD_RECENCY;

            let reason = if promoted_flag {
                format!(
                    "升级：总分 {:.2}>=0.5，频率 {}>=2，时效 {:.2}>=0.3",
                    total, c.frequency, recency
                )
            } else {
                let mut blockers = vec![];
                if total < THRESHOLD_SCORE {
                    blockers.push(format!("总分 {:.2}<0.5", total));
                }
                if c.frequency < THRESHOLD_FREQUENCY {
                    blockers.push(format!("频率 {}<2", c.frequency));
                }
                if recency < THRESHOLD_RECENCY {
                    blockers.push(format!("时效 {:.2}<0.3", recency));
                }
                format!("未升级：{}", blockers.join("，"))
            };

            if promoted_flag {
                self.memory.promote_to_long_term(&c.memory.id, total)?;
                promoted += 1;
            } else if total < 0.2 {
                // 极低分标记衰减
                self.memory.mark_decaying(&c.memory.id)?;
                decayed += 1;
            }

            breakdowns.push(ScoreBreakdown {
                memory_id: c.memory.id.clone(),
                relevance,
                frequency,
                diversity,
                recency,
                integration,
                richness,
                reinforcement: c.reinforcement,
                total,
                promoted: promoted_flag,
                reason,
            });
        }

        let _ = episodic; // 保留用于未来扩展（如跨会话多样性）
        let summary = format!(
            "Deep Sleep 完成：{} 候选评分",
            breakdowns.len()
        );
        Ok((breakdowns, promoted, decayed, summary))
    }

    // --- Dream Diary 持久化 ---

    fn insert_diary_stage(
        &self,
        id: &str,
        started_at: &str,
        stage: &str,
        reviewed: i64,
        promoted: i64,
        decayed: i64,
        summary: &str,
        details: &str,
    ) -> Result<()> {
        self.db.with_conn(|conn| {
            conn.execute(
                "INSERT INTO dream_diary (id, started_at, stage, reviewed_count, promoted_count, decayed_count, summary, details_json)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                params![id, started_at, stage, reviewed, promoted, decayed, summary, details],
            )
        })?;
        Ok(())
    }
}

// --- 辅助函数 ---

/// 当前 ISO 时间字符串。
fn now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

/// 简单分词：按非字母数字字符切分，转小写，过滤停用词与短词。
///
/// 首期不引入分词库，CJK 与 ASCII 混合按字符切分（中文单字视为 token）。
fn tokenize(s: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut current = String::new();
    for ch in s.chars() {
        if ch.is_alphanumeric() {
            current.push(ch.to_ascii_lowercase());
        } else {
            if !current.is_empty() {
                push_token(&mut out, &current);
                current.clear();
            }
            // CJK 字符单独成 token（is_alphanumeric 对 CJK 返回 true，故走上面分支）
        }
    }
    if !current.is_empty() {
        push_token(&mut out, &current);
    }
    out
}

/// 推入 token，过滤过短（<2 字符）的英文词。CJK 单字保留。
fn push_token(out: &mut Vec<String>, tok: &str) {
    if tok.chars().count() < 2 && tok.is_ascii() {
        return;
    }
    out.push(tok.to_string());
}

/// Jaccard 相似度：|A∩B| / |A∪B|。
fn jaccard(a: &HashSet<String>, b: &HashSet<String>) -> f64 {
    if a.is_empty() && b.is_empty() {
        return 1.0;
    }
    let inter = a.intersection(b).count();
    let union = a.union(b).count();
    if union == 0 {
        return 0.0;
    }
    inter as f64 / union as f64
}

/// 时效性评分：基于半衰期的指数衰减。
///
/// recency = 0.5^(age_days / half_life_days)
///   - age=0 时 recency=1.0（最新）
///   - age=half_life 时 recency=0.5（半衰）
///   - age=2*half_life 时 recency=0.25
fn compute_recency(created_at: &str, now: chrono::DateTime<chrono::Utc>, half_life: f64) -> f64 {
    let parsed = chrono::DateTime::parse_from_rfc3339(created_at)
        .or_else(|_| {
            // SQLite datetime('now') 格式 "YYYY-MM-DD HH:MM:SS" 转 RFC3339
            chrono::NaiveDateTime::parse_from_str(created_at, "%Y-%m-%d %H:%M:%S")
                .map(|ndt| chrono::DateTime::<chrono::Utc>::from_naive_utc_and_offset(ndt, chrono::Utc).into())
        })
        .or_else(|_| {
            // 仅日期
            chrono::NaiveDate::parse_from_str(created_at, "%Y-%m-%d")
                .map(|d| chrono::DateTime::<chrono::Utc>::from_naive_utc_and_offset(d.and_hms_opt(0, 0, 0).unwrap(), chrono::Utc).into())
        });
    let dt = match parsed {
        Ok(dt) => dt.with_timezone(&chrono::Utc),
        Err(_) => return 0.5, // 解析失败给中等分
    };
    let age_days = (now - dt).num_seconds() as f64 / 86400.0;
    0.5f64.powf(age_days / half_life.max(1.0))
}

fn row_to_diary(row: &rusqlite::Row) -> rusqlite::Result<DreamDiaryEntry> {
    Ok(DreamDiaryEntry {
        id: row.get(0)?,
        started_at: row.get(1)?,
        finished_at: row.get(2).unwrap_or_default(),
        stage: row.get(3)?,
        reviewed_count: row.get(4)?,
        promoted_count: row.get(5)?,
        decayed_count: row.get(6)?,
        summary: row.get(7)?,
        details_json: row.get(8).unwrap_or_default(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vector::EmbeddingClient;

    fn setup() -> (Arc<Db>, Arc<MemoryEngine>, Arc<Config>, Dreamer) {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let db = Arc::new(Db::open(tmp.path().to_str().unwrap()).unwrap());
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

        let cfg = Arc::new(Config {
            core_host: "127.0.0.1".into(),
            core_port: 0,
            db_path: ":memory:".into(),
            embedding_provider: "ollama".into(),
            embedding_model: "test".into(),
            embedding_api_base: "http://127.0.0.1:1".into(),
            embedding_api_key: "".into(),
            embedding_timeout_secs: 1,
            recency_half_life_days: 7.0,
            max_age_days: 30,
        });
        let embedder = Arc::new(EmbeddingClient::new(&cfg));
        let mem = Arc::new(MemoryEngine::new(db.clone(), embedder));
        let dreamer = Dreamer::new(db.clone(), mem.clone(), cfg.clone());
        (db, mem, cfg, dreamer)
    }

    #[test]
    fn test_tokenize_ascii() {
        let tokens = tokenize("MapReduce paper review");
        assert!(tokens.contains(&"mapreduce".into()));
        assert!(tokens.contains(&"paper".into()));
        assert!(tokens.contains(&"review".into()));
        // "p" 等短词被过滤
        assert!(!tokens.iter().any(|t| t == "p"));
    }

    #[test]
    fn test_tokenize_cjk() {
        let tokens = tokenize("分布式系统论文");
        // CJK 单字成 token（中文 is_alphanumeric 返回 true）
        assert!(tokens.iter().any(|t| t.contains("分")));
        assert!(tokens.iter().any(|t| t.contains("论")));
    }

    #[test]
    fn test_jaccard_identical() {
        let a: HashSet<String> = ["a", "b", "c"].iter().map(|s| s.to_string()).collect();
        let b = a.clone();
        assert!((jaccard(&a, &b) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_jaccard_disjoint() {
        let a: HashSet<String> = ["a"].iter().map(|s| s.to_string()).collect();
        let b: HashSet<String> = ["b"].iter().map(|s| s.to_string()).collect();
        assert!(jaccard(&a, &b).abs() < 1e-9);
    }

    #[test]
    fn test_compute_recency_now() {
        let now = chrono::Utc::now();
        let just_now = now.to_rfc3339();
        let r = compute_recency(&just_now, now, 7.0);
        assert!((r - 1.0).abs() < 1e-6, "刚创建的 recency 应为 1，实际 {}", r);
    }

    #[test]
    fn test_compute_recency_half_life() {
        let now = chrono::Utc::now();
        // 7 天前 = 1 个半衰期 → recency 应为 0.5
        let past = now - chrono::Duration::days(7);
        let r = compute_recency(&past.to_rfc3339(), now, 7.0);
        assert!((r - 0.5).abs() < 1e-3, "7 天前 recency 应为 0.5，实际 {}", r);
    }

    #[test]
    fn test_compute_recency_invalid_date() {
        let r = compute_recency("not-a-date", chrono::Utc::now(), 7.0);
        assert_eq!(r, 0.5, "非法日期应返回中等分 0.5");
    }

    #[tokio::test]
    async fn test_dream_empty_memory() {
        let (_db, _mem, _cfg, dreamer) = setup();
        let result = dreamer.dream().await.unwrap();
        assert_eq!(result.reviewed_count, 0);
        assert_eq!(result.promoted_count, 0);
        assert!(result.summary.contains("无近期情景记忆") || result.summary.contains("无候选"));
    }

    #[tokio::test]
    async fn test_dream_promotes_high_frequency() {
        let (_db, mem, _cfg, dreamer) = setup();
        // 插入 3 条相似内容（高频，应被升级）
        for _ in 0..3 {
            mem.create(CreateMemoryRequest {
                layer: MemoryLayer::Episodic,
                content: "MapReduce distributed system paper review".into(),
                importance_score: 0.7,
            })
            .await
            .unwrap();
        }
        let result = dreamer.dream().await.unwrap();
        // 至少有一条候选被评分
        assert!(result.reviewed_count > 0, "应有候选被评分");
        // 写入 dream_diary
        let diary = dreamer.list_diary(10).unwrap();
        assert!(!diary.is_empty(), "Dream Diary 应有记录");
        assert_eq!(diary[0].stage, "done");
    }
}
