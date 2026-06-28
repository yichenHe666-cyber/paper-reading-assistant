// 核动力科研牛马 v2 — Go 后端入口。
//
// 文件概述：main.go 是后端二进制的启动点，串联各层：
//   1. config.Load：加载配置并绝对化数据路径（痛点②修复核心）；
//   2. store.Open + Migrate：打开 SQLite（绝对路径）并建表；
//   3. ImportSeedPapers：导入人工精选种子论文（幂等，重启不重复产生数据）；
//   4. server.New + Run：装配 gin 路由并启动 HTTP 服务（带优雅关闭）。
//
// 启动后访问 GET /api/health 应返回 data_dir 绝对路径——这是 M1 验收点。
// 退出路径：Run 收到 SIGINT/SIGTERM 返回 nil 后，执行 PRAGMA wal_checkpoint(TRUNCATE)
// 再 defer db.Close()，确保 -wal 文件内容合并回主库，重启不丢数据（痛点②根治的收尾环）。
package main

import (
	"database/sql"
	"log"
	"os"

	"nuclear-ox-v2/backend/internal/config"
	"nuclear-ox-v2/backend/internal/paper"
	"nuclear-ox-v2/backend/internal/server"
	"nuclear-ox-v2/backend/internal/store"
)

func main() {
	// 1. 加载配置：路径绝对化 + 启动校验（缺 API key 等 fail-fast）
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("配置加载失败: %v", err)
	}

	// 2. 打开数据库（路径已绝对化，重启不变）并迁移 schema
	db, err := store.Open(cfg.DBPath)
	if err != nil {
		log.Fatalf("打开数据库失败: %v", err)
	}
	defer db.Close()
	if err := store.Migrate(db); err != nil {
		// log.Fatalf 会跳过 defer db.Close，故手动关闭再退出，避免句柄泄漏与 -wal 残留
		log.Printf("数据库迁移失败: %v", err)
		_ = db.Close()
		os.Exit(1)
	}

	// 3. 导入种子论文（幂等，重启不重复产生数据；文件缺失仅告警不阻断启动）
	importSeedPapers(cfg, db)

	// 4. 装配并启动 HTTP 服务
	srv := server.New(cfg, db)
	log.Printf("=== 核动力科研牛马 v2 启动 ===")
	log.Printf("监听: http://%s:%d", cfg.Server.Host, cfg.Server.Port)
	log.Printf("数据目录: %s", cfg.DataDir)
	log.Printf("数据库:   %s", cfg.DBPath)
	log.Printf("LLM:      provider=%s model=%s", cfg.LLM.Provider, cfg.LLM.Model)
	log.Printf("健康检查: GET /api/health")

	// Run 在收到 SIGINT/SIGTERM 后优雅关闭返回 nil；
	// 失败时用 log.Fatalf 会跳过 defer db.Close，故仅启动期 fatal，运行期错误走正常退出
	if err := srv.Run(); err != nil {
		log.Printf("服务退出: %v", err)
	}
	// 优雅关闭后、defer db.Close 前，显式 WAL checkpoint(TRUNCATE)：
	// 将 -wal 文件内容合并回主库并截断 -wal，避免重启后读取不到最新数据。
	// Go 与 Rust core 共享同一 SQLite 文件，Go 退出时的 checkpoint 是数据落盘的关键。
	if _, err := db.Exec("PRAGMA wal_checkpoint(TRUNCATE);"); err != nil {
		log.Printf("[db] [WARN] WAL checkpoint 失败: %v", err)
	}
}

// importSeedPapers 加载种子清单并导入数据库。
// 路径为空（未配置 SEED_PAPERS_PATH）时跳过；文件不存在或解析失败仅告警，不阻断启动。
// 幂等：基于稳定 id 的 ON CONFLICT，重启重复导入不产生重复行、不覆盖阅读进度。
func importSeedPapers(cfg *config.Config, db *sql.DB) {
	path := cfg.PaperSource.SeedPapersPath
	if path == "" {
		return
	}
	seeds, err := paper.LoadSeedPapers(path)
	if err != nil {
		log.Printf("[seed] [WARN] 加载种子清单失败（跳过）: %v", err)
		return
	}
	repo := paper.NewRepository(db)
	imported, skipped, failed, err := paper.ImportSeedPapers(repo, seeds)
	if err != nil {
		log.Printf("[seed] [WARN] 导入种子论文失败: %v", err)
		return
	}
	log.Printf("[seed] [INFO] 种子论文导入: imported=%d skipped=%d failed=%d (清单共 %d 篇)",
		imported, skipped, failed, len(seeds))
}
