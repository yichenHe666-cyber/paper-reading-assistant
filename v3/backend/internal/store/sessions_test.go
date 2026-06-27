// store 包 sessions/messages 的测试。
//
// 覆盖流式异常落库的基础：AppendMessage 事务原子性、计数同步、列表顺序。
package store

import (
	"testing"
)

// TestCreateAndGetSession 验证会话创建与查询。
func TestCreateAndGetSession(t *testing.T) {
	db := newSkillsTestDB(t)
	s := Session{ID: "s1", Title: "测试会话", SkillMode: "auto"}
	if err := CreateSession(db, s); err != nil {
		t.Fatalf("CreateSession 失败: %v", err)
	}
	got, err := GetSession(db, "s1")
	if err != nil {
		t.Fatalf("GetSession 失败: %v", err)
	}
	if got.Title != "测试会话" || got.SkillMode != "auto" {
		t.Fatalf("会话字段异常: %+v", got)
	}
	if got.EnabledSkillIDs != "[]" {
		t.Fatalf("缺省 enabled_skill_ids 应为 []，得到 %s", got.EnabledSkillIDs)
	}
}

// TestGetSessionNotFound 验证未找到返回明确错误。
func TestGetSessionNotFound(t *testing.T) {
	db := newSkillsTestDB(t)
	_, err := GetSession(db, "nope")
	if err != ErrSessionNotFound {
		t.Fatalf("期望 ErrSessionNotFound，得到 %v", err)
	}
}

// TestAppendMessageUpdatesSessionCount 验证追加消息事务原子性：计数与消息同步。
// 这是流式异常落库的基础——即便中途出错，已落库的消息与计数一致。
func TestAppendMessageUpdatesSessionCount(t *testing.T) {
	db := newSkillsTestDB(t)
	_ = CreateSession(db, Session{ID: "s1", Title: "t"})

	msgs := []Message{
		{ID: "m1", SessionID: "s1", Role: "user", Content: "你好", TokenCount: 10},
		{ID: "m2", SessionID: "s1", Role: "assistant", Content: "你好！", TokenCount: 20, ReasoningContent: "思考中..."},
		{ID: "m3", SessionID: "s1", Role: "assistant", Content: "", ToolCalls: `[{"id":"c1","type":"function","function":{"name":"list_topics","arguments":"{}"}}]`},
	}
	for _, m := range msgs {
		if err := AppendMessage(db, m); err != nil {
			t.Fatalf("AppendMessage 失败: %v", err)
		}
	}
	got, _ := GetSession(db, "s1")
	if got.MessageCount != 3 {
		t.Fatalf("message_count 期望 3，得到 %d", got.MessageCount)
	}
	if got.TotalTokens != 30 { // 10 + 20 + 0
		t.Fatalf("total_tokens 期望 30，得到 %d", got.TotalTokens)
	}
}

// TestListMessagesOrder 验证消息按插入顺序（rowid 升序）返回，保证对话顺序。
//
// 选 rowid 而非 created_at：created_at 仅秒级精度，同秒内多条消息会 tie；
// id 为 UUID 不可按插入序排序。rowid 由 SQLite 隐式自增，稳定反映插入顺序。
func TestListMessagesOrder(t *testing.T) {
	db := newSkillsTestDB(t)
	_ = CreateSession(db, Session{ID: "s1", Title: "t"})
	// 逆序插入（m2 先、m1 后），验证查询按 rowid 升序（即插入顺序）而非 id 字母序
	_ = AppendMessage(db, Message{ID: "m2", SessionID: "s1", Role: "assistant", Content: "second"})
	_ = AppendMessage(db, Message{ID: "m1", SessionID: "s1", Role: "user", Content: "first"})

	list, err := ListMessages(db, "s1")
	if err != nil {
		t.Fatalf("ListMessages 失败: %v", err)
	}
	if len(list) != 2 {
		t.Fatalf("期望 2 条消息，得到 %d", len(list))
	}
	// m2 先插入 → rowid 更小 → 排在前（按插入顺序，而非 id 字母序 m1 < m2）
	if list[0].ID != "m2" {
		t.Fatalf("顺序异常，期望 m2 在前（先插入），得到 %s", list[0].ID)
	}
	if list[1].ID != "m1" {
		t.Fatalf("顺序异常，期望 m1 在后（后插入），得到 %s", list[1].ID)
	}
}

// TestDeleteSessionCascade 验证删除会话同时清空其消息。
func TestDeleteSessionCascade(t *testing.T) {
	db := newSkillsTestDB(t)
	_ = CreateSession(db, Session{ID: "s1", Title: "t"})
	_ = AppendMessage(db, Message{ID: "m1", SessionID: "s1", Role: "user", Content: "x"})
	_ = AppendMessage(db, Message{ID: "m2", SessionID: "s1", Role: "assistant", Content: "y"})

	if err := DeleteSession(db, "s1"); err != nil {
		t.Fatalf("DeleteSession 失败: %v", err)
	}
	if _, err := GetSession(db, "s1"); err != ErrSessionNotFound {
		t.Fatalf("会话应已删除，得到 %v", err)
	}
	list, _ := ListMessages(db, "s1")
	if len(list) != 0 {
		t.Fatalf("会话消息应已清空，剩 %d 条", len(list))
	}
}

// TestUpdateSessionTitle 验证标题更新。
func TestUpdateSessionTitle(t *testing.T) {
	db := newSkillsTestDB(t)
	_ = CreateSession(db, Session{ID: "s1", Title: "旧标题"})
	if err := UpdateSessionTitle(db, "s1", "新标题"); err != nil {
		t.Fatalf("UpdateSessionTitle 失败: %v", err)
	}
	got, _ := GetSession(db, "s1")
	if got.Title != "新标题" {
		t.Fatalf("标题未更新: %s", got.Title)
	}
}

// TestListSessionsOrder 验证会话按 updated_at 降序（最新在前）。
func TestListSessionsOrder(t *testing.T) {
	db := newSkillsTestDB(t)
	_ = CreateSession(db, Session{ID: "s1", Title: "旧"})
	_ = CreateSession(db, Session{ID: "s2", Title: "新"})
	// 给 s1 追加消息使其 updated_at 更新 → 应排到前面
	_ = AppendMessage(db, Message{ID: "m1", SessionID: "s1", Role: "user", Content: "x"})

	list, err := ListSessions(db, 0)
	if err != nil {
		t.Fatalf("ListSessions 失败: %v", err)
	}
	if len(list) != 2 {
		t.Fatalf("期望 2 个会话，得到 %d", len(list))
	}
	if list[0].ID != "s1" {
		t.Fatalf("最近更新的 s1 应排前，得到 %s", list[0].ID)
	}
}
