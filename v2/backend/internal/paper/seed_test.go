// Package paper 的种子清单导入测试。
//
// 文件概述：seed_test.go 验证种子清单的加载与导入契约：
//   - LoadSeedPapers 能正确解析 JSON 种子文件；
//   - ImportSeedPapers 幂等（重复导入不产生重复行）；
//   - 重复导入不覆盖用户阅读进度（read_status）。
//
// 测试库由 openTestRepo（repository_test.go 共用）创建，schema 与生产一致。
package paper

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// TestSeedLoadSeedPapers 验证从临时 JSON 文件解析种子清单。
func TestSeedLoadSeedPapers(t *testing.T) {
	seed := SeedFile{
		Papers: []SeedPaper{
			{Title: "Paper A", ArxivID: "1111.1111", Level: "beginner", DifficultyScore: 2, Tags: []string{"x"}},
			{Title: "Paper B", DOI: "10.1000/b", Level: "advanced", DifficultyScore: 8, Tags: []string{"y"}},
		},
	}
	data, err := json.Marshal(seed)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "seed.json")
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
	got, err := LoadSeedPapers(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 {
		t.Fatalf("解析得到 %d 篇，期望 2", len(got))
	}
	if got[0].Title != "Paper A" || got[0].ArxivID != "1111.1111" {
		t.Errorf("第一篇解析错误: %+v", got[0])
	}
	if got[1].DOI != "10.1000/b" {
		t.Errorf("第二篇 DOI 错误: %+v", got[1])
	}
}

// TestSeedLoadSeedPapersMissingFile 验证文件不存在时返回错误。
func TestSeedLoadSeedPapersMissingFile(t *testing.T) {
	if _, err := LoadSeedPapers(filepath.Join(t.TempDir(), "nope.json")); err == nil {
		t.Fatal("文件不存在时应返回错误")
	}
}

// TestSeedImportSeedPapers 验证导入与幂等：重复导入不产生重复行，分类字段正确写入。
func TestSeedImportSeedPapers(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()
	papers := []SeedPaper{
		{Title: "Attention Is All You Need", ArxivID: "1706.03762", Level: "beginner", PaperType: "classic", SubDomain: "dl", DifficultyScore: 3, Tags: []string{"Transformer"}},
		{Title: "BERT", ArxivID: "1810.04805", Level: "intermediate", PaperType: "classic", SubDomain: "nlp", DifficultyScore: 5, Tags: []string{"NLP"}},
		{Title: "GloVe", DOI: "10.3115/v1/D14-1162", Level: "beginner", PaperType: "classic", SubDomain: "nlp", DifficultyScore: 3},
		{Title: "The Illustrated Transformer", Level: "beginner", PaperType: "popular", SubDomain: "dl", DifficultyScore: 1},
	}
	imported, skipped, failed, err := ImportSeedPapers(repo, papers)
	if err != nil {
		t.Fatal(err)
	}
	if imported != 4 || skipped != 0 || failed != 0 {
		t.Fatalf("首次导入: imported=%d skipped=%d failed=%d，期望 4/0/0", imported, skipped, failed)
	}
	n, _ := repo.CountPapers()
	if n != 4 {
		t.Fatalf("首次导入后论文数 %d，期望 4", n)
	}

	// 重复导入，验证幂等（不产生重复行）
	imported2, _, failed2, err := ImportSeedPapers(repo, papers)
	if err != nil {
		t.Fatal(err)
	}
	if failed2 != 0 {
		t.Errorf("重复导入不应有失败，实际 failed=%d", failed2)
	}
	if imported2 != 4 {
		t.Errorf("重复导入 imported=%d，期望 4（更新而非新增）", imported2)
	}
	n2, _ := repo.CountPapers()
	if n2 != 4 {
		t.Fatalf("重复导入后论文数 %d，期望仍为 4（幂等）", n2)
	}

	// 验证分类字段与 ai_classified 写入
	var level, paperType, subDomain, tags string
	var aiClassified, diff int
	row := repo.db.QueryRow(
		`SELECT COALESCE(level,''), COALESCE(paper_type,''), COALESCE(sub_domain,''),
		        COALESCE(tags,''), COALESCE(ai_classified,0), COALESCE(difficulty_score,0)
		 FROM papers WHERE id=?`, "arxiv_1706.03762")
	if err := row.Scan(&level, &paperType, &subDomain, &tags, &aiClassified, &diff); err != nil {
		t.Fatal(err)
	}
	if level != "beginner" || paperType != "classic" || subDomain != "dl" {
		t.Errorf("分类字段错误: level=%s type=%s sub=%s", level, paperType, subDomain)
	}
	if aiClassified != 0 {
		t.Errorf("ai_classified 应为 0（人工预设），实际 %d", aiClassified)
	}
	if diff != 3 {
		t.Errorf("difficulty_score 应为 3，实际 %d", diff)
	}
	if tags != `["Transformer"]` {
		t.Errorf("tags 写入错误: %q", tags)
	}

	// 验证无标识符论文用 seed_{slug} 稳定 id 落库（幂等关键）
	p, err := repo.GetPaper("seed_the_illustrated_transformer")
	if err != nil {
		t.Fatal(err)
	}
	if p == nil {
		t.Fatal("无标识符论文应用 seed_{slug} 作为稳定 id，未找到该行")
	}
}

// TestSeedImportSkipsEmptyTitle 验证空标题论文被跳过。
func TestSeedImportSkipsEmptyTitle(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()
	papers := []SeedPaper{
		{Title: "", ArxivID: "0000.0000", Level: "beginner"},
		{Title: "Valid Paper", ArxivID: "1111.2222", Level: "beginner"},
	}
	imported, skipped, failed, err := ImportSeedPapers(repo, papers)
	if err != nil {
		t.Fatal(err)
	}
	if imported != 1 || skipped != 1 || failed != 0 {
		t.Fatalf("imported=%d skipped=%d failed=%d，期望 1/1/0", imported, skipped, failed)
	}
}

// TestSeedImportPreservesReadStatus 验证重复导入不覆盖用户阅读进度。
func TestSeedImportPreservesReadStatus(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()
	papers := []SeedPaper{
		{Title: "ResNet", ArxivID: "1512.03385", Level: "intermediate", DifficultyScore: 4},
	}
	if _, _, _, err := ImportSeedPapers(repo, papers); err != nil {
		t.Fatal(err)
	}
	// 用户标记已读
	if err := repo.UpdateReadStatus("arxiv_1512.03385", "done"); err != nil {
		t.Fatal(err)
	}
	// 重复导入，不应覆盖 read_status
	if _, _, _, err := ImportSeedPapers(repo, papers); err != nil {
		t.Fatal(err)
	}
	p, err := repo.GetPaper("arxiv_1512.03385")
	if err != nil {
		t.Fatal(err)
	}
	if p.ReadStatus != "done" {
		t.Errorf("重复导入不应覆盖 read_status，实际 %q", p.ReadStatus)
	}
}
