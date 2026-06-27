// Package store 的运行时冒烟测试。
//
// 文件概述：store_test.go 验证 SQLite 持久化层在真实驱动下能正确：
//   1. 打开数据库文件（modernc.org/sqlite 纯 Go 驱动，非 cgo）；
//   2. 执行 Migrate 创建全部业务表且幂等（重复执行不报错、不丢数据）；
//   3. 启用 WAL 模式（读写并发基础）；
//   4. 关闭后重新打开同一文件，表结构与数据仍在（验证非内存库、非临时库）。
//
// 这些测试是"重启后论文丢失"痛点修复的最小验证闭环：只要库文件路径稳定（由 config 层保证绝对路径），
// 重开即得旧数据。本测试用 t.TempDir() 模拟稳定路径。
package store

import (
	"database/sql"
	"path/filepath"
	"strings"
	"testing"
)

// expectedTables 是 Migrate 应创建的全部业务表名。
// 若后续里程碑新增表，需同步追加到这里，避免漏建。
var expectedTables = []string{
	"topics", "papers", "chat_sessions", "chat_messages",
	"skills", "memories", "decision_ledger", "llm_calls", "llm_cache",
}

// TestOpenAndMigrate 验证开库 + 建表 + 幂等性 + 重开后数据持久。
func TestOpenAndMigrate(t *testing.T) {
	// 使用临时目录，测试结束自动清理；路径绝对，模拟 config 层传入的绝对路径
	dbPath := filepath.Join(t.TempDir(), "test.db")

	// 第一次打开并迁移
	db, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	if err := Migrate(db); err != nil {
		db.Close()
		t.Fatalf("首次 Migrate 失败: %v", err)
	}
	// 幂等性：再次 Migrate 不应报错（CREATE TABLE IF NOT EXISTS）
	if err := Migrate(db); err != nil {
		db.Close()
		t.Fatalf("二次 Migrate 应幂等，但失败: %v", err)
	}

	// 校验全部预期表都已创建
	got, err := tableNames(db)
	if err != nil {
		db.Close()
		t.Fatalf("读取表名失败: %v", err)
	}
	for _, want := range expectedTables {
		if !contains(got, want) {
			db.Close()
			t.Fatalf("缺失表 %q；实际表: %v", want, got)
		}
	}

	// 写入一条 topic 并提交，验证非内存库
	if _, err := db.Exec(
		`INSERT INTO topics(id, name) VALUES(?, ?)`, "t1", "distributed_systems"); err != nil {
		db.Close()
		t.Fatalf("插入 topics 失败: %v", err)
	}
	db.Close()

	// 重新打开同一文件，验证数据持久（这是"重启不丢数据"的核心保证）
	db2, err := Open(dbPath)
	if err != nil {
		t.Fatalf("重开数据库失败: %v", err)
	}
	defer db2.Close()

	var name string
	if err := db2.QueryRow(`SELECT name FROM topics WHERE id=?`, "t1").Scan(&name); err != nil {
		t.Fatalf("重开后读取失败（数据未持久？）: %v", err)
	}
	if name != "distributed_systems" {
		t.Fatalf("重开后数据不一致: got %q", name)
	}
}

// TestWALMode 验证 WAL 模式确实启用（PRAGMA journal_mode 应返回 "wal"）。
func TestWALMode(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "wal.db")
	db, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	defer db.Close()

	var mode string
	// 注意：modernc.org/sqlite 对 PRAGMA 查询返回小写 "wal"
	if err := db.QueryRow(`PRAGMA journal_mode;`).Scan(&mode); err != nil {
		t.Fatalf("读取 journal_mode 失败: %v", err)
	}
	if strings.ToLower(mode) != "wal" {
		t.Fatalf("WAL 未启用，实际 journal_mode=%q", mode)
	}
}

// tableNames 从 sqlite_master 读取所有用户表名。
func tableNames(db *sql.DB) ([]string, error) {
	rows, err := db.Query(`SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var names []string
	for rows.Next() {
		var n string
		if err := rows.Scan(&n); err != nil {
			return nil, err
		}
		names = append(names, n)
	}
	return names, rows.Err()
}

// contains 判断切片是否含某字符串。
func contains(s []string, v string) bool {
	for _, x := range s {
		if x == v {
			return true
		}
	}
	return false
}
