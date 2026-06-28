// Package paper 的种子清单导入功能。
//
// 文件概述：seed.go 提供"人工精选论文清单"的加载与导入能力。
// 种子清单（seed_papers.json）是一份手工策划的论文集合，按难度分级，
// 用于在新库初始化时快速填充高质量论文，避免空库启动体验。
//
// 设计要点：
//   - 种子论文使用稳定 id（arxiv_id > doi > seed_{slug}），保证重复导入幂等；
//   - 导入时 ai_classified=0（标记为人工预设），AI 分类流程据此不覆盖其 tags；
//   - 重复导入不覆盖用户的 read_status/obsidian_path/阅读时长；
//   - level/paper_type/sub_domain/difficulty_score 由种子清单直接指定，不依赖 AI。
package paper

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
)

// SeedPaper 是种子清单中的一篇论文。
type SeedPaper struct {
	Title           string   `json:"title"`
	ArxivID         string   `json:"arxiv_id"`
	DOI             string   `json:"doi"`
	Level           string   `json:"level"`
	PaperType       string   `json:"paper_type"`
	SubDomain       string   `json:"sub_domain"`
	DifficultyScore int      `json:"difficulty_score"`
	Tags            []string `json:"tags"`
	Company         string   `json:"company"`
	Reason          string   `json:"reason"`
}

// SeedFile 是种子清单文件格式。
type SeedFile struct {
	Papers []SeedPaper `json:"papers"`
}

// LoadSeedPapers 读取并解析种子清单 JSON 文件。
func LoadSeedPapers(path string) ([]SeedPaper, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("读取种子清单 %s 失败: %w", path, err)
	}
	var f SeedFile
	if err := json.Unmarshal(data, &f); err != nil {
		return nil, fmt.Errorf("解析种子清单 %s 失败: %w", path, err)
	}
	return f.Papers, nil
}

// SeedPaperToMeta 将种子论文转换为数据源元数据 PaperMeta。
// level/paper_type/sub_domain/difficulty_score 不在 PaperMeta 中（由导入流程单独写入），
// 此处仅填充基本元数据字段；reason 仅用于人工说明，不入库。
func SeedPaperToMeta(seed SeedPaper) PaperMeta {
	return PaperMeta{
		Title:   seed.Title,
		ArxivID: seed.ArxivID,
		DOI:     seed.DOI,
		Company: seed.Company,
		Tags:    seed.Tags,
		Source:  "seed",
	}
}

// seedPaperID 按优先级生成稳定 id：arxiv_id > doi > seed_{slug}。
// 前两级与 paperMetaID 一致；第三级用基于标题的 slug 兜底，
// 保证无标识符的种子论文也可幂等导入（不依赖随机 uuid）。
func seedPaperID(seed SeedPaper) string {
	if seed.ArxivID != "" {
		return "arxiv_" + seed.ArxivID
	}
	if seed.DOI != "" {
		return "doi_" + seed.DOI
	}
	return "seed_" + Slugify(seed.Title)
}

// ImportSeedPapers 将种子论文批量导入数据库。
// 返回 imported（成功写入数）、skipped（因缺标题等跳过）、failed（写入失败）。
//
// 行为保证：
//   - 幂等：基于稳定 id 用 INSERT ... ON CONFLICT，重复导入不产生重复行；
//   - 不覆盖阅读进度：冲突时保留 read_status/obsidian_path/last_read_at/total_read_seconds；
//   - 人工预设标记：ai_classified=0，AI 分类流程据此不覆盖 tags。
//
// 实现说明：未直接调用 UpsertPaperMeta，因其对无 arxiv_id/doi 的论文回退到随机 uuid，
// 会破坏种子清单的幂等导入。此处用一条 upsert 同时写入基本元数据与分类字段，
// 功能上是"UpsertPaperMeta 写基本元数据 + UPDATE 设分类字段"的等价合并。
func ImportSeedPapers(repo *Repository, papers []SeedPaper) (imported, skipped, failed int, err error) {
	for _, seed := range papers {
		if seed.Title == "" {
			skipped++
			log.Printf("[seed] [WARN] 跳过无标题论文")
			continue
		}
		meta := SeedPaperToMeta(seed)
		id := seedPaperID(seed)
		tagsJSON := tagsToJSON(meta.Tags)
		_, e := repo.db.Exec(
			`INSERT INTO papers(id, title, authors, year, abstract, pdf_url, doi, arxiv_id,
			    source, venue, company, github_repo, tags, level, paper_type, sub_domain,
			    difficulty_score, ai_classified, read_status)
			 VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'unread')
			 ON CONFLICT(id) DO UPDATE SET
			    title=excluded.title, authors=excluded.authors, year=excluded.year,
			    abstract=excluded.abstract, pdf_url=excluded.pdf_url, doi=excluded.doi,
			    arxiv_id=excluded.arxiv_id, source=excluded.source, venue=excluded.venue,
			    company=excluded.company, github_repo=excluded.github_repo, tags=excluded.tags,
			    level=excluded.level, paper_type=excluded.paper_type, sub_domain=excluded.sub_domain,
			    difficulty_score=excluded.difficulty_score, ai_classified=0`,
			id, meta.Title, meta.Authors, meta.Year, meta.Abstract, meta.PDFURL, meta.DOI,
			meta.ArxivID, meta.Source, meta.Venue, meta.Company, meta.GitHubRepo, tagsJSON,
			seed.Level, seed.PaperType, seed.SubDomain, seed.DifficultyScore,
		)
		if e != nil {
			failed++
			log.Printf("[seed] [WARN] 导入失败 %s: %v", seed.Title, e)
			continue
		}
		imported++
	}
	log.Printf("[seed] [INFO] 导入完成: imported=%d skipped=%d failed=%d", imported, skipped, failed)
	return imported, skipped, failed, nil
}
