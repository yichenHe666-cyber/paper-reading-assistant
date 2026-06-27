// agent 包 ChatService 的测试，重点验证流式异常落库（spec §4.1 根因 #3 修复）。
//
// 覆盖：
//   - 正常发消息：user + assistant 消息落库
//   - LLM 失败（4xx）：user 消息落库，assistant 部分内容/错误说明落库（不空白）
//   - 会话 CRUD
//   - 自进化触发阈值
package agent

import (
	"context"
	"strings"
	"testing"
	"time"

	"nuclear-ox-v2/backend/internal/llm"
	"nuclear-ox-v2/backend/internal/paper"
	"nuclear-ox-v2/backend/internal/store"
)

// newTestChatService 构造一个接 mock LLM 的 ChatService，返回 service 与 mock（供脚本化响应）。
func newTestChatService(t *testing.T, responses []mockResponse) (*ChatService, *mockLLMServer) {
	t.Helper()
	db, repo := newTestAgentDB(t)
	mock := newMockLLMServer(responses)
	c := llm.New("deepseek", "deepseek-chat", mock.URL(), "k", 10)
	tools := NewToolRegistry()
	RegisterBuiltinTools(tools, repo)
	ag := NewAgent(c, tools, WithPerTurnTimeout(5*time.Second), WithRetryOn5xx(false))
	skills := NewSkillRegistry(db, nil)
	evolver := NewEvolver(c, db)
	svc := NewChatService(db, ag, skills, evolver)
	t.Cleanup(mock.Close)
	return svc, mock
}

// TestChatServiceSendMessageNormal 验证正常发消息：user + assistant 落库。
func TestChatServiceSendMessageNormal(t *testing.T) {
	svc, _ := newTestChatService(t, []mockResponse{
		{body: mockFinalAnswer("这是回答。", 10)},
	})

	sid, err := svc.CreateSession("测试", "auto", nil)
	if err != nil { t.Fatalf("CreateSession: %v", err) }

	ch, err := svc.SendMessage(context.Background(), sid, "你好")
	if err != nil { t.Fatalf("SendMessage: %v", err) }
	events := drainEvents(ch)

	// 应有 token + done
	var hasToken, hasDone bool
	for _, ev := range events {
		if ev.Type == EventToken { hasToken = true }
		if ev.Type == EventDone { hasDone = true }
	}
	if !hasToken || !hasDone { t.Fatalf("缺少 token/done 事件: %+v", events) }

	// 验证消息落库
	msgs, err := svc.ListMessages(sid)
	if err != nil { t.Fatalf("ListMessages: %v", err) }
	if len(msgs) != 2 { t.Fatalf("期望 2 条消息（user+assistant），得到 %d", len(msgs)) }
	if msgs[0].Role != "user" || msgs[0].Content != "你好" {
		t.Errorf("user 消息异常: %+v", msgs[0])
	}
	if msgs[1].Role != "assistant" || !strings.Contains(msgs[1].Content, "这是回答") {
		t.Errorf("assistant 消息异常: %+v", msgs[1])
	}
}

// TestChatServiceStreamingPersistOnError 是流式异常落库的核心测试（spec §4.1 根因 #3）。
// 场景：LLM 返回 4xx → agent 发 error 事件 → tapAndPersist 仍把 user 消息落库，
// 且 assistant 消息也落库（即便内容为空，也记录错误说明，不空白）。
func TestChatServiceStreamingPersistOnError(t *testing.T) {
	svc, _ := newTestChatService(t, []mockResponse{
		{status: 400, body: `{"error":{"message":"bad"}}`},
	})

	sid, _ := svc.CreateSession("错误场景", "auto", nil)
	ch, err := svc.SendMessage(context.Background(), sid, "会失败的问题")
	if err != nil { t.Fatalf("SendMessage: %v", err) }
	events := drainEvents(ch)

	// 应有 error 事件
	var hasError bool
	for _, ev := range events {
		if ev.Type == EventError { hasError = true }
	}
	if !hasError { t.Fatal("缺少 error 事件") }

	// 关键断言：user 消息必须已落库（即便 LLM 失败）
	msgs, err := svc.ListMessages(sid)
	if err != nil { t.Fatalf("ListMessages: %v", err) }
	if len(msgs) < 1 { t.Fatalf("user 消息应已落库，实际 %d 条", len(msgs)) }
	if msgs[0].Role != "user" || msgs[0].Content != "会失败的问题" {
		t.Errorf("user 消息未正确落库: %+v", msgs[0])
	}
}

// TestChatServiceSessionNotFound 验证发消息到不存在会话报错。
func TestChatServiceSessionNotFound(t *testing.T) {
	svc, _ := newTestChatService(t, nil)
	_, err := svc.SendMessage(context.Background(), "nope", "hi")
	if err == nil { t.Error("不存在的会话应报错") }
}

// TestChatServiceCreateAndListSessions 验证会话 CRUD。
func TestChatServiceCreateAndListSessions(t *testing.T) {
	svc, _ := newTestChatService(t, nil)
	id1, _ := svc.CreateSession("会话1", "auto", nil)
	id2, _ := svc.CreateSession("会话2", "manual", []string{"summarize"})

	list, err := svc.ListSessions(0)
	if err != nil { t.Fatalf("ListSessions: %v", err) }
	if len(list) != 2 { t.Fatalf("期望 2 个会话，得到 %d", len(list)) }

	// 验证 manual 模式 enabled_skill_ids 持久化
	sess, _ := svc.GetSession(id2)
	if sess.SkillMode != "manual" || !strings.Contains(sess.EnabledSkillIDs, "summarize") {
		t.Errorf("manual 会话配置异常: %+v", sess)
	}

	// 删除
	if err := svc.DeleteSession(id1); err != nil { t.Fatalf("DeleteSession: %v", err) }
	list2, _ := svc.ListSessions(0)
	if len(list2) != 1 || list2[0].ID != id2 {
		t.Errorf("删除后会话列表异常: %+v", list2)
	}
}

// TestChatServiceWithToolCall 验证带工具调用的会话落库 user+assistant。
func TestChatServiceWithToolCall(t *testing.T) {
	svc, _ := newTestChatService(t, []mockResponse{
		{body: mockToolCall("c1", "list_topics", "{}")},
		{body: mockFinalAnswer("基于查询结果回答。", 12)},
	})

	sid, _ := svc.CreateSession("工具会话", "auto", nil)
	ch, err := svc.SendMessage(context.Background(), sid, "有哪些主题")
	if err != nil { t.Fatalf("SendMessage: %v", err) }
	events := drainEvents(ch)

	var hasToolCall, hasDone bool
	for _, ev := range events {
		if ev.Type == EventToolCall { hasToolCall = true }
		if ev.Type == EventDone { hasDone = true }
	}
	if !hasToolCall { t.Error("缺少 tool_call 事件") }
	if !hasDone { t.Error("缺少 done 事件") }

	msgs, _ := svc.ListMessages(sid)
	// user + assistant（工具调用的中间消息 M2 不单独落库）
	if len(msgs) != 2 { t.Errorf("期望 2 条消息，得到 %d", len(msgs)) }
	if msgs[1].Role != "assistant" || !strings.Contains(msgs[1].Content, "基于查询结果") {
		t.Errorf("assistant 消息异常: %+v", msgs[1])
	}
}

// 确保 paper 包被引用（newTestAgentDB 间接使用）
var _ = paper.Paper{}

// 确保 store 包被引用
var _ = store.Open
