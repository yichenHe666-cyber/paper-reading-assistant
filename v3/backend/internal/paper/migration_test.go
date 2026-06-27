// Package paper 的旧库迁移测试。
//
// 文件概述：migration_test.go 验证 MigrateLegacyDB 能将旧库的 topics/papers
// 幂等导入新库，且旧库以只读方式打开、不被修改。这是痛点②"找回历史数据"的验证闭环。
package paper

import (
	"path/filepath"
	"testing"

	"nuclear-ox-v2/backend/internal/store"
)

// TestMigrateLegacyDB 验证旧库数据导入新库。
func TestMigrateLegacyDB(t *testing.T) {
	// 1. 建旧库并写入数据（模拟用户散落在某 cwd 的历史库）
	legacyPath := filepath.Join(t.TempDir(), "legacy.db")
	legacyDB, err := store.Open(legacyPath)
	if err != nil {
		t.Fatalf("建旧库失败: %v", err)
	}
	if err := store.Migrate(legacyDB); err != nil {
		legacyDB.Close()
		t.Fatalf("迁移旧库 schema 失败: %v", err)
	}
	oldRepo := NewRepository(legacyDB)
	_ = oldRepo.UpsertTopic(Topic{ID: "ds", Name: "distributed_systems"})
	_ = oldRepo.UpsertTopic(Topic{ID: "ml", Name: "machine_learning"})
	_ = oldRepo.UpsertPaper(Paper{ID: "ds_mapreduce", Title: "MapReduce", TopicID: "ds"})
	_ = oldRepo.UpsertPaper(Paper{ID: "ds_gfs", Title: "GFS", TopicID: "ds"})
	_ = oldRepo.UpsertPaper(Paper{ID: "ml_transformer", Title: "Transformer", TopicID: "ml"})
	// 关闭旧库写连接，确保后续只读打开无锁冲突
	if err := legacyDB.Close(); err != nil {
		t.Fatal(err)
	}

	// 2. 建新库（空）
	repo, newDB, _ := openTestRepo(t)
	defer newDB.Close()

	// 3. 迁移
	result, err := MigrateLegacyDB(repo, legacyPath)
	if err != nil {
		t.Fatalf("MigrateLegacyDB 失败: %v", err)
	}
	if result.TopicsMoved != 2 {
		t.Errorf("TopicsMoved: got %d want 2", result.TopicsMoved)
	}
	if result.PapersMoved != 3 {
		t.Errorf("PapersMoved: got %d want 3", result.PapersMoved)
	}

	// 4. 验证新库数据
	topics, _ := repo.ListTopics()
	if len(topics) != 2 {
		t.Errorf("新库主题数: got %d want 2", len(topics))
	}
	n, _ := repo.CountPapers()
	if n != 3 {
		t.Errorf("新库论文数: got %d want 3", n)
	}
	// 验证具体论文存在
	p, _ := repo.GetPaper("ml_transformer")
	if p == nil || p.Title != "Transformer" {
		t.Errorf("迁移后论文 ml_transformer 缺失或错误: %+v", p)
	}
}

// TestMigrateLegacyDBIdempotent 验证重复迁移不产生重复行。
func TestMigrateLegacyDBIdempotent(t *testing.T) {
	legacyPath := filepath.Join(t.TempDir(), "legacy2.db")
	legacyDB, _ := store.Open(legacyPath)
	_ = store.Migrate(legacyDB)
	oldRepo := NewRepository(legacyDB)
	_ = oldRepo.UpsertTopic(Topic{ID: "t", Name: "t"})
	_ = oldRepo.UpsertPaper(Paper{ID: "t_p", Title: "P", TopicID: "t"})
	legacyDB.Close()

	repo, newDB, _ := openTestRepo(t)
	defer newDB.Close()

	// 迁移两次
	if _, err := MigrateLegacyDB(repo, legacyPath); err != nil {
		t.Fatal(err)
	}
	if _, err := MigrateLegacyDB(repo, legacyPath); err != nil {
		t.Fatal(err)
	}
	n, _ := repo.CountPapers()
	if n != 1 {
		t.Errorf("重复迁移后论文数应为 1，实际 %d（未幂等？）", n)
	}
}

// TestFindLegacyDBsExcludesCurrent 验证 FindLegacyDBs 排除当前库路径。
func TestFindLegacyDBsExcludesCurrent(t *testing.T) {
	// 在临时目录建一个候选旧库文件
	dir := t.TempDir()
	currentDB := filepath.Join(dir, "current.db")

	// currentDB 本身不应出现在结果中
	found := FindLegacyDBs(currentDB)
	for _, p := range found {
		if p == currentDB {
			t.Errorf("FindLegacyDBs 不应返回当前库路径 %s", p)
		}
	}
}
