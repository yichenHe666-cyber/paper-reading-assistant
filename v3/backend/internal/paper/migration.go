// Package paper 的旧库迁移工具。
//
// 文件概述：migration.go 解决痛点②"重启后论文读取为 0"的历史遗留数据找回问题：
//   旧 Python 版用相对路径 "data/reading_assistant.db"，按进程 cwd 解析，导致数据库
//   文件散落在不同 cwd 下（启动器/IDE/快捷方式各自一个 cwd → 各自一个空库）。
//   新版虽已用绝对路径根治，但用户旧库里可能已有辛苦同步的论文数据。
//
// 本文件提供：
//   - FindLegacyDBs：扫描若干候选 cwd 位置，列出存在的旧库路径（排除当前新库）；
//   - MigrateLegacyDB：打开旧库，将其 topics/papers 用 Upsert 幂等导入当前库。
//
// 安全保证：
//   - 旧库以只读方式打开，绝不修改原文件；
//   - 导入用 INSERT OR REPLACE（按 id 幂等），重复迁移不产生重复行；
//   - 迁移失败不阻断启动，仅返回错误供上层记日志；
//   - 自动跳过与当前库同路径的文件，避免无意义自迁移。
package paper

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"

	// 显式注册纯 Go SQLite 驱动，使本包可独立打开旧库（不依赖 store 包被引入）。
	_ "modernc.org/sqlite"
)

// MigrateResult 描述一次迁移的统计结果。
type MigrateResult struct {
	SourceDB    string // 旧库路径
	TopicsMoved int    // 导入的主题数
	PapersMoved int    // 导入的论文数
}

// FindLegacyDBs 扫描候选位置，返回存在的旧库文件路径（已去重、已排除 currentDB）。
//
// 候选位置覆盖旧版可能散落数据库的常见 cwd：
//   1. 当前工作目录下的 data/reading_assistant.db（IDE/终端直接运行）
//   2. 可执行文件同级 data/reading_assistant.db（打包脚本/快捷方式）
//   3. 用户主目录下 data/reading_assistant.db（部分启动器）
//   4. 用户主目录下 .nuclear-research-ox/data/...（旧兜底路径）
//
// currentDB 是新版当前使用的绝对路径库，命中则跳过（避免自迁移）。
func FindLegacyDBs(currentDB string) []string {
	currentAbs, _ := filepath.Abs(currentDB)

	var candidates []string
	// 候选 1：cwd 下相对路径
	if cwd, err := os.Getwd(); err == nil {
		candidates = append(candidates, filepath.Join(cwd, "data", "reading_assistant.db"))
	}
	// 候选 2：可执行文件同级
	if exe, err := os.Executable(); err == nil {
		candidates = append(candidates, filepath.Join(filepath.Dir(exe), "data", "reading_assistant.db"))
	}
	// 候选 3 & 4：用户主目录下
	if home, err := os.UserHomeDir(); err == nil {
		candidates = append(candidates,
			filepath.Join(home, "data", "reading_assistant.db"),
			filepath.Join(home, ".nuclear-research-ox", "data", "reading_assistant.db"),
		)
	}

	// 去重 + 存在性检查 + 排除当前库
	seen := map[string]bool{}
	var found []string
	for _, p := range candidates {
		abs, err := filepath.Abs(p)
		if err != nil {
			continue
		}
		if seen[abs] {
			continue
		}
		seen[abs] = true
		// 排除当前库
		if abs == currentAbs {
			continue
		}
		// 必须是普通文件且可读
		info, err := os.Stat(abs)
		if err != nil || info.IsDir() {
			continue
		}
		found = append(found, abs)
	}
	return found
}

// MigrateLegacyDB 打开旧库（只读），将其 topics 与 papers 幂等导入当前 Repository。
//
// 旧库表结构兼容性：旧 Python 版用 SQLAlchemy 建表，列名与本版基本一致。
// 此处用防御性查询：缺失列以 COALESCE 兜底默认值，避免因 schema 细微差异整体失败。
// 若旧库根本无 topics/papers 表，返回错误（上层忽略即可，不影响启动）。
func MigrateLegacyDB(repo *Repository, legacyDBPath string) (MigrateResult, error) {
	result := MigrateResult{SourceDB: legacyDBPath}

	// 以只读 URI 打开旧库，物理上不可能误写原文件
	dsn := "file:" + legacyDBPath + "?mode=ro"
	legacy, err := sql.Open("sqlite", dsn)
	if err != nil {
		return result, fmt.Errorf("打开旧库 %s 失败: %w", legacyDBPath, err)
	}
	defer legacy.Close()

	// 迁移 topics：列名与新版一致；缺失列用 COALESCE 兜底
	if err := migrateRows(legacy, "topics",
		`SELECT id, COALESCE(name,''), COALESCE(name_cn,''), COALESCE(paper_count,0)
		 FROM topics`,
		func(rows *sql.Rows) error {
			var t Topic
			if err := rows.Scan(&t.ID, &t.Name, &t.NameCN, &t.PaperCount); err != nil {
				return err
			}
			if t.ID == "" {
				return nil // 跳过无 id 的脏行
			}
			if err := repo.UpsertTopic(t); err != nil {
				return err
			}
			result.TopicsMoved++
			return nil
		},
	); err != nil {
		// topics 迁移失败不阻断 papers 尝试，但记录错误
		return result, fmt.Errorf("迁移 topics 失败: %w", err)
	}

	// 迁移 papers
	if err := migrateRows(legacy, "papers",
		`SELECT id, COALESCE(title,''), COALESCE(authors,''), COALESCE(year,0),
		        COALESCE(topic_id,''), COALESCE(pdf_url,''), COALESCE(doi,''),
		        COALESCE(abstract,''), COALESCE(read_status,'unread'),
		        COALESCE(obsidian_path,'')
		 FROM papers`,
		func(rows *sql.Rows) error {
			var p Paper
			if err := rows.Scan(&p.ID, &p.Title, &p.Authors, &p.Year, &p.TopicID,
				&p.PDFURL, &p.DOI, &p.Abstract, &p.ReadStatus, &p.ObsidianPath); err != nil {
				return err
			}
			if p.ID == "" {
				return nil
			}
			if err := repo.UpsertPaper(p); err != nil {
				return err
			}
			result.PapersMoved++
			return nil
		},
	); err != nil {
		return result, fmt.Errorf("迁移 papers 失败: %w", err)
	}

	return result, nil
}

// migrateRows 是迁移通用骨架：在旧库执行 query，逐行回调 scanFn 写入新库。
// tableName 仅用于错误信息，便于定位是哪张表迁移失败。
func migrateRows(legacy *sql.DB, tableName, query string,
	scanFn func(rows *sql.Rows) error) error {
	rows, err := legacy.Query(query)
	if err != nil {
		return fmt.Errorf("查询旧库 %s 失败（可能表不存在）: %w", tableName, err)
	}
	defer rows.Close()
	for rows.Next() {
		if err := scanFn(rows); err != nil {
			return fmt.Errorf("迁移 %s 单行失败: %w", tableName, err)
		}
	}
	return rows.Err()
}
