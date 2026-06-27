//! axum HTTP 路由（spec §7.2 记忆相关 API）。
//!
//! 暴露端点供 Go 后端调用（localhost 内网，不暴露公网）：
//!   GET    /health                健康检查
//!   POST   /memory                创建记忆（自动异步生成 embedding）
//!   GET    /memory/:id            查询记忆
//!   DELETE /memory/:id            删除记忆（含向量级联）
//!   GET    /memory/search         关键字检索（?keyword=&limit=）
//!   POST   /memory/search-vector  向量相似度检索（body: {query, top_k}）
//!   POST   /dream                 触发梦境（Light → REM → Deep）
//!   GET    /dream-diary           列出 Dream Diary（?limit=）
//!   GET    /dream-diary/:id       查询单条 Dream Diary
//!   POST   /decision              记录决策到账本
//!   GET    /decisions             列出决策（?limit=）
//!
//! 错误响应统一 JSON：`{"error": "<message>"}`，状态码 500 表示内部错误，404 表示未找到。
//! 成功响应体即领域对象（Memory / DreamResult / DreamDiaryEntry / DecisionEntry 等），
//! 或列表包装 `{"items": [...]}`，与 Go 侧 client 的反序列化对齐。

use std::sync::Arc;

use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Json, Response};
use axum::routing::{get, post};
use axum::Router;
use serde::Deserialize;
use serde_json::json;

use crate::config::Config;
use crate::db::Db;
use crate::dreaming::Dreamer;
use crate::memory::{CreateDecisionRequest, CreateMemoryRequest, MemoryEngine};
use crate::vector::EmbeddingClient;

/// 应用共享状态。所有 handler 通过 State<AppState> 访问。
///
/// Clone 廉价：内部全是 Arc。
#[derive(Clone)]
pub struct AppState {
    pub memory: Arc<MemoryEngine>,
    pub dreamer: Arc<Dreamer>,
}

/// 构建 axum Router。由 main 调用。
///
/// 内部组装 EmbeddingClient → MemoryEngine → Dreamer 三层依赖，
/// 通过 with_state 注入 AppState。
pub fn build_app(db: Arc<Db>, cfg: Arc<Config>) -> Router {
    let embedder = Arc::new(EmbeddingClient::new(&cfg));
    let memory = Arc::new(MemoryEngine::new(db.clone(), embedder));
    let dreamer = Arc::new(Dreamer::new(db, memory.clone(), cfg));
    let state = AppState { memory, dreamer };

    Router::new()
        .route("/health", get(health))
        // 记忆 CRUD
        .route("/memory", post(create_memory))
        .route("/memory/:id", get(get_memory).delete(delete_memory))
        .route("/memory/search", get(search_memory))
        .route("/memory/search-vector", post(search_vector))
        // 梦境整合
        .route("/dream", post(trigger_dream))
        .route("/dream-diary", get(list_dream_diary))
        .route("/dream-diary/:id", get(get_dream_diary))
        // 决策账本
        .route("/decision", post(add_decision))
        .route("/decisions", get(list_decisions))
        .with_state(state)
}

// --- 健康检查 ---

async fn health() -> Json<serde_json::Value> {
    Json(json!({
        "status": "ok",
        "service": "nuclear-ox-core",
    }))
}

// --- 记忆 ---

async fn create_memory(State(st): State<AppState>, Json(req): Json<CreateMemoryRequest>) -> Response {
    match st.memory.create(req).await {
        Ok(m) => (StatusCode::CREATED, Json(m)).into_response(),
        Err(e) => internal_error(e.to_string()),
    }
}

async fn get_memory(State(st): State<AppState>, Path(id): Path<String>) -> Response {
    match st.memory.get(&id) {
        Ok(Some(m)) => Json(m).into_response(),
        Ok(None) => not_found("记忆不存在"),
        Err(e) => internal_error(e.to_string()),
    }
}

async fn delete_memory(State(st): State<AppState>, Path(id): Path<String>) -> Response {
    match st.memory.delete(&id) {
        Ok(_) => (StatusCode::NO_CONTENT, Json(json!({"ok": true}))).into_response(),
        Err(e) => internal_error(e.to_string()),
    }
}

/// 关键字检索 query 参数。
#[derive(Deserialize)]
struct SearchQuery {
    keyword: String,
    #[serde(default = "default_limit")]
    limit: i64,
}

async fn search_memory(State(st): State<AppState>, Query(q): Query<SearchQuery>) -> Response {
    match st.memory.search_by_keyword(&q.keyword, q.limit) {
        Ok(list) => Json(json!({"items": list})).into_response(),
        Err(e) => internal_error(e.to_string()),
    }
}

/// 向量检索请求体。
#[derive(Deserialize)]
struct SearchVectorRequest {
    query: String,
    #[serde(default = "default_top_k")]
    top_k: usize,
}

async fn search_vector(
    State(st): State<AppState>,
    Json(req): Json<SearchVectorRequest>,
) -> Response {
    match st.memory.search_by_vector(&req.query, req.top_k).await {
        Ok(list) => Json(json!({"items": list})).into_response(),
        Err(e) => internal_error(e.to_string()),
    }
}

// --- 梦境 ---

async fn trigger_dream(State(st): State<AppState>) -> Response {
    match st.dreamer.dream().await {
        Ok(r) => Json(r).into_response(),
        Err(e) => internal_error(e.to_string()),
    }
}

/// 列表 query 参数（dream-diary / decisions 共用）。
#[derive(Deserialize)]
struct ListQuery {
    #[serde(default = "default_limit")]
    limit: i64,
}

async fn list_dream_diary(State(st): State<AppState>, Query(q): Query<ListQuery>) -> Response {
    match st.dreamer.list_diary(q.limit) {
        Ok(list) => Json(json!({"items": list})).into_response(),
        Err(e) => internal_error(e.to_string()),
    }
}

async fn get_dream_diary(State(st): State<AppState>, Path(id): Path<String>) -> Response {
    match st.dreamer.get_diary(&id) {
        Ok(Some(d)) => Json(d).into_response(),
        Ok(None) => not_found("Dream Diary 条目不存在"),
        Err(e) => internal_error(e.to_string()),
    }
}

// --- 决策账本 ---

async fn add_decision(
    State(st): State<AppState>,
    Json(req): Json<CreateDecisionRequest>,
) -> Response {
    match st.memory.add_decision(req) {
        Ok(d) => (StatusCode::CREATED, Json(d)).into_response(),
        Err(e) => internal_error(e.to_string()),
    }
}

async fn list_decisions(State(st): State<AppState>, Query(q): Query<ListQuery>) -> Response {
    match st.memory.list_decisions(q.limit) {
        Ok(list) => Json(json!({"items": list})).into_response(),
        Err(e) => internal_error(e.to_string()),
    }
}

// --- 错误响应辅助 ---

fn internal_error(msg: String) -> Response {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"error": msg})),
    )
        .into_response()
}

fn not_found(msg: &str) -> Response {
    (StatusCode::NOT_FOUND, Json(json!({"error": msg}))).into_response()
}

fn default_limit() -> i64 {
    20
}

fn default_top_k() -> usize {
    5
}
