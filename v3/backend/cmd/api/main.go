// 核动力科研牛马 v2 — Go 后端入口。
//
// 文件概述：main.go 是后端二进制的启动点，串联各层：
//   1. config.Load：加载配置并绝对化数据路径（痛点②修复核心）；
//   2. store.Open + Migrate：打开 SQLite（绝对路径）并建表；
//   3. paper.FindLegacyDBs + MigrateLegacyDB：尽力迁移旧版相对路径遗留库（找回历史数据）；
//   4. server.New + Run：装配 gin 路由并启动 HTTP 服务（带优雅关闭）。
//
// 启动后访问 GET /api/health 应返回 data_dir 绝对路径——这是 M1 验收点。
// 退出路径：Run 收到 SIGINT/SIGTERM 返回 nil 后，defer db.Close() 执行 WAL checkpoint，
// 数据落盘后再退出，避免 -wal 文件残留。
package main

import (
	"log"

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
		log.Fatalf("数据库迁移失败: %v", err)
	}

	// 3. 启动时尽力迁移旧库：找回散落在历史 cwd 的论文数据（痛点②业务层）
	repo := paper.NewRepository(db)
	for _, legacy := range paper.FindLegacyDBs(cfg.DBPath) {
		r, err := paper.MigrateLegacyDB(repo, legacy)
		if err != nil {
			log.Printf("[迁移] 旧库 %s 失败: %v", legacy, err)
			continue
		}
		log.Printf("[迁移] 已从旧库 %s 导入: 主题 %d, 论文 %d", legacy, r.TopicsMoved, r.PapersMoved)
	}

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
}
