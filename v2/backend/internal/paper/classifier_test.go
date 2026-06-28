// Package paper 的 AI 分类器测试。
//
// 文件概述：classifier_test.go 验证：
//   - LLM 输出为纯 JSON 时的提取与解析；
//   - LLM 输出包裹在 markdown code block（```json ... ```）时的提取；
//   - LLM 输出带前后解释文字时的提取；
//   - difficulty_score 越界时钳制到 1-10；
//   - 枚举值非法时回退安全默认；
//   - ClassifyPaper 跳过 ai_classified=0 的人工预设论文；
//   - ClassifyPaper 对可分类论文的端到端落库；
//   - ClassifyBatch 批量分类与幂等。
//
// LLM 调用通过 httptest mock server 注入（与 llm/client_test.go 一致的模式），
// 解析逻辑直接对纯函数 parseClassificationResult 喂入 mock 响应内容。
package paper

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"nuclear-ox-v2/backend/internal/llm"
)

// mockChatResp 构造一个合法的 OpenAI 风格 chat completions 响应体，content 为助手回复。
func mockChatResp(content string) string {
	b, _ := json.Marshal(map[string]any{
		"id":     "resp-1",
		"model":  "deepseek-chat",
		"choices": []map[string]any{
			{
				"index":         0,
				"message":       map[string]any{"role": "assistant", "content": content},
				"finish_reason": "stop",
			},
		},
		"usage": map[string]any{
			"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8,
		},
	})
	return string(b)
}

// newMockLLMClient 启动一个返回固定 content 的 mock LLM server，并构造指向它的 Client。
// hitCount 记录被调用次数，便于断言"是否被调用"。
func newMockLLMClient(t *testing.T, content string) (*llm.Client, *int, *httptest.Server) {
	t.Helper()
	hits := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, mockChatResp(content))
	}))
	t.Cleanup(srv.Close)
	c := llm.New("deepseek", "deepseek-chat", srv.URL, "k", 10)
	return c, &hits, srv
}

// TestParseClassificationResult_PureJSON 验证纯 JSON 输出的提取与解析。
func TestParseClassificationResult_PureJSON(t *testing.T) {
	content := `{"level":"beginner","paper_type":"survey","sub_domain":"llm","difficulty_score":3,"tags":["LLM","综述"],"reason":"综述适合入门"}`
	r, err := parseClassificationResult(content)
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if r.Level != "beginner" {
		t.Errorf("Level: got %q want beginner", r.Level)
	}
	if r.PaperType != "survey" {
		t.Errorf("PaperType: got %q want survey", r.PaperType)
	}
	if r.SubDomain != "llm" {
		t.Errorf("SubDomain: got %q want llm", r.SubDomain)
	}
	if r.DifficultyScore != 3 {
		t.Errorf("DifficultyScore: got %d want 3", r.DifficultyScore)
	}
	if len(r.Tags) != 2 || r.Tags[0] != "LLM" {
		t.Errorf("Tags: got %+v", r.Tags)
	}
}

// TestParseClassificationResult_MarkdownCodeBlock 验证 ```json 包裹的输出提取。
func TestParseClassificationResult_MarkdownCodeBlock(t *testing.T) {
	content := "好的，以下是评估结果：\n```json\n" +
		`{"level":"advanced","paper_type":"sota","sub_domain":"llm","difficulty_score":9,"tags":["DeepSeek"],"reason":"前沿研究"}` +
		"\n```\n希望对你有帮助。"
	r, err := parseClassificationResult(content)
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if r.Level != "advanced" {
		t.Errorf("Level: got %q want advanced", r.Level)
	}
	if r.PaperType != "sota" {
		t.Errorf("PaperType: got %q want sota", r.PaperType)
	}
	if r.DifficultyScore != 9 {
		t.Errorf("DifficultyScore: got %d want 9", r.DifficultyScore)
	}
	if r.Tags[0] != "DeepSeek" {
		t.Errorf("Tags[0]: got %q want DeepSeek", r.Tags[0])
	}
}

// TestParseClassificationResult_PlainCodeBlock 验证无语言标识的 ``` 代码块。
func TestParseClassificationResult_PlainCodeBlock(t *testing.T) {
	content := "```\n" +
		`{"level":"intermediate","paper_type":"classic","sub_domain":"nlp","difficulty_score":5,"tags":["BERT"],"reason":"经典论文"}` +
		"\n```"
	r, err := parseClassificationResult(content)
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if r.Level != "intermediate" {
		t.Errorf("Level: got %q want intermediate", r.Level)
	}
}

// TestParseClassificationResult_ClampHigh 验证 difficulty_score 超上限钳制到 10。
func TestParseClassificationResult_ClampHigh(t *testing.T) {
	content := `{"level":"advanced","paper_type":"frontier","sub_domain":"llm","difficulty_score":15,"tags":[],"reason":""}`
	r, err := parseClassificationResult(content)
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if r.DifficultyScore != 10 {
		t.Errorf("difficulty_score 15 应钳制到 10，实际 %d", r.DifficultyScore)
	}
}

// TestParseClassificationResult_ClampLow 验证 difficulty_score 低于下限钳制到 1。
func TestParseClassificationResult_ClampLow(t *testing.T) {
	content := `{"level":"beginner","paper_type":"tutorial","sub_domain":"ml","difficulty_score":-3,"tags":[],"reason":""}`
	r, err := parseClassificationResult(content)
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if r.DifficultyScore != 1 {
		t.Errorf("difficulty_score -3 应钳制到 1，实际 %d", r.DifficultyScore)
	}
}

// TestParseClassificationResult_InvalidEnums 验证非法枚举值回退安全默认。
func TestParseClassificationResult_InvalidEnums(t *testing.T) {
	content := `{"level":"weird","paper_type":"foo","sub_domain":"bar","difficulty_score":5,"tags":[],"reason":""}`
	r, err := parseClassificationResult(content)
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if r.Level != "intermediate" {
		t.Errorf("非法 level 应回退 intermediate，实际 %q", r.Level)
	}
	if r.PaperType != "theoretical" {
		t.Errorf("非法 paper_type 应回退 theoretical，实际 %q", r.PaperType)
	}
	if r.SubDomain != "ml" {
		t.Errorf("非法 sub_domain 应回退 ml，实际 %q", r.SubDomain)
	}
}

// TestParseClassificationResult_NoJSON 验证无 JSON 时返回错误。
func TestParseClassificationResult_NoJSON(t *testing.T) {
	_, err := parseClassificationResult("这段话里没有任何 JSON 对象")
	if err == nil {
		t.Error("无 JSON 内容应返回错误")
	}
}

// TestClassifyPaper_SkipAIClassified0 验证 ai_classified=0 的人工预设论文被跳过：
// LLM 不应被调用，数据库分类字段不应被改动。
func TestClassifyPaper_SkipAIClassified0(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	// 写入一篇论文（UpsertPaperMeta 默认 ai_classified=1），再改为 0 并预设 level
	if err := repo.UpsertPaperMeta(PaperMeta{
		Title: "Seed Paper", ArxivID: "9999.00001", Source: "seed",
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.db.Exec(
		`UPDATE papers SET ai_classified=0, level='beginner', paper_type='survey' WHERE id='arxiv_9999.00001'`); err != nil {
		t.Fatal(err)
	}

	c, hits, _ := newMockLLMClient(t, `{"level":"advanced","paper_type":"sota","sub_domain":"llm","difficulty_score":9,"tags":[],"reason":""}`)
	clf := NewAIClassifier(c)

	if err := clf.ClassifyPaper(context.Background(), repo, "arxiv_9999.00001"); err != nil {
		t.Fatalf("ClassifyPaper 失败: %v", err)
	}
	if *hits != 0 {
		t.Errorf("ai_classified=0 应跳过，LLM 不应被调用，实际调用 %d 次", *hits)
	}
	// 验证人工预设的分类未被覆盖
	row, err := repo.getPaperForClassification("arxiv_9999.00001")
	if err != nil {
		t.Fatal(err)
	}
	if row.Level != "beginner" {
		t.Errorf("人工 level 不应被覆盖: got %q want beginner", row.Level)
	}
	if row.AIClassified != 0 {
		t.Errorf("ai_classified 不应变: got %d want 0", row.AIClassified)
	}
}

// TestClassifyPaper_Persist 验证对可分类论文（ai_classified=1）的端到端落库：
// LLM 被调用一次，分类字段被写入，ai_classified 置 1。
func TestClassifyPaper_Persist(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	if err := repo.UpsertPaperMeta(PaperMeta{
		Title: "BERT", ArxivID: "1810.04805", Source: "arxiv",
		Abstract: "We introduce a new language representation model",
	}); err != nil {
		t.Fatal(err)
	}
	// UpsertPaperMeta 设 ai_classified=1，不会被 ClassifyPaper 跳过

	resp := `{"level":"intermediate","paper_type":"classic","sub_domain":"nlp","difficulty_score":4,"tags":["BERT","NLP"],"reason":"需先学Transformer"}`
	c, hits, _ := newMockLLMClient(t, resp)
	clf := NewAIClassifier(c)

	if err := clf.ClassifyPaper(context.Background(), repo, "arxiv_1810.04805"); err != nil {
		t.Fatalf("ClassifyPaper 失败: %v", err)
	}
	if *hits != 1 {
		t.Errorf("LLM 应被调用 1 次，实际 %d", *hits)
	}
	row, err := repo.getPaperForClassification("arxiv_1810.04805")
	if err != nil {
		t.Fatal(err)
	}
	if row.Level != "intermediate" {
		t.Errorf("Level: got %q want intermediate", row.Level)
	}
	if row.PaperType != "classic" {
		t.Errorf("PaperType: got %q want classic", row.PaperType)
	}
	if row.AIClassified != 1 {
		t.Errorf("ai_classified: got %d want 1", row.AIClassified)
	}
}

// TestClassifyBatch 验证批量分类：ai_classified=0 且 level='' 的论文被分类并置 1。
func TestClassifyBatch(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	// 两篇待分类论文：ai_classified=0 且 level=''
	for _, id := range []string{"1111.00001", "1111.00002"} {
		if err := repo.UpsertPaperMeta(PaperMeta{
			Title: "P-" + id, ArxivID: id, Source: "arxiv",
		}); err != nil {
			t.Fatal(err)
		}
		// UpsertPaperMeta 设 ai_classified=1，改回 0 以模拟未分类（level 保持空）
		if _, err := repo.db.Exec(
			`UPDATE papers SET ai_classified=0 WHERE id=?`, "arxiv_"+id); err != nil {
			t.Fatal(err)
		}
	}
	// 一篇种子论文：ai_classified=0 但 level 已设 → 不应被批次处理
	if err := repo.UpsertPaperMeta(PaperMeta{Title: "Seed", ArxivID: "1111.00003", Source: "seed"}); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.db.Exec(
		`UPDATE papers SET ai_classified=0, level='beginner' WHERE id='arxiv_1111.00003'`); err != nil {
		t.Fatal(err)
	}

	resp := `{"level":"intermediate","paper_type":"classic","sub_domain":"ml","difficulty_score":5,"tags":[],"reason":""}`
	c, hits, _ := newMockLLMClient(t, resp)
	clf := NewAIClassifier(c)

	n, err := clf.ClassifyBatch(context.Background(), repo)
	if err != nil {
		t.Fatalf("ClassifyBatch 失败: %v", err)
	}
	if n != 2 {
		t.Errorf("应分类 2 篇，实际 %d", n)
	}
	if *hits != 2 {
		t.Errorf("LLM 应被调用 2 次，实际 %d", *hits)
	}
	// 种子论文未被处理：level 仍为 beginner，ai_classified 仍为 0
	seed, _ := repo.getPaperForClassification("arxiv_1111.00003")
	if seed.Level != "beginner" {
		t.Errorf("种子论文 level 不应变: got %q want beginner", seed.Level)
	}
	// 已分类论文 ai_classified=1
	for _, id := range []string{"arxiv_1111.00001", "arxiv_1111.00002"} {
		row, _ := repo.getPaperForClassification(id)
		if row.AIClassified != 1 {
			t.Errorf("%s ai_classified 应为 1，实际 %d", id, row.AIClassified)
		}
	}
}

// TestClassifyBatch_Idempotent 验证再次批次分类不再处理已分类论文。
func TestClassifyBatch_Idempotent(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	if err := repo.UpsertPaperMeta(PaperMeta{Title: "P", ArxivID: "2222.00001", Source: "arxiv"}); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.db.Exec(
		`UPDATE papers SET ai_classified=0 WHERE id='arxiv_2222.00001'`); err != nil {
		t.Fatal(err)
	}

	resp := `{"level":"intermediate","paper_type":"classic","sub_domain":"ml","difficulty_score":5,"tags":[],"reason":""}`
	c, hits, _ := newMockLLMClient(t, resp)
	clf := NewAIClassifier(c)

	n1, _ := clf.ClassifyBatch(context.Background(), repo)
	if n1 != 1 {
		t.Fatalf("首次应分类 1 篇，实际 %d", n1)
	}
	// 再次运行：该论文已 ai_classified=1，不再被查询命中
	n2, _ := clf.ClassifyBatch(context.Background(), repo)
	if n2 != 0 {
		t.Errorf("二次应分类 0 篇（幂等），实际 %d", n2)
	}
	if *hits != 1 {
		t.Errorf("LLM 应仅被调用 1 次（首次），实际 %d", *hits)
	}
}
