// agent 包 Evolver 的测试，验证自进化雏形（spec §6）。
//
// 覆盖：
//   - DistillSkill：mock LLM 返回合法技能草稿 JSON → 解析 + 落库
//   - DistillSkill 安全：草稿含凭证 → 拒绝
//   - DistillSkill 安全：slug 含路径分隔符 → 拒绝
//   - TrackUsage：usage_count +1，成功率更新
//   - ShouldDistill 阈值判定
package agent

import (
	"context"
	"strings"
	"testing"
	"time"

	"nuclear-ox-v2/backend/internal/llm"
	"nuclear-ox-v2/backend/internal/store"
)

// newTestEvolver 构造接 mock LLM 的 Evolver。
func newTestEvolver(t *testing.T, responses []mockResponse) (*Evolver, *mockLLMServer, *store.Skill) {
	t.Helper()
	db, _ := newTestAgentDB(t)
	mock := newMockLLMServer(responses)
	c := llm.New("deepseek", "deepseek-chat", mock.URL(), "k", 10)
	t.Cleanup(mock.Close)
	return NewEvolver(c, db), mock, nil
}

// mockDraftResp 构造 LLM 返回的技能草稿 chat completion 响应。
// 草稿 JSON 作为 message.content（已转义），符合 OpenAI 响应格式。
func mockDraftResp(slug, name, desc, content string, worth bool) string {
	w := "false"
	if worth { w = "true" }
	draftJSON := `{"slug":` + jsonStr(slug) + `,"name":` + jsonStr(name) +
		`,"description":` + jsonStr(desc) + `,"content":` + jsonStr(content) +
		`,"worth_saving":` + w + `}`
	// 包装为 chat completion，草稿 JSON 作为 content
	return `{"id":"r","model":"deepseek-chat","choices":[{"index":0,"message":{"role":"assistant","content":` + jsonStr(draftJSON) + `},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":3,"total_tokens":8}}`
}

// TestDistillSkillSuccess 验证合法草稿被解析并落库。
func TestDistillSkillSuccess(t *testing.T) {
	evolver, _, _ := newTestEvolver(t, []mockResponse{
		{body: mockDraftResp("paper-summary", "论文摘要", "生成结构化摘要",
			"1.读标题 2.读摘要 3.提炼要点", true)},
	})

	msgs := []store.Message{
		{ID: "m1", SessionID: "s1", Role: "user", Content: "帮我总结这篇论文"},
		{ID: "m2", SessionID: "s1", Role: "assistant", Content: "好的，先调用 get_paper..."},
	}
	draft, err := evolver.DistillSkill(context.Background(), msgs)
	if err != nil { t.Fatalf("DistillSkill 失败: %v", err) }
	if !draft.WorthSaving { t.Error("应 WorthSaving=true") }
	if draft.Slug != "paper-summary" { t.Errorf("slug 异常: %s", draft.Slug) }

	// 验证落库
	got, err := store.GetSkillBySlug(evolver.db, "paper-summary")
	if err != nil { t.Fatalf("技能未落库: %v", err) }
	if got.Name != "论文摘要" || !strings.Contains(got.Content, "读标题") {
		t.Errorf("落库技能内容异常: %+v", got)
	}
	if !got.Enabled { t.Error("落库技能应默认启用") }
}

// TestDistillSkillRejectsCredential 验证草稿含凭证被拒绝（spec §6.5 安全缰绳）。
func TestDistillSkillRejectsCredential(t *testing.T) {
	evolver, _, _ := newTestEvolver(t, []mockResponse{
		{body: mockDraftResp("leaky", "泄漏", "含凭证",
			"使用 sk-abc123 调用 API", true)},
	})

	_, err := evolver.DistillSkill(context.Background(), []store.Message{
		{ID: "m1", SessionID: "s1", Role: "user", Content: "x"},
	})
	if err == nil { t.Fatal("含凭证的草稿应被拒绝") }
	if !strings.Contains(err.Error(), "凭证") {
		t.Errorf("错误应提示凭证问题，实际: %v", err)
	}
	// 验证未落库
	if _, err := store.GetSkillBySlug(evolver.db, "leaky"); err == nil {
		t.Error("含凭证技能不应落库")
	}
}

// TestDistillSkillRejectsBadSlug 验证 slug 含路径分隔符被拒绝（路径遍历防护）。
func TestDistillSkillRejectsBadSlug(t *testing.T) {
	evolver, _, _ := newTestEvolver(t, []mockResponse{
		{body: mockDraftResp("../etc/passwd", "恶意", "x", "y", true)},
	})

	_, err := evolver.DistillSkill(context.Background(), []store.Message{
		{ID: "m1", SessionID: "s1", Role: "user", Content: "x"},
	})
	if err == nil { t.Fatal("恶意 slug 应被拒绝") }
	if !strings.Contains(err.Error(), "非法字符") {
		t.Errorf("错误应提示非法字符，实际: %v", err)
	}
}

// TestDistillSkillNotWorthSaving 验证 worth_saving=false 时不落库。
func TestDistillSkillNotWorthSaving(t *testing.T) {
	evolver, _, _ := newTestEvolver(t, []mockResponse{
		{body: mockDraftResp("chitchat", "闲聊", "不值得", "无", false)},
	})

	draft, err := evolver.DistillSkill(context.Background(), []store.Message{
		{ID: "m1", SessionID: "s1", Role: "user", Content: "今天天气不错"},
	})
	if err != nil { t.Fatalf("DistillSkill 失败: %v", err) }
	if draft.WorthSaving { t.Error("应 WorthSaving=false") }
	if _, err := store.GetSkillBySlug(evolver.db, "chitchat"); err == nil {
		t.Error("worth_saving=false 的技能不应落库")
	}
}

// TestTrackUsage 验证用量统计更新。
func TestTrackUsage(t *testing.T) {
	evolver, _, _ := newTestEvolver(t, nil)
	// 先注册一个技能
	_ = store.RegisterBuiltin(evolver.db, store.Skill{
		Slug: "demo", Name: "D", Description: "d", Content: "c", Enabled: true,
	})

	// 成功使用 3 次
	for i := 0; i < 3; i++ {
		if err := evolver.TrackUsage([]string{"demo"}, true); err != nil {
			t.Fatalf("TrackUsage 失败: %v", err)
		}
	}
	got, _ := store.GetSkillBySlug(evolver.db, "demo")
	if got.UsageCount != 3 { t.Errorf("usage_count 期望 3，得到 %d", got.UsageCount) }
	if got.SuccessRate < 0.6 { // 3 次成功 EMA 应较高
		t.Errorf("成功率应较高，得到 %v", got.SuccessRate)
	}
	if got.Version != 4 { t.Errorf("version 期望 4（1+3），得到 %d", got.Version) }
}

// TestTrackUsageMissingSkill 验证统计不存在的技能不报错（用户可能已删除）。
func TestTrackUsageMissingSkill(t *testing.T) {
	evolver, _, _ := newTestEvolver(t, nil)
	if err := evolver.TrackUsage([]string{"nonexistent"}, true); err != nil {
		t.Errorf("不存在的技能应跳过不报错，得到 %v", err)
	}
}

// TestShouldDistill 验证阈值判定。
func TestShouldDistill(t *testing.T) {
	evolver, _, _ := newTestEvolver(t, nil)
	if evolver.ShouldDistill(14) { t.Error("14 次应不触发") }
	if !evolver.ShouldDistill(15) { t.Error("15 次应触发") }
	if !evolver.ShouldDistill(100) { t.Error("100 次应触发") }
}

// 确保时间包被引用（部分构造用）
var _ = time.Second
