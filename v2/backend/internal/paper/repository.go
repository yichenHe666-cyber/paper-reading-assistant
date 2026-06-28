// Package paper 提供论文与主题的持久化与同步能力。
//
// 文件概述：repository.go 定义 Topic/Paper 数据模型与基于 SQLite 的 CRUD 操作。
// 这是痛点②（"重启后论文读取为 0"）业务层修复的承载点：
//   - 存储层（store.go）已保证数据库路径绝对化，不再随 cwd 漂移；
//   - 本层保证同步写入的数据用 Upsert（INSERT OR REPLACE）幂等落库，
//     重启后 ListTopics/ListPapers 直接从稳定路径库读取，必然返回既有数据。
//
// 设计要点：
//   - 所有写操作用 INSERT OR REPLACE（按主键幂等），重复同步不报错、不重复；
//   - 所有读操作不依赖任何缓存层，直接查库——重启即读库，所见即所得；
//   - id 由 topic 目录名 + 论文文件名 slug 化派生，跨同步稳定，保证 Upsert 命中同一行。
package paper

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

// Topic 表示一个论文主题分类（对应 Papers We Love 仓库顶层目录）。
type Topic struct {
	ID         string `json:"id"`          // 稳定 id（目录名 slug 化）
	Name       string `json:"name"`        // 原始目录名
	NameCN     string `json:"name_cn"`     // 中文名称（可空）
	PaperCount int    `json:"paper_count"` // 该主题下论文数（同步后更新）
	CreatedAt  string `json:"created_at"`  // 创建时间
}

// Paper 表示一篇论文的元数据。
// JSON tag 必须为 snake_case，与前端 types.ts 对齐——gin 默认用字段名（PascalCase）
// 序列化，会导致前端读不到字段，故全部显式标注。
type Paper struct {
	ID                string `json:"id"`                  // 稳定 id（topic_id/slug 派生）
	Title             string `json:"title"`               // 标题
	Authors           string `json:"authors"`             // 作者（逗号分隔）
	Year              int    `json:"year"`                // 发表年份（0 表示未知）
	TopicID           string `json:"topic_id"`            // 所属主题 id
	PDFURL            string `json:"pdf_url"`             // PDF 下载地址
	DOI               string `json:"doi"`                 // DOI
	Abstract          string `json:"abstract"`            // 摘要
	ReadStatus        string `json:"read_status"`         // 阅读状态：unread/reading/done/reread
	ObsidianPath      string `json:"obsidian_path"`       // Obsidian 笔记路径
	CreatedAt         string `json:"created_at"`          // 创建时间
	Source            string `json:"source"`              // 数据源：arxiv/openalex/acl/company
	Venue             string `json:"venue"`               // 发表会议/期刊
	Level             string `json:"level"`               // AI 分类难度：beginner/intermediate/advanced
	PaperType         string `json:"paper_type"`          // 论文类型：survey/tutorial/classic/...
	SubDomain         string `json:"sub_domain"`          // 子领域：ml/dl/llm/...
	DifficultyScore   int    `json:"difficulty_score"`    // 难度评分 1-10
	Tags              string `json:"tags"`                // 标签 JSON 数组字符串
	AIClassified      int    `json:"ai_classified"`       // 是否已 AI 分类：0=人工预设/未分类，1=已分类
	Company           string `json:"company"`             // 公司名（company 源用）
	GitHubRepo        string `json:"github_repo"`         // GitHub 仓库全名（company 源用）
	ArxivID           string `json:"arxiv_id"`            // arXiv ID
	LastReadAt        string `json:"last_read_at"`        // 上次阅读时间
	TotalReadSeconds  int    `json:"total_read_seconds"`  // 累计阅读时长（秒）
}

// Repository 是论文/主题的数据访问层。持有已打开的 *sql.DB（由 store.Open 提供）。
// 所有方法并发安全（SQLite 单写多读 + WAL，配合 store.Open 的 SetMaxOpenConns(1)）。
type Repository struct {
	db *sql.DB
}

// NewRepository 构造一个基于已打开数据库的 Repository。
func NewRepository(db *sql.DB) *Repository {
	return &Repository{db: db}
}

// UpsertTopic 插入或更新一个主题（按主键 id 幂等）。
// 重复同步同一仓库时，已存在的主题会被覆盖 name/name_cn，不会产生重复行。
func (r *Repository) UpsertTopic(t Topic) error {
	_, err := r.db.Exec(
		`INSERT INTO topics(id, name, name_cn, paper_count)
		 VALUES(?, ?, ?, ?)
		 ON CONFLICT(id) DO UPDATE SET name=excluded.name, name_cn=excluded.name_cn`,
		t.ID, t.Name, t.NameCN, t.PaperCount,
	)
	if err != nil {
		return fmt.Errorf("UpsertTopic(%s) 失败: %w", t.ID, err)
	}
	return nil
}

// ListTopics 返回全部主题，按 name 排序。
// 重启后调用此方法直接读库——只要库路径稳定（config 层保证），必然返回既有数据。
func (r *Repository) ListTopics() ([]Topic, error) {
	rows, err := r.db.Query(
		`SELECT id, name, COALESCE(name_cn,''), paper_count, COALESCE(created_at,'')
		 FROM topics ORDER BY name`)
	if err != nil {
		return nil, fmt.Errorf("ListTopics 查询失败: %w", err)
	}
	defer rows.Close()

	var topics []Topic
	for rows.Next() {
		var t Topic
		if err := rows.Scan(&t.ID, &t.Name, &t.NameCN, &t.PaperCount, &t.CreatedAt); err != nil {
			return nil, fmt.Errorf("ListTopics 扫描失败: %w", err)
		}
		topics = append(topics, t)
	}
	return topics, rows.Err()
}

// GetTopic 按 id 查询单个主题。
func (r *Repository) GetTopic(id string) (*Topic, error) {
	var t Topic
	err := r.db.QueryRow(
		`SELECT id, name, COALESCE(name_cn,''), paper_count, COALESCE(created_at,'')
		 FROM topics WHERE id=?`, id,
	).Scan(&t.ID, &t.Name, &t.NameCN, &t.PaperCount, &t.CreatedAt)
	if err == sql.ErrNoRows {
		return nil, nil // 未找到返回 nil（非错误），便于上层区分
	}
	if err != nil {
		return nil, fmt.Errorf("GetTopic(%s) 失败: %w", id, err)
	}
	return &t, nil
}

// UpdatePaperCount 刷新某主题下的论文计数（同步完成后调用）。
func (r *Repository) UpdatePaperCount(topicID string) error {
	_, err := r.db.Exec(
		`UPDATE topics SET paper_count=(
		    SELECT COUNT(*) FROM papers WHERE topic_id=?
		 ) WHERE id=?`, topicID, topicID)
	if err != nil {
		return fmt.Errorf("UpdatePaperCount(%s) 失败: %w", topicID, err)
	}
	return nil
}

// UpsertPaper 插入或更新一篇论文（按主键 id 幂等）。
// 重复同步时已存在的论文保留 read_status/obsidian_path（用户阅读进度不被覆盖）。
func (r *Repository) UpsertPaper(p Paper) error {
	_, err := r.db.Exec(
		`INSERT INTO papers(id, title, authors, year, topic_id, pdf_url, doi, abstract, read_status, obsidian_path)
		 VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		 ON CONFLICT(id) DO UPDATE SET
		   title=excluded.title, authors=excluded.authors, year=excluded.year,
		   topic_id=excluded.topic_id, pdf_url=excluded.pdf_url, doi=excluded.doi,
		   abstract=excluded.abstract`,
		p.ID, p.Title, p.Authors, p.Year, p.TopicID, p.PDFURL, p.DOI, p.Abstract,
		p.ReadStatus, p.ObsidianPath,
	)
	if err != nil {
		return fmt.Errorf("UpsertPaper(%s) 失败: %w", p.ID, err)
	}
	return nil
}

// ListPapersByTopic 按 topic 返回论文列表，按 title 排序。
func (r *Repository) ListPapersByTopic(topicID string) ([]Paper, error) {
	rows, err := r.db.Query(
		`SELECT id, title, COALESCE(authors,''), COALESCE(year,0), COALESCE(topic_id,''),
		        COALESCE(pdf_url,''), COALESCE(doi,''), COALESCE(abstract,''),
		        COALESCE(read_status,'unread'), COALESCE(obsidian_path,''), COALESCE(created_at,''),
		        COALESCE(source,''), COALESCE(venue,''), COALESCE(level,''),
		        COALESCE(paper_type,''), COALESCE(sub_domain,''), COALESCE(difficulty_score,5),
		        COALESCE(tags,'[]'), COALESCE(ai_classified,0), COALESCE(company,''),
		        COALESCE(github_repo,''), COALESCE(arxiv_id,''),
		        COALESCE(last_read_at,''), COALESCE(total_read_seconds,0)
		 FROM papers WHERE topic_id=? ORDER BY title`, topicID)
	if err != nil {
		return nil, fmt.Errorf("ListPapersByTopic(%s) 查询失败: %w", topicID, err)
	}
	defer rows.Close()

	var papers []Paper
	for rows.Next() {
		var p Paper
		if err := scanPaperFull(rows, &p); err != nil {
			return nil, fmt.Errorf("ListPapersByTopic 扫描失败: %w", err)
		}
		papers = append(papers, p)
	}
	return papers, rows.Err()
}

// GetPaper 按 id 查询单篇论文。
func (r *Repository) GetPaper(id string) (*Paper, error) {
	var p Paper
	err := r.db.QueryRow(
		`SELECT id, title, COALESCE(authors,''), COALESCE(year,0), COALESCE(topic_id,''),
		        COALESCE(pdf_url,''), COALESCE(doi,''), COALESCE(abstract,''),
		        COALESCE(read_status,'unread'), COALESCE(obsidian_path,''), COALESCE(created_at,''),
		        COALESCE(source,''), COALESCE(venue,''), COALESCE(level,''),
		        COALESCE(paper_type,''), COALESCE(sub_domain,''), COALESCE(difficulty_score,5),
		        COALESCE(tags,'[]'), COALESCE(ai_classified,0), COALESCE(company,''),
		        COALESCE(github_repo,''), COALESCE(arxiv_id,''),
		        COALESCE(last_read_at,''), COALESCE(total_read_seconds,0)
		 FROM papers WHERE id=?`, id,
	).Scan(&p.ID, &p.Title, &p.Authors, &p.Year, &p.TopicID,
		&p.PDFURL, &p.DOI, &p.Abstract, &p.ReadStatus, &p.ObsidianPath, &p.CreatedAt,
		&p.Source, &p.Venue, &p.Level, &p.PaperType, &p.SubDomain, &p.DifficultyScore,
		&p.Tags, &p.AIClassified, &p.Company, &p.GitHubRepo, &p.ArxivID,
		&p.LastReadAt, &p.TotalReadSeconds)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("GetPaper(%s) 失败: %w", id, err)
	}
	return &p, nil
}

// scanPaperFull 将一行完整论文字段扫描到 Paper。
// 列顺序须与 ListPapersByTopic / ListPapers 的 SELECT 一致。
func scanPaperFull(rows *sql.Rows, p *Paper) error {
	return rows.Scan(&p.ID, &p.Title, &p.Authors, &p.Year, &p.TopicID,
		&p.PDFURL, &p.DOI, &p.Abstract, &p.ReadStatus, &p.ObsidianPath, &p.CreatedAt,
		&p.Source, &p.Venue, &p.Level, &p.PaperType, &p.SubDomain, &p.DifficultyScore,
		&p.Tags, &p.AIClassified, &p.Company, &p.GitHubRepo, &p.ArxivID,
		&p.LastReadAt, &p.TotalReadSeconds)
}

// UpdateReadStatus 更新论文阅读状态。这是用户操作，不应被同步覆盖。
func (r *Repository) UpdateReadStatus(id, status string) error {
	_, err := r.db.Exec(`UPDATE papers SET read_status=? WHERE id=?`, status, id)
	if err != nil {
		return fmt.Errorf("UpdateReadStatus(%s) 失败: %w", id, err)
	}
	return nil
}

// CountPapers 返回论文总数（首页统计用，验证"重启后是否为 0"的直接指标）。
func (r *Repository) CountPapers() (int, error) {
	var n int
	err := r.db.QueryRow(`SELECT COUNT(*) FROM papers`).Scan(&n)
	if err != nil {
		return 0, fmt.Errorf("CountPapers 失败: %w", err)
	}
	return n, nil
}

// Slugify 将目录名/文件名转为稳定 id 用的 slug。
// 规则：小写、空格转下划线、去除非 [a-z0-9_-] 字符。
// 用于保证同一篇论文在多次同步中生成相同 id，使 Upsert 命中同一行。
func Slugify(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	// 空格/制表符转下划线
	s = strings.ReplaceAll(s, " ", "_")
	s = strings.ReplaceAll(s, "\t", "_")
	var b strings.Builder
	for i := 0; i < len(s); i++ {
		c := s[i]
		// 保留小写字母、数字、下划线、连字符；其余丢弃
		if (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-' {
			b.WriteByte(c)
		}
	}
	return b.String()
}

// Source 表示一个论文数据源（arxiv/openalex/acl/company 等）。
type Source struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	SourceType   string `json:"source_type"`
	Enabled      int    `json:"enabled"`
	LastSyncedAt string `json:"last_synced_at"`
	SyncCount    int    `json:"sync_count"`
	Config       string `json:"config"`
}

// paperMetaID 按 arxiv_id > doi > uuid 的优先级生成稳定 id。
func paperMetaID(meta PaperMeta) string {
	if meta.ArxivID != "" {
		return "arxiv_" + meta.ArxivID
	}
	if meta.DOI != "" {
		return "doi_" + meta.DOI
	}
	return "uuid_" + uuid.New().String()
}

// tagsToJSON 将标签切片序列化为 JSON 字符串；空切片返回空串。
func tagsToJSON(tags []string) string {
	if len(tags) == 0 {
		return ""
	}
	b, err := json.Marshal(tags)
	if err != nil {
		return ""
	}
	return string(b)
}

// UpsertPaperMeta 将数据源返回的 PaperMeta 幂等写入 papers 表。
// id 生成规则：有 arxiv_id 用 arxiv_{arxiv_id}，有 doi 用 doi_{doi}，否则 uuid_{uuid}。
// 不覆盖 read_status/obsidian_path/last_read_at/total_read_seconds（用户阅读状态与笔记）。
// 若论文已存在且 ai_classified=0（人工预设），不覆盖 tags；level/paper_type/sub_domain/difficulty_score
// 由 AI 分类流程维护，本方法（数据源同步）不触碰它们。
func (r *Repository) UpsertPaperMeta(meta PaperMeta) error {
	id := paperMetaID(meta)
	tagsJSON := tagsToJSON(meta.Tags)
	_, err := r.db.Exec(
		`INSERT INTO papers(id, title, authors, year, abstract, pdf_url, doi, arxiv_id,
			source, venue, company, github_repo, tags, ai_classified)
		 VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
		 ON CONFLICT(id) DO UPDATE SET
			title=excluded.title, authors=excluded.authors, year=excluded.year,
			abstract=excluded.abstract, pdf_url=excluded.pdf_url, doi=excluded.doi,
			arxiv_id=excluded.arxiv_id, source=excluded.source, venue=excluded.venue,
			company=excluded.company, github_repo=excluded.github_repo,
			tags=CASE WHEN papers.ai_classified=0 THEN papers.tags ELSE excluded.tags END`,
		id, meta.Title, meta.Authors, meta.Year, meta.Abstract, meta.PDFURL, meta.DOI,
		meta.ArxivID, meta.Source, meta.Venue, meta.Company, meta.GitHubRepo, tagsJSON,
	)
	if err != nil {
		return fmt.Errorf("UpsertPaperMeta(%s) 失败: %w", id, err)
	}
	return nil
}

// UpdateSourceSync UPSERT 到 sources 表，刷新 last_synced_at 与 sync_count。
// name/source_type 为 NOT NULL 列，首次插入以空串占位（由源注册流程另行维护），
// 冲突时仅更新 last_synced_at 与 sync_count，不覆盖已有的 name/source_type。
func (r *Repository) UpdateSourceSync(sourceID string, count int) error {
	_, err := r.db.Exec(
		`INSERT INTO sources(id, name, source_type, last_synced_at, sync_count)
		 VALUES(?, '', '', datetime('now'), ?)
		 ON CONFLICT(id) DO UPDATE SET last_synced_at=datetime('now'), sync_count=excluded.sync_count`,
		sourceID, count,
	)
	if err != nil {
		return fmt.Errorf("UpdateSourceSync(%s) 失败: %w", sourceID, err)
	}
	return nil
}

// ListSources 查询全部数据源，按 id 排序。
func (r *Repository) ListSources() ([]Source, error) {
	rows, err := r.db.Query(
		`SELECT id, COALESCE(name,''), COALESCE(source_type,''), COALESCE(enabled,1),
		        COALESCE(last_synced_at,''), COALESCE(sync_count,0), COALESCE(config,'')
		 FROM sources ORDER BY id`)
	if err != nil {
		return nil, fmt.Errorf("ListSources 查询失败: %w", err)
	}
	defer rows.Close()

	var sources []Source
	for rows.Next() {
		var s Source
		if err := rows.Scan(&s.ID, &s.Name, &s.SourceType, &s.Enabled,
			&s.LastSyncedAt, &s.SyncCount, &s.Config); err != nil {
			return nil, fmt.Errorf("ListSources 扫描失败: %w", err)
		}
		sources = append(sources, s)
	}
	return sources, rows.Err()
}

// GetSource 按 id 查询单个数据源。
func (r *Repository) GetSource(id string) (*Source, error) {
	var s Source
	err := r.db.QueryRow(
		`SELECT id, COALESCE(name,''), COALESCE(source_type,''), COALESCE(enabled,1),
		        COALESCE(last_synced_at,''), COALESCE(sync_count,0), COALESCE(config,'')
		 FROM sources WHERE id=?`, id,
	).Scan(&s.ID, &s.Name, &s.SourceType, &s.Enabled, &s.LastSyncedAt, &s.SyncCount, &s.Config)
	if err == sql.ErrNoRows {
		return nil, nil // 未找到返回 nil（非错误），便于上层区分
	}
	if err != nil {
		return nil, fmt.Errorf("GetSource(%s) 失败: %w", id, err)
	}
	return &s, nil
}

// --- 论文检索/阅读历史相关方法 ---

// PaperFilter 是 ListPapers 的过滤条件。
type PaperFilter struct {
	Source    string // 数据源：arxiv/openalex/acl/company
	Level     string // 难度：beginner/intermediate/advanced
	SubDomain string // 子领域：ml/dl/llm/...
	PaperType string // 论文类型：survey/tutorial/...
	Query     string // 关键词（标题/作者/摘要模糊匹配）
	Page      int    // 页码，从 1 开始
	PageSize  int    // 每页条数
}

// ReadingStats 是论文阅读历史统计。
type ReadingStats struct {
	Count        int    `json:"count"`         // 阅读次数（reading_history 记录数）
	TotalSeconds int    `json:"total_seconds"` // 累计阅读时长（秒）
	LastReadAt   string `json:"last_read_at"`  // 上次阅读时间
}

// PaperDetail 是论文详情（论文元数据 + 阅读统计）。
type PaperDetail struct {
	Paper
	ReadingStats ReadingStats `json:"reading_stats"`
}

// ListPapers 按过滤条件分页查询论文，返回论文列表与总数。
// 过滤条件为空时返回全量（分页）。关键词 q 对 title/authors/abstract 做大小写不敏感 LIKE。
func (r *Repository) ListPapers(filter PaperFilter) ([]Paper, int, error) {
	// 构造 WHERE 子句
	where := "1=1"
	args := []interface{}{}
	if filter.Source != "" {
		where += " AND source=?"
		args = append(args, filter.Source)
	}
	if filter.Level != "" {
		where += " AND level=?"
		args = append(args, filter.Level)
	}
	if filter.SubDomain != "" {
		where += " AND sub_domain=?"
		args = append(args, filter.SubDomain)
	}
	if filter.PaperType != "" {
		where += " AND paper_type=?"
		args = append(args, filter.PaperType)
	}
	if filter.Query != "" {
		where += " AND (title LIKE ? OR authors LIKE ? OR abstract LIKE ?)"
		q := "%" + filter.Query + "%"
		args = append(args, q, q, q)
	}

	// 查询总数
	var total int
	if err := r.db.QueryRow("SELECT COUNT(*) FROM papers WHERE "+where, args...).Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("ListPapers count 失败: %w", err)
	}

	// 分页查询
	offset := (filter.Page - 1) * filter.PageSize
	query := `SELECT id, title, COALESCE(authors,''), COALESCE(year,0), COALESCE(topic_id,''),
	                COALESCE(pdf_url,''), COALESCE(doi,''), COALESCE(abstract,''),
	                COALESCE(read_status,'unread'), COALESCE(obsidian_path,''), COALESCE(created_at,''),
	                COALESCE(source,''), COALESCE(venue,''), COALESCE(level,''),
	                COALESCE(paper_type,''), COALESCE(sub_domain,''), COALESCE(difficulty_score,5),
	                COALESCE(tags,'[]'), COALESCE(ai_classified,0), COALESCE(company,''),
	                COALESCE(github_repo,''), COALESCE(arxiv_id,''),
	                COALESCE(last_read_at,''), COALESCE(total_read_seconds,0)
	         FROM papers WHERE ` + where + `
	         ORDER BY created_at DESC LIMIT ? OFFSET ?`
	args = append(args, filter.PageSize, offset)

	rows, err := r.db.Query(query, args...)
	if err != nil {
		return nil, 0, fmt.Errorf("ListPapers 查询失败: %w", err)
	}
	defer rows.Close()

	var papers []Paper
	for rows.Next() {
		var p Paper
		if err := scanPaperFull(rows, &p); err != nil {
			return nil, 0, fmt.Errorf("ListPapers 扫描失败: %w", err)
		}
		papers = append(papers, p)
	}
	return papers, total, rows.Err()
}

// GetPaperWithHistory 返回论文详情 + 阅读历史统计。
func (r *Repository) GetPaperWithHistory(id string) (*PaperDetail, error) {
	p, err := r.GetPaper(id)
	if err != nil {
		return nil, err
	}
	if p == nil {
		return nil, nil
	}
	detail := &PaperDetail{Paper: *p}

	var count int
	var totalSeconds int
	var lastReadAt string
	err = r.db.QueryRow(
		`SELECT COUNT(*), COALESCE(SUM(duration_seconds),0), COALESCE(MAX(end_time),'')
		 FROM reading_history WHERE paper_id=?`, id,
	).Scan(&count, &totalSeconds, &lastReadAt)
	if err != nil {
		return nil, fmt.Errorf("GetPaperWithHistory 读取统计失败: %w", err)
	}
	detail.ReadingStats = ReadingStats{
		Count:        count,
		TotalSeconds: totalSeconds,
		LastReadAt:   lastReadAt,
	}
	return detail, nil
}

// GetRelatedPapers 返回与指定论文 sub_domain 相同的论文（排除自身），按难度升序取前 limit 篇。
func (r *Repository) GetRelatedPapers(id string, limit int) ([]Paper, error) {
	// 先取目标论文的 sub_domain
	var subDomain string
	err := r.db.QueryRow(
		`SELECT COALESCE(sub_domain,'') FROM papers WHERE id=?`, id,
	).Scan(&subDomain)
	if err == sql.ErrNoRows {
		return nil, nil // 论文不存在，返回 nil（上层 404）
	}
	if err != nil {
		return nil, fmt.Errorf("GetRelatedPapers(%s) 查询 sub_domain 失败: %w", id, err)
	}
	if subDomain == "" {
		return []Paper{}, nil // 无子领域信息，返回空
	}

	rows, err := r.db.Query(
		`SELECT id, title, COALESCE(authors,''), COALESCE(year,0), COALESCE(topic_id,''),
		        COALESCE(pdf_url,''), COALESCE(doi,''), COALESCE(abstract,''),
		        COALESCE(read_status,'unread'), COALESCE(obsidian_path,''), COALESCE(created_at,''),
		        COALESCE(source,''), COALESCE(venue,''), COALESCE(level,''),
		        COALESCE(paper_type,''), COALESCE(sub_domain,''), COALESCE(difficulty_score,5),
		        COALESCE(tags,'[]'), COALESCE(ai_classified,0), COALESCE(company,''),
		        COALESCE(github_repo,''), COALESCE(arxiv_id,''),
		        COALESCE(last_read_at,''), COALESCE(total_read_seconds,0)
		 FROM papers WHERE sub_domain=? AND id<>?
		 ORDER BY difficulty_score ASC LIMIT ?`, subDomain, id, limit)
	if err != nil {
		return nil, fmt.Errorf("GetRelatedPapers(%s) 查询失败: %w", id, err)
	}
	defer rows.Close()

	var papers []Paper
	for rows.Next() {
		var p Paper
		if err := scanPaperFull(rows, &p); err != nil {
			return nil, fmt.Errorf("GetRelatedPapers 扫描失败: %w", err)
		}
		papers = append(papers, p)
	}
	return papers, rows.Err()
}

// CreateReadingHistory 创建一条阅读历史记录（id=uuid, paper_id, start_time=now）。
// 返回生成的 history id。
func (r *Repository) CreateReadingHistory(paperID string) (string, error) {
	historyID := uuid.NewString()
	_, err := r.db.Exec(
		`INSERT INTO reading_history(id, paper_id, start_time) VALUES(?, ?, datetime('now'))`,
		historyID, paperID,
	)
	if err != nil {
		return "", fmt.Errorf("CreateReadingHistory(%s) 失败: %w", paperID, err)
	}
	return historyID, nil
}

// UpdatePaperReadStatus 更新论文阅读状态。
func (r *Repository) UpdatePaperReadStatus(id, status string) error {
	_, err := r.db.Exec(`UPDATE papers SET read_status=? WHERE id=?`, status, id)
	if err != nil {
		return fmt.Errorf("UpdatePaperReadStatus(%s) 失败: %w", id, err)
	}
	return nil
}

// EndReadingHistory 结束一次阅读会话：
//   - 计算 duration_seconds = now - start_time；
//   - 更新 reading_history 的 end_time 与 duration_seconds；
//   - 更新 papers 表的 last_read_at 与 total_read_seconds += duration。
//
// 内部调用 UpdatePaperReadStats 聚合阅读统计。
func (r *Repository) EndReadingHistory(historyID string) error {
	var paperID string
	var startTime string
	err := r.db.QueryRow(
		`SELECT paper_id, start_time FROM reading_history WHERE id=?`, historyID,
	).Scan(&paperID, &startTime)
	if err == sql.ErrNoRows {
		return fmt.Errorf("阅读历史 %s 不存在", historyID)
	}
	if err != nil {
		return fmt.Errorf("EndReadingHistory(%s) 查询失败: %w", historyID, err)
	}

	// 用 SQLite 的 strftime 计算秒差，避免 Go 侧时区/格式差异
	var duration int
	err = r.db.QueryRow(
		`SELECT CAST(strftime('%s', 'now') AS INTEGER) - CAST(strftime('%s', ?) AS INTEGER)`,
		startTime,
	).Scan(&duration)
	if err != nil {
		return fmt.Errorf("EndReadingHistory 计算时长失败: %w", err)
	}
	if duration < 0 {
		duration = 0
	}

	// 更新 reading_history
	if _, err := r.db.Exec(
		`UPDATE reading_history SET end_time=datetime('now'), duration_seconds=? WHERE id=?`,
		duration, historyID,
	); err != nil {
		return fmt.Errorf("EndReadingHistory 更新历史失败: %w", err)
	}

	// 更新 papers 阅读统计
	if err := r.UpdatePaperReadStats(paperID, duration); err != nil {
		return err
	}
	return nil
}

// UpdatePaperReadStats 累加论文阅读时长，并刷新 last_read_at。
func (r *Repository) UpdatePaperReadStats(id string, durationSeconds int) error {
	_, err := r.db.Exec(
		`UPDATE papers SET last_read_at=datetime('now'),
		        total_read_seconds=total_read_seconds+? WHERE id=?`,
		durationSeconds, id,
	)
	if err != nil {
		return fmt.Errorf("UpdatePaperReadStats(%s) 失败: %w", id, err)
	}
	return nil
}
