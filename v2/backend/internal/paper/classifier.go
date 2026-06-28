// Package paper 的 AI 难度分类器。
//
// 文件概述：classifier.go 调用 LLM 从"零基础读者"视角评估论文阅读难度，
// 输出 level/paper_type/sub_domain/difficulty_score/tags/reason，并落库。
//
// 设计要点：
//   - Classify 是纯 LLM 调用 + JSON 解析，不碰数据库，便于单独测试解析逻辑；
//   - ClassifyPaper 处理单篇：已分类（ai_classified=1，含 AI 分类与人工预设种子）的论文跳过；
//   - ClassifyBatch 批量处理 ai_classified=0 且 level='' 的论文，逐条调用避免限流；
//   - LLM 输出可能包裹在 markdown code block 或带前后解释文字，extractJSON 鲁棒提取。
package paper

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"strings"

	"nuclear-ox-v2/backend/internal/llm"
)

// ClassificationResult 是 AI 分类输出。
type ClassificationResult struct {
	Level           string   `json:"level"`            // beginner/intermediate/advanced
	PaperType       string   `json:"paper_type"`       // survey/tutorial/popular/classic/...
	SubDomain       string   `json:"sub_domain"`       // ml/dl/llm/...
	DifficultyScore int      `json:"difficulty_score"`  // 1-10
	Tags            []string `json:"tags"`
	Reason          string   `json:"reason"`
}

// 允许的枚举值。LLM 返回不在范围内的值时回退到安全默认，保证分类总能落库。
var (
	allowedLevels = map[string]bool{
		"beginner": true, "intermediate": true, "advanced": true,
	}
	allowedPaperTypes = map[string]bool{
		"survey": true, "tutorial": true, "popular": true, "classic": true,
		"applied": true, "engineering": true, "sota": true,
		"theoretical": true, "frontier": true,
	}
	allowedSubDomains = map[string]bool{
		"ml": true, "dl": true, "llm": true, "context_engineering": true,
		"llm_security": true, "rl": true, "reasoning": true,
		"ai_infra": true, "distributed": true, "cv": true, "nlp": true,
	}
)

// AIClassifier 用 LLM 对论文进行难度分类。
type AIClassifier struct {
	llmClient *llm.Client
}

// NewAIClassifier 构造分类器。
func NewAIClassifier(llmClient *llm.Client) *AIClassifier {
	return &AIClassifier{llmClient: llmClient}
}

// classifyPrompt 构造以零基础读者视角评估难度的 prompt。
func classifyPrompt(title, abstract string) string {
	return fmt.Sprintf(`你是 AI 论文难度评估专家，服务对象是一位刚开始学习 AI 的零基础读者
（懂中文，会写简单代码，但不了解机器学习/深度学习/数学基础）。

请从这位读者的视角评估以下论文的阅读难度，返回 JSON：
{
  "level": "beginner|intermediate|advanced",
  "paper_type": "survey|tutorial|popular|classic|applied|engineering|sota|theoretical|frontier",
  "sub_domain": "ml|dl|llm|context_engineering|llm_security|rl|reasoning|ai_infra|distributed|cv|nlp",
  "difficulty_score": 1-10,
  "tags": ["关键标签1", "关键标签2"],
  "reason": "一句话解释为什么给这个难度（从零基础读者角度）"
}

评分标准：
- 1-3 分：这位零基础读者能直接读懂，或只需补少量前置知识
- 4-6 分：需要先学完入门级 ML/DL 课程才能读懂
- 7-10 分：需要扎实的数学/领域专业知识，对零基础读者暂不建议

标题：%s
摘要：%s`, title, abstract)
}

// Classify 调用 LLM 对单篇论文（标题+摘要）分类。
// 不访问数据库，便于直接测试解析与校验逻辑。
func (c *AIClassifier) Classify(ctx context.Context, title, abstract string) (*ClassificationResult, error) {
	prompt := classifyPrompt(title, abstract)
	messages := []llm.Message{
		{Role: llm.RoleUser, Content: prompt},
	}
	resp, err := c.llmClient.Chat(ctx, messages)
	if err != nil {
		return nil, fmt.Errorf("LLM 调用失败: %w", err)
	}
	if resp == nil || len(resp.Choices) == 0 {
		return nil, fmt.Errorf("LLM 返回空 choices")
	}
	content := resp.Choices[0].Message.Content
	return parseClassificationResult(content)
}

// parseClassificationResult 从 LLM 文本输出中提取 JSON 并解析、校验。
// LLM 可能在 JSON 前后附加解释文字，或用 markdown code block 包裹，均需兼容。
func parseClassificationResult(content string) (*ClassificationResult, error) {
	jsonStr := extractJSON(content)
	if jsonStr == "" {
		return nil, fmt.Errorf("未能从 LLM 输出提取 JSON: %s", truncate(content, 200))
	}
	var result ClassificationResult
	if err := json.Unmarshal([]byte(jsonStr), &result); err != nil {
		return nil, fmt.Errorf("解析分类 JSON 失败: %w", err)
	}
	// 校验枚举值：非法值回退安全默认，保证下游总能用
	if !allowedLevels[result.Level] {
		result.Level = "intermediate"
	}
	if !allowedPaperTypes[result.PaperType] {
		result.PaperType = "theoretical"
	}
	if !allowedSubDomains[result.SubDomain] {
		result.SubDomain = "ml"
	}
	// difficulty_score 钳制到 1-10
	if result.DifficultyScore < 1 {
		result.DifficultyScore = 1
	}
	if result.DifficultyScore > 10 {
		result.DifficultyScore = 10
	}
	return &result, nil
}

// extractJSON 从可能含 markdown code block 或前后说明文字的内容中提取 JSON 对象。
// 优先识别 ```json / ``` 代码块；否则回退到首个 { 到末个 } 的子串。
func extractJSON(content string) string {
	// 1. 尝试 markdown code block
	if idx := strings.Index(content, "```"); idx >= 0 {
		rest := content[idx+3:]
		// 跳过可选的语言标识（如 json），取到下一个换行
		if nl := strings.Index(rest, "\n"); nl >= 0 {
			rest = rest[nl+1:]
		}
		if end := strings.Index(rest, "```"); end >= 0 {
			return strings.TrimSpace(rest[:end])
		}
	}
	// 2. 回退：首个 { 到末个 }
	first := strings.Index(content, "{")
	last := strings.LastIndex(content, "}")
	if first >= 0 && last > first {
		return content[first : last+1]
	}
	return ""
}

// truncate 截断字符串到 max 字符，便于错误信息展示。
func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}

// --- Repository 辅助方法（分类流程专用，定义在本文件以集中分类相关逻辑）---

// classificationRow 承载分类流程需要的论文字段。
type classificationRow struct {
	ID           string
	Title        string
	Abstract     string
	AIClassified int
	Level        string
	PaperType    string
}

// getPaperForClassification 读取单篇论文供分类用：title/abstract/ai_classified/level/paper_type。
func (r *Repository) getPaperForClassification(paperID string) (*classificationRow, error) {
	var row classificationRow
	err := r.db.QueryRow(
		`SELECT id, COALESCE(title,''), COALESCE(abstract,''),
		        COALESCE(ai_classified,0), COALESCE(level,''), COALESCE(paper_type,'')
		 FROM papers WHERE id=?`, paperID,
	).Scan(&row.ID, &row.Title, &row.Abstract, &row.AIClassified, &row.Level, &row.PaperType)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("getPaperForClassification(%s) 失败: %w", paperID, err)
	}
	return &row, nil
}

// listPapersForBatchClassification 返回所有待分类论文：ai_classified=0 且 level 为空。
func (r *Repository) listPapersForBatchClassification() ([]classificationRow, error) {
	rows, err := r.db.Query(
		`SELECT id, COALESCE(title,''), COALESCE(abstract,''),
		        COALESCE(ai_classified,0), COALESCE(level,'')
		 FROM papers WHERE ai_classified=0 AND (level IS NULL OR level='')`)
	if err != nil {
		return nil, fmt.Errorf("listPapersForBatchClassification 查询失败: %w", err)
	}
	defer rows.Close()
	var result []classificationRow
	for rows.Next() {
		var row classificationRow
		if err := rows.Scan(&row.ID, &row.Title, &row.Abstract, &row.AIClassified, &row.Level); err != nil {
			return nil, fmt.Errorf("listPapersForBatchClassification 扫描失败: %w", err)
		}
		result = append(result, row)
	}
	return result, rows.Err()
}

// UpdateAIClassification 写入 AI 分类结果并把 ai_classified 置 1。
// 不触碰 read_status/obsidian_path 等用户字段。
func (r *Repository) UpdateAIClassification(paperID string, result ClassificationResult) error {
	tagsJSON := tagsToJSON(result.Tags)
	_, err := r.db.Exec(
		`UPDATE papers SET level=?, paper_type=?, sub_domain=?,
		        difficulty_score=?, tags=?, ai_classified=1
		 WHERE id=?`,
		result.Level, result.PaperType, result.SubDomain,
		result.DifficultyScore, tagsJSON, paperID,
	)
	if err != nil {
		return fmt.Errorf("UpdateAIClassification(%s) 失败: %w", paperID, err)
	}
	return nil
}

// classifyAndUpdate 是 ClassifyPaper 与 ClassifyBatch 共享的内部流程：
// 调用 Classify 得到结果并落库。
func (c *AIClassifier) classifyAndUpdate(ctx context.Context, repo *Repository,
	paperID, title, abstract string) error {
	result, err := c.Classify(ctx, title, abstract)
	if err != nil {
		return err
	}
	return repo.UpdateAIClassification(paperID, *result)
}

// ClassifyPaper 对单篇论文分类。
// 已分类（ai_classified=1，含 AI 分类与人工预设种子）的论文跳过，避免重复分类与覆盖。
// 待分类（ai_classified=0，来自数据源同步）的论文才会调用 LLM 分类。
func (c *AIClassifier) ClassifyPaper(ctx context.Context, repo *Repository, paperID string) error {
	row, err := repo.getPaperForClassification(paperID)
	if err != nil {
		return err
	}
	if row == nil {
		return fmt.Errorf("论文 %s 不存在", paperID)
	}
	if row.AIClassified == 1 {
		// 已分类（AI 或人工预设），跳过
		return nil
	}
	return c.classifyAndUpdate(ctx, repo, paperID, row.Title, row.Abstract)
}

// ClassifyBatch 批量分类所有 ai_classified=0 且 level='' 的论文。
// 逐条调用避免并发触发 LLM 限流；单篇失败仅记日志，不中断整体。
// 返回成功分类的数量。
func (c *AIClassifier) ClassifyBatch(ctx context.Context, repo *Repository) (int, error) {
	rows, err := repo.listPapersForBatchClassification()
	if err != nil {
		return 0, err
	}
	count := 0
	for _, row := range rows {
		if err := c.classifyAndUpdate(ctx, repo, row.ID, row.Title, row.Abstract); err != nil {
			log.Printf("[分类] 论文 %s 分类失败: %v", row.ID, err)
			continue
		}
		count++
	}
	return count, nil
}
