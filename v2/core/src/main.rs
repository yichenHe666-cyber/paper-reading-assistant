//! 核动力科研牛马 v2 — Rust core 二进制入口。
//!
//! 启动流程：
//!   1. 从环境变量加载 Config（数据库路径、HTTP 端口、embedding provider）；
//!   2. 打开 SQLite（与 Go 共用同一文件）并补建 dream_diary 表；
//!   3. 启动 axum HTTP 服务，监听 CORE_HOST:CORE_PORT（默认 127.0.0.1:8788）；
//!   4. Go 后端通过 http://127.0.0.1:8788/* 调用本服务。
//!
//! 与 Go 后端的部署关系：同机部署，二者共享 SQLite 文件，通过 localhost HTTP 通信。
//! 不暴露公网端口，避免外部直接访问 core。

use std::sync::Arc;

use nuclear_ox_core::{config::Config, db::Db, http::build_app};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // 初始化日志：默认 INFO，可通过 RUST_LOG 覆盖
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let cfg = Config::load()?;
    tracing::info!("=== 核动力科研牛马 v2 Rust core 启动 ===");
    tracing::info!("监听: http://{}:{}", cfg.core_host, cfg.core_port);
    tracing::info!("数据库: {}", cfg.db_path);
    tracing::info!(
        "Embedding: provider={} model={}",
        cfg.embedding_provider, cfg.embedding_model
    );

    // 打开数据库并补建 dream_diary 表
    let db = Arc::new(Db::open(&cfg.db_path)?);
    db.ensure_dream_diary_table()?;

    // 构造 axum app
    let app = build_app(db.clone(), Arc::new(cfg.clone()));
    let addr: std::net::SocketAddr = format!("{}:{}", cfg.core_host, cfg.core_port).parse()?;

    let listener = tokio::net::TcpListener::bind(addr).await?;
    tracing::info!("Rust core 已就绪，等待 Go 后端调用");
    axum::serve(listener, app).await?;
    Ok(())
}
