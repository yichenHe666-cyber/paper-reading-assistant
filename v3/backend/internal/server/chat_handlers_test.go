// server 包 M2 路由（chat/skills）的 HTTP 契约测试。
//
// 文件概述：chat_handlers_test.go 用 httptest + mock LLM 验证会话/技能端点：
//   - 会话 CRUD
//   - 非流式发消息（mock LLM 返回最终回答）
//   - SSE 流式发消息（验证 text/event-stream 与事件格式）
//   - 技能 CRUD
//   - 手动触发自进化
//
// 关键：用 mock LLM server 替代真实 DeepSeek，保证测试稳定可复现。
package server

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"nuclear-ox-v2/backend/internal/config"
	"nuclear-ox-v2/backend/internal/store"
)

// mockLLMResp 是一个可脚本化的 mock LLM server。每次请求按顺序返回预设响应。
type mockLLMResp struct {
	server    *httptest.Server
	responses []string
	calls     int
}

func newMockLLMResp(responses []string) *mockLLMResp {
	m := &mockLLMResp{responses: responses}
	m.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		idx := m.calls
		m.calls++
		w.Header().Set("Content-Type", "application/json")
		if idx >= len(m.responses) {
			w.WriteHeader(http.StatusInternalServerError)
			io.WriteString(w, `{"error":"mock 脚本耗尽"}`)
			return
		}
		io.WriteString(w, m.responses[idx])
	}))
	return m
}
func (m *mockLLMResp) Close() { m.server.Close() }
func (m *mockLLMResp) URL() string { return m.server.URL }

// chatCompletion 构造一个 chat completion 响应体。
func chatCompletion(content string) string {
	b, _ := json.Marshal(content)
	return `{"id":"r","model":"deepseek-chat","choices":[{"index":0,"message":{"role":"assistant","content":` + string(b) + `},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":3,"total_tokens":8}}`
}

// newTestServerWithMockLLM 构造一个指向 mock LLM 的测试 Server。
// 返回 Server、httptest、mock（供脚本化与断言调用次数）。
func newTestServerWithMockLLM(t *testing.T, llmResponses []string) (*Server, *httptest.Server, *mockLLMResp) {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")
	db, err := store.Open(dbPath)
	if err != nil { t.Fatalf("store.Open: %v", err) }
	if err := store.Migrate(db); err != nil { t.Fatalf("store.Migrate: %v", err) }
	mock := newMockLLMResp(llmResponses)
	cfg := &config.Config{
		DataDir: dir, DBPath: dbPath, LogDir: filepath.Join(dir, "logs"),
		Server: config.ServerConfig{Host: "127.0.0.1", Port: 0},
		LLM: config.LLMConfig{
			Provider: "deepseek", Model: "deepseek-chat",
			APIBase: mock.URL(), APIKey: "k", Timeout: 10,
		},
		GitHub: config.GitHubConfig{DefaultRepo: "pwl/papers"},
	}
	s := New(cfg, db)
	ts := httptest.NewServer(s.Handler())
	t.Cleanup(func() { ts.Close(); db.Close(); mock.Close() })
	return s, ts, mock
}

// TestCreateAndListSessions 验证会话创建与列表。
func TestCreateAndListSessions(t *testing.T) {
	_, ts, _ := newTestServerWithMockLLM(t, nil)

	// 创建
	code, body := doJSON(t, ts, "POST", "/api/chat/sessions", []byte(`{"title":"我的会话","skill_mode":"auto"}`))
	if code != 200 { t.Fatalf("创建会话状态码: %d, body: %s", code, body) }
	var created struct{ ID string `json:"id"` }
	if err := json.Unmarshal(body, &created); err != nil { t.Fatalf("解析: %v", err) }
	if created.ID == "" { t.Error("应返回非空 id") }

	// 列表
	code, body = doGet(t, ts, "/api/chat/sessions")
	if code != 200 { t.Fatalf("列表状态码: %d", code) }
	var list []store.Session
	if err := json.Unmarshal(body, &list); err != nil { t.Fatalf("解析列表: %v", err) }
	if len(list) != 1 || list[0].Title != "我的会话" {
		t.Errorf("列表异常: %+v", list)
	}
}

// TestSendMessageNonStream 验证非流式发消息。
func TestSendMessageNonStream(t *testing.T) {
	_, ts, _ := newTestServerWithMockLLM(t, []string{
		chatCompletion("这是助手回答。"),
	})

	// 先建会话
	_, body := doJSON(t, ts, "POST", "/api/chat/sessions", []byte(`{}`))
	var created struct{ ID string `json:"id"` }
	json.Unmarshal(body, &created)

	// 发消息
	code, body := doJSON(t, ts, "POST", "/api/chat/sessions/"+created.ID+"/messages",
		[]byte(`{"content":"你好"}`))
	if code != 200 { t.Fatalf("发消息状态码: %d, body: %s", code, body) }
	var resp struct {
		Content string `json:"content"`
		Turns   int    `json:"turns"`
	}
	json.Unmarshal(body, &resp)
	if resp.Content != "这是助手回答。" {
		t.Errorf("content 异常: %q", resp.Content)
	}

	// 验证消息落库
	code, body = doGet(t, ts, "/api/chat/sessions/"+created.ID+"/messages")
	if code != 200 { t.Fatalf("查消息状态码: %d", code) }
	var msgs []store.Message
	json.Unmarshal(body, &msgs)
	if len(msgs) != 2 { t.Fatalf("期望 2 条消息，得到 %d", len(msgs)) }
}

// TestSendMessageStream 验证 SSE 流式发消息（痛点③前端乱码关联，但本测试聚焦后端 SSE 格式）。
func TestSendMessageStream(t *testing.T) {
	_, ts, _ := newTestServerWithMockLLM(t, []string{
		chatCompletion("流式回答第一行\n第二行"),
	})

	_, body := doJSON(t, ts, "POST", "/api/chat/sessions", []byte(`{}`))
	var created struct{ ID string `json:"id"` }
	json.Unmarshal(body, &created)

	// 发起 SSE 请求
	req, _ := http.NewRequest("POST", ts.URL+"/api/chat/sessions/"+created.ID+"/messages/stream",
		bytes.NewReader([]byte(`{"content":"hi"}`)))
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil { t.Fatalf("SSE 请求失败: %v", err) }
	defer resp.Body.Close()

	if ct := resp.Header.Get("Content-Type"); !strings.HasPrefix(ct, "text/event-stream") {
		t.Errorf("Content-Type 应为 text/event-stream，实际 %s", ct)
	}

	// 读取全部 SSE 数据
	all, _ := io.ReadAll(resp.Body)
	s := string(all)
	// 应包含 data: 前缀的事件
	if !strings.Contains(s, "data: ") {
		t.Errorf("SSE 应含 data: 事件，实际: %s", s)
	}
	// 应包含 token 与 end 事件
	if !strings.Contains(s, `"type":"token"`) {
		t.Errorf("SSE 应含 token 事件: %s", s)
	}
	if !strings.Contains(s, `"type":"end"`) {
		t.Errorf("SSE 应含 end 标记: %s", s)
	}
}

// TestSendMessageToMissingSession 验证发消息到不存在会话返回 404。
func TestSendMessageToMissingSession(t *testing.T) {
	_, ts, _ := newTestServerWithMockLLM(t, nil)
	code, _ := doJSON(t, ts, "POST", "/api/chat/sessions/nope/messages",
		[]byte(`{"content":"hi"}`))
	if code != 404 {
		t.Errorf("期望 404，得到 %d", code)
	}
}

// TestSkillsCRUD 验证技能增删查。
func TestSkillsCRUD(t *testing.T) {
	_, ts, _ := newTestServerWithMockLLM(t, nil)

	// 空列表应为 []
	code, body := doGet(t, ts, "/api/skills")
	if code != 200 { t.Fatalf("列表状态码: %d", code) }
	if string(body) != "[]" {
		t.Errorf("空技能列表应为 []，实际: %s", body)
	}

	// 创建
	code, body = doJSON(t, ts, "POST", "/api/skills", []byte(`{
		"slug":"my-skill","name":"我的技能","description":"测试","content":"步骤","level":0
	}`))
	if code != 200 { t.Fatalf("创建状态码: %d, body: %s", code, body) }
	var created store.Skill
	json.Unmarshal(body, &created)
	if created.Slug != "my-skill" || created.Name != "我的技能" {
		t.Errorf("创建返回异常: %+v", created)
	}

	// 列表应含 1 条
	_, body = doGet(t, ts, "/api/skills")
	var list []store.Skill
	json.Unmarshal(body, &list)
	if len(list) != 1 { t.Fatalf("期望 1 条技能，得到 %d", len(list)) }

	// 删除
	code, _ = doJSON(t, ts, "DELETE", "/api/skills/my-skill", nil)
	if code != 200 { t.Errorf("删除状态码: %d", code) }

	// 再查应为空
	_, body = doGet(t, ts, "/api/skills")
	if string(body) != "[]" { t.Errorf("删除后应为 []，实际: %s", body) }
}

// TestEvolveSessionManual 验证手动触发会话自进化。
// 流程：建会话 → 发消息造历史（消耗 mock[0]）→ evolve（消耗 mock[1]，返回技能草稿）。
func TestEvolveSessionManual(t *testing.T) {
	draftContent := `{"slug":"manual-skill","name":"手动技能","description":"手动提炼","content":"复用步骤","worth_saving":true}`
	_, ts, _ := newTestServerWithMockLLM(t, []string{
		chatCompletion("助手回答。"),   // 发消息时消耗
		chatCompletion(draftContent), // evolve 时消耗
	})

	// 建会话
	_, body := doJSON(t, ts, "POST", "/api/chat/sessions", []byte(`{}`))
	var created struct{ ID string `json:"id"` }
	json.Unmarshal(body, &created)

	// 发消息造历史
	_, _ = doJSON(t, ts, "POST", "/api/chat/sessions/"+created.ID+"/messages",
		[]byte(`{"content":"帮我总结"}`))

	// 手动触发 evolve
	code, body := doJSON(t, ts, "POST", "/api/chat/evolve",
		[]byte(`{"session_id":"`+created.ID+`"}`))
	if code != 200 { t.Fatalf("evolve 状态码: %d, body: %s", code, body) }
	var resp struct {
		Slug       string `json:"slug"`
		WorthSaving bool  `json:"worth_saving"`
		Saved      bool   `json:"saved"`
	}
	json.Unmarshal(body, &resp)
	if resp.Slug != "manual-skill" { t.Errorf("slug 异常: %s", resp.Slug) }
	if !resp.Saved { t.Error("应 saved=true") }

	// 验证技能落库
	_, body = doGet(t, ts, "/api/skills")
	var list []store.Skill
	json.Unmarshal(body, &list)
	found := false
	for _, s := range list {
		if s.Slug == "manual-skill" { found = true; break }
	}
	if !found { t.Error("提炼的技能应落库") }
}
