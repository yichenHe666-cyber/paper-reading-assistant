// Package memory 的 client 单元测试。
//
// 用 httptest 起 mock server 模拟 Rust core，验证 client：
//   - 请求方法/路径/查询参数/请求体正确；
//   - 成功响应正确解码；
//   - 404 返回 (nil, nil)；
//   - 错误响应 {"error":"..."} 被解码为带状态码的 Go error。
//
// 不依赖真实 Rust core 启动，纯契约测试。
package memory

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// mockCore 起 mock Rust core，返回 client 与请求记录器。
// handler 决定如何响应每个请求。
func mockCore(t *testing.T, handler http.HandlerFunc) (*Client, *httptest.Server) {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	// baseURL 形如 http://127.0.0.1:PORT，不带尾部 /
	return New(srv.URL, 5.0), srv
}

// requestRecord 记录最近一次请求的方法、路径、请求体，供断言。
type requestRecord struct {
	method string
	path   string
	body   string
}

// recorder 返回一个 handler，记录请求到 rec 并委托给 next。
func recorder(rec *requestRecord, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		rec.method = r.Method
		rec.path = r.URL.Path
		if r.Body != nil {
			b, _ := io.ReadAll(r.Body)
			rec.body = string(b)
		}
		next(w, r)
	}
}

func writeJSON(t *testing.T, w http.ResponseWriter, status int, v any) {
	t.Helper()
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		t.Fatalf("写入响应失败: %v", err)
	}
}

// --- 记忆 CRUD 测试 ---

func TestCreateMemory(t *testing.T) {
	var rec requestRecord
	client, _ := mockCore(t, recorder(&rec, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/memory" {
			t.Errorf("请求不匹配：got %s %s, want POST /memory", r.Method, r.URL.Path)
		}
		// 验证请求体含 layer/content
		if !strings.Contains(rec.body, `"layer":"episodic"`) || !strings.Contains(rec.body, `"content":"hello"`) {
			t.Errorf("请求体缺失字段: %s", rec.body)
		}
		writeJSON(t, w, http.StatusCreated, Memory{
			ID: "m1", Layer: "episodic", Content: "hello", ImportanceScore: 0.7,
			DecayState: "active", EmbeddingID: "e1", CreatedAt: "2026-06-27T00:00:00Z",
		})
	}))

	m, err := client.CreateMemory(context.Background(), CreateMemoryRequest{
		Layer: LayerEpisodic, Content: "hello", ImportanceScore: 0.7,
	})
	if err != nil {
		t.Fatalf("CreateMemory 失败: %v", err)
	}
	if m.ID != "m1" || m.Layer != "episodic" || m.Content != "hello" {
		t.Errorf("响应解码错误: %+v", m)
	}
}

func TestGetMemory_NotFound(t *testing.T) {
	client, _ := mockCore(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(t, w, http.StatusNotFound, map[string]string{"error": "记忆不存在"})
	})
	m, err := client.GetMemory(context.Background(), "nope")
	if err != nil {
		t.Fatalf("404 应返回 nil,nil，得 err: %v", err)
	}
	if m != nil {
		t.Errorf("404 应返回 nil Memory，得 %+v", m)
	}
}

func TestGetMemory_OK(t *testing.T) {
	var rec requestRecord
	client, _ := mockCore(t, recorder(&rec, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/memory/m1" {
			t.Errorf("路径错误: got %s, want /memory/m1", r.URL.Path)
		}
		writeJSON(t, w, http.StatusOK, Memory{ID: "m1", Layer: "episodic", Content: "x"})
	}))
	m, err := client.GetMemory(context.Background(), "m1")
	if err != nil || m == nil {
		t.Fatalf("GetMemory 失败: %v m=%v", err, m)
	}
	if m.ID != "m1" {
		t.Errorf("ID 错误: %s", m.ID)
	}
}

func TestDeleteMemory(t *testing.T) {
	var rec requestRecord
	client, _ := mockCore(t, recorder(&rec, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("方法错误: %s", r.Method)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	if err := client.DeleteMemory(context.Background(), "m1"); err != nil {
		t.Fatalf("DeleteMemory 失败: %v", err)
	}
}

func TestSearchMemory_QueryParams(t *testing.T) {
	var rec requestRecord
	client, _ := mockCore(t, recorder(&rec, func(w http.ResponseWriter, r *http.Request) {
		// 验证 keyword 与 limit 查询参数
		q := r.URL.Query()
		if q.Get("keyword") != "分布式" {
			t.Errorf("keyword 参数错误: %s", q.Get("keyword"))
		}
		if q.Get("limit") != "10" {
			t.Errorf("limit 参数错误: %s", q.Get("limit"))
		}
		writeJSON(t, w, http.StatusOK, map[string]any{
			"items": []Memory{{ID: "m1", Content: "分布式系统"}},
		})
	}))
	items, err := client.SearchMemory(context.Background(), "分布式", 10)
	if err != nil {
		t.Fatalf("SearchMemory 失败: %v", err)
	}
	if len(items) != 1 || items[0].ID != "m1" {
		t.Errorf("解码错误: %+v", items)
	}
}

func TestSearchVector(t *testing.T) {
	var rec requestRecord
	client, _ := mockCore(t, recorder(&rec, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/memory/search-vector" {
			t.Errorf("请求不匹配：got %s %s", r.Method, r.URL.Path)
		}
		// 验证请求体
		if !strings.Contains(rec.body, `"query":"vector"`) || !strings.Contains(rec.body, `"top_k":3`) {
			t.Errorf("请求体错误: %s", rec.body)
		}
		writeJSON(t, w, http.StatusOK, map[string]any{
			"items": []SimilarMemory{{Memory: Memory{ID: "m1"}, Similarity: 0.9}},
		})
	}))
	items, err := client.SearchVector(context.Background(), "vector", 3)
	if err != nil {
		t.Fatalf("SearchVector 失败: %v", err)
	}
	if len(items) != 1 || items[0].Similarity != 0.9 {
		t.Errorf("解码错误: %+v", items)
	}
}

// --- 梦境测试 ---

func TestTriggerDream(t *testing.T) {
	var rec requestRecord
	client, _ := mockCore(t, recorder(&rec, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/dream" {
			t.Errorf("请求不匹配：got %s %s, want POST /dream", r.Method, r.URL.Path)
		}
		writeJSON(t, w, http.StatusOK, DreamResult{
			DiaryID: "d1", PromotedCount: 2, DecayedCount: 1,
			Summary: "升级 2 条，衰减 1 条",
		})
	}))
	r, err := client.TriggerDream(context.Background())
	if err != nil {
		t.Fatalf("TriggerDream 失败: %v", err)
	}
	if r.DiaryID != "d1" || r.PromotedCount != 2 || r.DecayedCount != 1 {
		t.Errorf("解码错误: %+v", r)
	}
}

func TestListDreamDiary(t *testing.T) {
	client, _ := mockCore(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/dream-diary" {
			t.Errorf("路径错误: %s", r.URL.Path)
		}
		writeJSON(t, w, http.StatusOK, map[string]any{
			"items": []DreamDiaryEntry{{ID: "d1", RunID: "r1", Stage: "done"}},
		})
	})
	items, err := client.ListDreamDiary(context.Background(), 5)
	if err != nil {
		t.Fatalf("ListDreamDiary 失败: %v", err)
	}
	if len(items) != 1 || items[0].RunID != "r1" {
		t.Errorf("解码错误（run_id 缺失?）: %+v", items)
	}
}

func TestGetDreamDiary_NotFound(t *testing.T) {
	client, _ := mockCore(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(t, w, http.StatusNotFound, map[string]string{"error": "不存在"})
	})
	d, err := client.GetDreamDiary(context.Background(), "nope")
	if err != nil || d != nil {
		t.Errorf("404 应返回 nil,nil，得 err=%v d=%v", err, d)
	}
}

// --- 决策测试 ---

func TestAddDecision(t *testing.T) {
	client, _ := mockCore(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/decision" {
			t.Errorf("路径错误: %s", r.URL.Path)
		}
		writeJSON(t, w, http.StatusCreated, DecisionEntry{
			ID: "dec1", Decision: "采用 Rust", Rationale: "性能",
		})
	})
	d, err := client.AddDecision(context.Background(), CreateDecisionRequest{
		Decision: "采用 Rust", Rationale: "性能",
	})
	if err != nil {
		t.Fatalf("AddDecision 失败: %v", err)
	}
	if d.ID != "dec1" || d.Decision != "采用 Rust" {
		t.Errorf("解码错误: %+v", d)
	}
}

func TestListDecisions(t *testing.T) {
	client, _ := mockCore(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(t, w, http.StatusOK, map[string]any{
			"items": []DecisionEntry{{ID: "dec1"}},
		})
	})
	items, err := client.ListDecisions(context.Background(), 0)
	if err != nil {
		t.Fatalf("ListDecisions 失败: %v", err)
	}
	if len(items) != 1 {
		t.Errorf("解码错误: %+v", items)
	}
}

// --- 错误处理测试 ---

func TestCoreError_Decoded(t *testing.T) {
	client, _ := mockCore(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(t, w, http.StatusInternalServerError, map[string]string{
			"error": "数据库锁定",
		})
	})
	_, err := client.TriggerDream(context.Background())
	if err == nil {
		t.Fatal("应返回错误")
	}
	// 错误信息应包含状态码与 core 的 error 字段
	if !strings.Contains(err.Error(), "500") || !strings.Contains(err.Error(), "数据库锁定") {
		t.Errorf("错误信息未含状态码/原文: %v", err)
	}
}

func TestCoreError_ConnectionRefused(t *testing.T) {
	// 指向一个不存在的端口，触发连接错误
	client := New("http://127.0.0.1:1", 1.0)
	_, err := client.TriggerDream(context.Background())
	if err == nil {
		t.Fatal("连接失败应返回错误")
	}
}
