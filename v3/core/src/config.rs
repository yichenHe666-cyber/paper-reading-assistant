//! 配置加载（环境变量）。
//!
//! 与 Go 后端的配置分离：本服务只关心自身所需的子集（数据库路径、HTTP 端口、embedding）。
//! 数据库路径默认与 Go 后端一致（NRO_DATA_DIR 派生），便于共享同一 SQLite 文件。

use std::env;

use anyhow::{anyhow, Result};

/// Rust core 配置。所有字段从环境变量加载。
#[derive(Debug, Clone)]
pub struct Config {
    /// 监听地址，默认 127.0.0.1（仅本机，Go 后端调用）
    pub core_host: String,
    /// 监听端口，默认 8788
    pub core_port: u16,
    /// SQLite 数据库绝对路径（与 Go 共用）
    pub db_path: String,
    /// embedding provider：ollama | openai
    pub embedding_provider: String,
    /// embedding 模型名，如 nomic-embed-text / text-embedding-3-small
    pub embedding_model: String,
    /// embedding API 基址
    pub embedding_api_base: String,
    /// embedding API key（ollama 可空）
    pub embedding_api_key: String,
    /// 单次 embedding 请求超时（秒）
    pub embedding_timeout_secs: u64,
    /// 梦境整合：时效性半衰期（天），控制记忆衰减速度（spec §5.3）
    pub recency_half_life_days: f64,
    /// 梦境整合：超龄记忆不再 eligible 升级（天）
    pub max_age_days: u64,
}

impl Config {
    /// 从环境变量加载配置。失败时返回明确错误。
    pub fn load() -> Result<Self> {
        let data_dir = env::var("NRO_DATA_DIR").unwrap_or_else(|_| {
            // 默认与 Go 后端一致：可执行文件同级 data 目录
            let exe = env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("."));
            exe.parent()
                .unwrap_or(std::path::Path::new("."))
                .join("data")
                .to_string_lossy()
                .to_string()
        });
        let db_path = if std::path::Path::new(&data_dir).is_absolute() {
            std::path::Path::new(&data_dir).join("db").join("reading_assistant.db")
        } else {
            // 相对路径基于可执行文件解析（与 Go 后端一致，避免 cwd 漂移）
            let exe = env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("."));
            exe.parent()
                .unwrap_or(std::path::Path::new("."))
                .join(&data_dir)
                .join("db")
                .join("reading_assistant.db")
        };

        let cfg = Config {
            core_host: env::var("CORE_HOST").unwrap_or_else(|_| "127.0.0.1".into()),
            core_port: env::var("CORE_PORT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(8788),
            db_path: db_path.to_string_lossy().to_string(),
            embedding_provider: env::var("EMBEDDING_PROVIDER")
                .unwrap_or_else(|_| "ollama".into()),
            embedding_model: env::var("EMBEDDING_MODEL")
                .unwrap_or_else(|_| "nomic-embed-text".into()),
            embedding_api_base: env::var("EMBEDDING_API_BASE")
                .unwrap_or_else(|_| "http://localhost:11434".into()),
            embedding_api_key: env::var("EMBEDDING_API_KEY").unwrap_or_default(),
            embedding_timeout_secs: env::var("EMBEDDING_TIMEOUT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(30),
            recency_half_life_days: env::var("RECENCY_HALF_LIFE_DAYS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(7.0),
            max_age_days: env::var("MAX_AGE_DAYS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(30),
        };

        if !std::path::Path::new(&cfg.db_path).exists() {
            // 数据库不存在不立即 fail：可能 Go 后端尚未启动建表。
            // 但路径必须合法，否则后续 open 会失败。
            if let Some(parent) = std::path::Path::new(&cfg.db_path).parent() {
                std::fs::create_dir_all(parent).map_err(|e| anyhow!("创建数据库目录失败: {}", e))?;
            }
        }

        Ok(cfg)
    }
}
