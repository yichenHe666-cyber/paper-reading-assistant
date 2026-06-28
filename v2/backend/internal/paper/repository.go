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
	ID         string // 稳定 id（目录名 slug 化）
	Name       string // 原始目录名
	NameCN     string // 中文名称（可空）
	PaperCount int    // 该主题下论文数（同步后更新）
	CreatedAt  string // 创建时间
}

// Paper 表示一篇论文的元数据。
type Paper struct {
	ID           string // 稳定 id（topic_id/slug 派生）
	Title        string // 标题
	Authors      string // 作者（逗号分隔）
	Year         int    // 发表年份（0 表示未知）
	TopicID      string // 所属主题 id
	PDFURL       string // PDF 下载地址
	DOI          string // DOI
	Abstract     string // 摘要
	ReadStatus   string // 阅读状态：unread/reading/done/reread
	ObsidianPath string // Obsidian 笔记路径
	CreatedAt    string // 创建时间
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

// ListPapers 按 topic 返回论文列表，按 title 排序。
func (r *Repository) ListPapers(topicID string) ([]Paper, error) {
	rows, err := r.db.Query(
		`SELECT id, title, COALESCE(authors,''), COALESCE(year,0), COALESCE(topic_id,''),
		        COALESCE(pdf_url,''), COALESCE(doi,''), COALESCE(abstract,''),
		        COALESCE(read_status,'unread'), COALESCE(obsidian_path,''), COALESCE(created_at,'')
		 FROM papers WHERE topic_id=? ORDER BY title`, topicID)
	if err != nil {
		return nil, fmt.Errorf("ListPapers(%s) 查询失败: %w", topicID, err)
	}
	defer rows.Close()

	var papers []Paper
	for rows.Next() {
		var p Paper
		if err := rows.Scan(&p.ID, &p.Title, &p.Authors, &p.Year, &p.TopicID,
			&p.PDFURL, &p.DOI, &p.Abstract, &p.ReadStatus, &p.ObsidianPath, &p.CreatedAt); err != nil {
			return nil, fmt.Errorf("ListPapers 扫描失败: %w", err)
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
		        COALESCE(read_status,'unread'), COALESCE(obsidian_path,''), COALESCE(created_at,'')
		 FROM papers WHERE id=?`, id,
	).Scan(&p.ID, &p.Title, &p.Authors, &p.Year, &p.TopicID,
		&p.PDFURL, &p.DOI, &p.Abstract, &p.ReadStatus, &p.ObsidianPath, &p.CreatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("GetPaper(%s) 失败: %w", id, err)
	}
	return &p, nil
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
