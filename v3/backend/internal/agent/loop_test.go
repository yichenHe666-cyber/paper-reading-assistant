// agent 包的契约测试。
//
// 文件概述：loop_test.go 用 httptest mock LLM server 验证 agent loop 的关键路径，
// 覆盖 spec §4.1 修复方案"真正 agent loop + 流式统一 channel"：
//   - 直接回答路径（无工具调用）：token + usage + done
//   - 多轮工具调用路径：tool_call → tool_result → token → done（多步推理可跑通）
//   - 4xx 错误：error 事件后 channel 关闭（不卡死、不抛 panic）
//   - 达 maxTurns：error 事件明确提示
//   - token 预算耗尽：error 事件
//
// 这些测试是 M2 验收"多轮工具调用成功 + 流式不崩"的底层保证。
package agent

import (
	"context"
	"database/sql"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"nuclear-ox-v2/backend/internal/llm"
	"nuclear-ox-v2/backend/internal/paper"
	"nuclear-ox-v2/backend/internal/store"
)

// mockLLMServer 构造一个可脚本化的 mock LLM server。
// responses 按调用顺序依次返回；status 非 0 时返回该状态码 + body（模拟错误）。
type mockLLMServer struct {
	server    *httptest.Server
	responses []mockResponse
	calls     int
}

type mockResponse struct {
	status int    // 0 表示 200
	body   string // 响应体
}

func newMockLLMServer(responses []mockResponse) *mockLLMServer {
	m := &mockLLMServer{responses: responses}
	m.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		idx := m.calls
		m.calls++
		if idx >= len(m.responses) {
			// 超出脚本：返回 500 帮助测试失败定位
			w.WriteHeader(http.StatusInternalServerError)
			io.WriteString(w, `{"error":"mock 脚本耗尽"}`)
			return
		}
		resp := m.responses[idx]
		w.Header().Set("Content-Type", "application/json")
		if resp.status != 0 {
			w.WriteHeader(resp.status)
		}
		io.WriteString(w, resp.body)
	}))
	return m
}

func (m *mockLLMServer) Close() { m.server.Close() }
func (m *mockLLMServer) URL() string { return m.server.URL }

// mockFinalAnswer 构造一个"最终回答"响应（无工具调用）。
func mockFinalAnswer(content string, total int) string {
	return `{"id":"r","model":"deepseek-chat","choices":[{"index":0,"message":{"role":"assistant","content":` + jsonStr(content) + `},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":3,"total_tokens":` + itoa(total) + `}}`
}

// mockToolCall 构造一个"工具调用"响应。
func mockToolCall(callID, name, args string) string {
	tc, _ := json.Marshal([]map[string]any{{
		"id": callID, "type": "function",
		"function": map[string]string{"name": name, "arguments": args},
	}})
	return `{"id":"r","model":"deepseek-chat","choices":[{"index":0,"message":{"role":"assistant","content":"","tool_calls":` + string(tc) + `},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":5,"completion_tokens":1,"total_tokens":6}}`
}

// jsonStr/itoa 是测试辅助（避免 import 重复）。
func jsonStr(s string) string { b, _ := json.Marshal(s); return string(b) }
func itoa(n int) string {
	if n == 0 { return "0" }
	neg := n < 0
	if neg { n = -n }
	var b [20]byte
	i := len(b)
	for n > 0 { i--; b[i] = byte('0' + n%10); n /= 10 }
	if neg { i--; b[i] = '-' }
	return string(b[i:])
}

// newTestAgentDB 建测试库 + 插入一个主题+一篇论文，返回 db 与 repo。
func newTestAgentDB(t *testing.T) (*sql.DB, *paper.Repository) {
	t.Helper()
	dbPath := t.TempDir() + "/agent.db"
	db, err := store.Open(dbPath)
	if err != nil { t.Fatalf("Open: %v", err) }
	t.Cleanup(func() { db.Close() })
	if err := store.Migrate(db); err != nil { t.Fatalf("Migrate: %v", err) }
	repo := paper.NewRepository(db)
	// 插入主题 + 论文
	if err := repo.UpsertTopic(paper.Topic{
		ID: "distributed", Name: "Distributed Systems", NameCN: "分布式系统",
	}); err != nil {
		t.Fatalf("UpsertTopic: %v", err)
	}
	if err := repo.UpsertPaper(paper.Paper{
		ID: "distributed_mapreduce", Title: "MapReduce", Authors: "Dean, Ghemawat",
		Year: 2004, TopicID: "distributed", Abstract: "Simplified data processing on large clusters.",
	}); err != nil {
		t.Fatalf("UpsertPaper: %v", err)
	}
	return db, repo
}

// drainEvents 消费 channel 全部事件并返回。
func drainEvents(ch <-chan StreamEvent) []StreamEvent {
	var out []StreamEvent
	for ev := range ch {
		out = append(out, ev)
	}
	return out
}

// TestAgentRunDirectAnswer 验证无工具调用的直接回答路径。
func TestAgentRunDirectAnswer(t *testing.T) {
	mock := newMockLLMServer([]mockResponse{
		{body: mockFinalAnswer("你好，我是科研助手。", 8)},
	})
	defer mock.Close()

	c := llm.New("deepseek", "deepseek-chat", mock.URL(), "k", 10)
	a := NewAgent(c, NewToolRegistry(), WithPerTurnTimeout(5*time.Second))

	events := drainEvents(a.Run(context.Background(), []llm.Message{
		{Role: llm.RoleUser, Content: "你好"},
	}))

	// 期望：usage + 至少一个 token + done
	var hasToken, hasUsage, hasDone bool
	var tokenContent string
	for _, ev := range events {
		switch ev.Type {
		case EventToken:
			hasToken = true
			tokenContent += ev.Content
		case EventUsage:
			hasUsage = true
		case EventDone:
			hasDone = true
		case EventError:
			t.Fatalf("不应有 error 事件: %s", ev.Content)
		}
	}
	if !hasToken || tokenContent != "你好，我是科研助手。" {
		t.Errorf("token 内容异常: %q", tokenContent)
	}
	if !hasUsage { t.Error("缺少 usage 事件") }
	if !hasDone { t.Error("缺少 done 事件") }
	if mock.calls != 1 { t.Errorf("LLM 应被调用 1 次，实际 %d", mock.calls) }
}

// TestAgentRunWithTools 验证多轮工具调用路径（痛点①根因 #6"无 agent loop"的修复）。
// 流程：模型先要调 list_topics → 执行 → 模型基于结果给出最终回答。
func TestAgentRunWithTools(t *testing.T) {
	db, repo := newTestAgentDB(t)
	_ = db
	mock := newMockLLMServer([]mockResponse{
		// 第 1 轮：模型决定调用 list_topics
		{body: mockToolCall("c1", "list_topics", "{}")},
		// 第 2 轮：模型基于工具结果给出最终回答
		{body: mockFinalAnswer("找到分布式系统主题。", 10)},
	})
	defer mock.Close()

	c := llm.New("deepseek", "deepseek-chat", mock.URL(), "k", 10)
	tools := NewToolRegistry()
	RegisterBuiltinTools(tools, repo)
	a := NewAgent(c, tools, WithPerTurnTimeout(5*time.Second))

	events := drainEvents(a.Run(context.Background(), []llm.Message{
		{Role: llm.RoleUser, Content: "有哪些主题？"},
	}))

	// 期望事件序列：usage, tool_call, tool_result, usage, token(s), done
	var hasToolCall, hasToolResult, hasDone bool
	var toolResultContent string
	for _, ev := range events {
		switch ev.Type {
		case EventToolCall:
			hasToolCall = true
			if ev.ToolName != "list_topics" {
				t.Errorf("工具名期望 list_topics，得到 %s", ev.ToolName)
			}
		case EventToolResult:
			hasToolResult = true
			toolResultContent = ev.ToolResult
		case EventError:
			t.Fatalf("不应有 error: %s", ev.Content)
		case EventDone:
			hasDone = true
		}
	}
	if !hasToolCall { t.Error("缺少 tool_call 事件") }
	if !hasToolResult { t.Error("缺少 tool_result 事件") }
	if !hasDone { t.Error("缺少 done 事件") }
	// 工具结果应包含我们插入的主题
	if !strings.Contains(toolResultContent, "Distributed Systems") && !strings.Contains(toolResultContent, "distributed") {
		t.Errorf("工具结果应含主题，实际: %s", toolResultContent)
	}
	if mock.calls != 2 { t.Errorf("LLM 应被调用 2 次（两轮），实际 %d", mock.calls) }
}

// TestAgentRunError4xx 验证 4xx 错误产生 error 事件后 channel 正常关闭（不卡死）。
func TestAgentRunError4xx(t *testing.T) {
	mock := newMockLLMServer([]mockResponse{
		{status: 400, body: `{"error":{"message":"bad param"}}`},
	})
	defer mock.Close()

	c := llm.New("deepseek", "deepseek-chat", mock.URL(), "k", 10)
	a := NewAgent(c, NewToolRegistry(), WithRetryOn5xx(false), WithPerTurnTimeout(5*time.Second))

	events := drainEvents(a.Run(context.Background(), []llm.Message{
		{Role: llm.RoleUser, Content: "hi"},
	}))

	var hasError bool
	for _, ev := range events {
		if ev.Type == EventError {
			hasError = true
			if !strings.Contains(ev.Content, "不可重试") && !strings.Contains(ev.Content, "失败") {
				t.Errorf("error 内容异常: %s", ev.Content)
			}
		}
		if ev.Type == EventDone {
			t.Error("4xx 不应有 done 事件")
		}
	}
	if !hasError { t.Error("缺少 error 事件") }
}

// TestAgentRunMaxTurns 验证达 maxTurns 仍无最终回答时产生明确 error。
func TestAgentRunMaxTurns(t *testing.T) {
	// mock 每次都返回工具调用，永不给最终回答
	responses := make([]mockResponse, 10)
	for i := range responses {
		responses[i] = mockResponse{body: mockToolCall("c"+itoa(i), "list_topics", "{}")}
	}
	mock := newMockLLMServer(responses)
	defer mock.Close()

	c := llm.New("deepseek", "deepseek-chat", mock.URL(), "k", 10)
	db, repo := newTestAgentDB(t)
	_ = db
	tools := NewToolRegistry()
	RegisterBuiltinTools(tools, repo)
	a := NewAgent(c, tools, WithMaxTurns(3), WithPerTurnTimeout(5*time.Second))

	events := drainEvents(a.Run(context.Background(), []llm.Message{
		{Role: llm.RoleUser, Content: "loop"},
	}))

	var hasMaxTurnsError bool
	for _, ev := range events {
		if ev.Type == EventError && strings.Contains(ev.Content, "最大轮数") {
			hasMaxTurnsError = true
		}
	}
	if !hasMaxTurnsError { t.Error("应产生'达到最大轮数'error 事件") }
}

// TestAgentRunTokenBudgetExceeded 验证累计超预算时终止。
func TestAgentRunTokenBudgetExceeded(t *testing.T) {
	// 第 1 轮返回工具调用（小用量），第 2 轮预算检查时已超 → error
	mock := newMockLLMServer([]mockResponse{
		{body: mockToolCall("c1", "list_topics", "{}")}, // usage total=6
	})
	defer mock.Close()

	c := llm.New("deepseek", "deepseek-chat", mock.URL(), "k", 10)
	db, repo := newTestAgentDB(t)
	_ = db
	tools := NewToolRegistry()
	RegisterBuiltinTools(tools, repo)
	// 预算设 5：第一轮 0<5 通过，调用后累计 6；第二轮 6>=5 触发预算耗尽 error
	a := NewAgent(c, tools, WithTokenBudget(5), WithMaxTurns(5), WithPerTurnTimeout(5*time.Second))

	events := drainEvents(a.Run(context.Background(), []llm.Message{
		{Role: llm.RoleUser, Content: "q"},
	}))

	var hasBudgetError bool
	for _, ev := range events {
		if ev.Type == EventError && strings.Contains(ev.Content, "预算") {
			hasBudgetError = true
		}
	}
	if !hasBudgetError { t.Error("应产生预算耗尽 error 事件") }
}

// TestToolRegistryBuiltin 验证内置工具注册与执行。
func TestToolRegistryBuiltin(t *testing.T) {
	db, repo := newTestAgentDB(t)
	_ = db
	r := NewToolRegistry()
	RegisterBuiltinTools(r, repo)

	if !r.Has("list_topics") || !r.Has("search_papers") || !r.Has("get_paper") {
		t.Error("内置工具未全部注册")
	}
	defs := r.Definitions()
	if len(defs) != 3 {
		t.Errorf("期望 3 个工具定义，得到 %d", len(defs))
	}

	// 执行 list_topics
	res, err := r.Execute(context.Background(), "list_topics", "{}")
	if err != nil { t.Fatalf("list_topics 执行失败: %v", err) }
	if !strings.Contains(res, "Distributed Systems") {
		t.Errorf("list_topics 结果应含主题: %s", res)
	}

	// 执行 get_paper
	res2, err := r.Execute(context.Background(), "get_paper", `{"id":"distributed_mapreduce"}`)
	if err != nil { t.Fatalf("get_paper 失败: %v", err) }
	if !strings.Contains(res2, "MapReduce") {
		t.Errorf("get_paper 结果应含 MapReduce: %s", res2)
	}

	// 未知工具
	_, err = r.Execute(context.Background(), "nope", "{}")
	if err == nil { t.Error("未知工具应报错") }
}
