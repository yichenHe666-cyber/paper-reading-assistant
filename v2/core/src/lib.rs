//! 核动力科研牛马 v2 — Rust core。
//!
//! 本 crate 是高性能核心服务，独立进程运行，通过 HTTP（axum）供 Go 后端调用。
//! 职责（spec §5）：
//!   - vector/   : 向量化（Ollama / OpenAI embedding 适配）
//!   - memory/   : 记忆引擎（五层存储 CRUD + 检索）
//!   - dreaming/ : 睡眠式记忆整合（Light → REM → Deep 三阶段，六信号评分）
//!   - http/     : axum HTTP 接口
//!
//! 与 Go 后端共用同一 SQLite 文件：Go 负责建 memories/decision_ledger 等表，
//! Rust 启动时补建 dream_diary 表，并对 memories 表做读写。
//! 共享数据库用 WAL 模式（Go 侧已启用），单写多读并发安全。

pub mod vector;
pub mod memory;
pub mod dreaming;
pub mod http;
pub mod db;
pub mod config;

pub use config::Config;
