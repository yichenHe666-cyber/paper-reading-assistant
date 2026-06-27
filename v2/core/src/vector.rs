//! 向量化适配层（spec §5）。
//!
//! 支持 Ollama 与 OpenAI 兼容的 embedding API：
//!   - Ollama：POST {base}/api/embeddings，body {model, prompt}，返回 {embedding: [f32]}；
//!   - OpenAI 兼容：POST {base}/embeddings，body {model, input}，返回 {data: [{embedding}]}。
//!
//! 设计要点：
//!   - 首期不引入专门向量库（Qdrant/Milvus），向量与记忆元数据同存 SQLite（embedding_id 关联）；
//!   - 相似度检索用余弦相似度，在 memory 模块内做 brute-force（小规模足够）；
//!   - provider 自动按 EMBEDDING_PROVIDER 切换，调用方无感。

use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};

use crate::config::Config;

/// Embedding 客户端。线程安全（reqwest::Client 内部可克隆共享）。
#[derive(Debug, Clone)]
pub struct EmbeddingClient {
    provider: String,
    model: String,
    api_base: String,
    api_key: String,
    http: reqwest::Client,
}

/// Ollama embedding 响应体。
#[derive(Debug, Deserialize)]
struct OllamaEmbeddingResponse {
    embedding: Vec<f32>,
}

/// OpenAI 兼容 embedding 响应体。
#[derive(Debug, Deserialize)]
struct OpenAIEmbeddingResponse {
    data: Vec<OpenAIEmbeddingData>,
}

#[derive(Debug, Deserialize)]
struct OpenAIEmbeddingData {
    embedding: Vec<f32>,
}

/// embedding 请求体（OpenAI 风格，Ollama 也接受 model+prompt 字段名差异在 client 内适配）。
#[derive(Debug, Serialize)]
struct OllamaRequest<'a> {
    model: &'a str,
    prompt: &'a str,
}

#[derive(Debug, Serialize)]
struct OpenAIRequest<'a> {
    model: &'a str,
    input: &'a str,
}

impl EmbeddingClient {
    /// 从 Config 构造客户端。
    pub fn new(cfg: &Config) -> Self {
        let http = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(cfg.embedding_timeout_secs))
            .build()
            .expect("构建 reqwest client 失败");
        Self {
            provider: cfg.embedding_provider.clone(),
            model: cfg.embedding_model.clone(),
            api_base: cfg.embedding_api_base.clone(),
            api_key: cfg.embedding_api_key.clone(),
            http,
        }
    }

    /// 对文本生成 embedding 向量。
    pub async fn embed(&self, text: &str) -> Result<Vec<f32>> {
        let prov = self.provider.to_lowercase();
        match prov.as_str() {
            "ollama" => self.embed_ollama(text).await,
            "openai" | "openai-compat" => self.embed_openai(text).await,
            _ => {
                // 未知 provider：尝试 OpenAI 兼容（最通用）
                self.embed_openai(text).await
            }
        }
    }

    async fn embed_ollama(&self, text: &str) -> Result<Vec<f32>> {
        let url = format!("{}/api/embeddings", self.api_base.trim_end_matches('/'));
        let body = OllamaRequest {
            model: &self.model,
            prompt: text,
        };
        let resp = self.http.post(&url).json(&body).send().await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(anyhow!("Ollama embedding 失败 [{}]: {}", status, text));
        }
        let parsed: OllamaEmbeddingResponse = resp.json().await?;
        Ok(parsed.embedding)
    }

    async fn embed_openai(&self, text: &str) -> Result<Vec<f32>> {
        let url = format!("{}/embeddings", self.api_base.trim_end_matches('/'));
        let body = OpenAIRequest {
            model: &self.model,
            input: text,
        };
        let mut req = self.http.post(&url).json(&body);
        if !self.api_key.is_empty() {
            req = req.bearer_auth(&self.api_key);
        }
        let resp = req.send().await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(anyhow!("OpenAI embedding 失败 [{}]: {}", status, text));
        }
        let parsed: OpenAIEmbeddingResponse = resp.json().await?;
        parsed
            .data
            .into_iter()
            .next()
            .map(|d| d.embedding)
            .ok_or_else(|| anyhow!("embedding 响应无 data"))
    }
}

/// 计算两个向量的余弦相似度。
///
/// 用于 memory 模块的相似度检索：cosine = (a·b) / (|a|*|b|)。
/// 返回值范围 [-1, 1]，越接近 1 越相似。
pub fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }
    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let norm_a: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let norm_b: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }
    dot / (norm_a * norm_b)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cosine_similarity_identical() {
        let v = vec![1.0, 2.0, 3.0];
        let sim = cosine_similarity(&v, &v);
        assert!((sim - 1.0).abs() < 1e-5, "相同向量相似度应为 1，实际 {}", sim);
    }

    #[test]
    fn test_cosine_similarity_orthogonal() {
        let a = vec![1.0, 0.0];
        let b = vec![0.0, 1.0];
        let sim = cosine_similarity(&a, &b);
        assert!(sim.abs() < 1e-5, "正交向量相似度应为 0，实际 {}", sim);
    }

    #[test]
    fn test_cosine_similarity_different_lengths() {
        let a = vec![1.0, 2.0];
        let b = vec![1.0];
        // 长度不等返回 0（安全兜底）
        assert_eq!(cosine_similarity(&a, &b), 0.0);
    }

    #[test]
    fn test_cosine_similarity_empty() {
        assert_eq!(cosine_similarity(&[], &[]), 0.0);
    }
}
