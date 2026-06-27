// Package config 负责加载与校验应用配置。
//
// 文件概述：config.go 定义全局配置结构 Config，提供 Load()（加载）、resolvePaths()（路径绝对化）
// 与 Validate()（启动校验）。
//
// 关键设计（修复"重启后论文丢失"痛点，见 spec §4.2）：
// 旧 Python 版的数据库路径是相对路径 "data/reading_assistant.db"，引擎按进程 cwd 解析，
// 导致开机自启/快捷方式/IDE 运行时 cwd 一变就打开全新空库、旧数据被孤立。
// 本包将所有数据路径统一置于 DataDir 下，并强制解析为绝对路径，基准为：
//   1. 环境变量 NRO_DATA_DIR（最高优先级，便于 Docker 卷挂载）；
//   2. 可执行文件同级 data 目录（默认，单机绿色部署）；
//   3. 用户主目录下 ~/.nuclear-research-ox（兜底）。
// 从根本上消除对进程 cwd 的隐式依赖。
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Config 是应用全局配置。Load() 返回后，所有路径字段均为绝对路径。
type Config struct {
	DataDir   string // 数据根目录（绝对路径）——数据库/PDF/日志/备份都置于其下
	DBPath    string // SQLite 数据库文件路径（绝对路径）
	LogDir    string // 日志目录（绝对路径）
	BackupDir string // 备份目录（绝对路径）

	Server  ServerConfig  // HTTP 服务配置
	LLM     LLMConfig     // LLM provider 配置
	GitHub  GitHubConfig  // GitHub 数据源配置
	Core    CoreConfig    // Rust core 服务配置（向量化/记忆/梦境，spec §5）
}

// ServerConfig 描述 HTTP 监听参数。
type ServerConfig struct {
	Host string // 监听地址，默认 0.0.0.0
	Port int    // 监听端口，默认 8000
}

// LLMConfig 描述 LLM provider 配置。支持 ollama / deepseek / openai-compat。
type LLMConfig struct {
	Provider       string  // provider 标识：ollama | deepseek | openai-compat
	APIBase        string  // OpenAI 兼容 API 基址
	APIKey         string  // API 密钥（ollama 可空）
	Model          string  // 模型名，如 deepseek-chat
	MaxTokens      int     // 单次最大 token
	Temperature    float64 // 生成温度
	Timeout        float64 // 请求超时（秒）
	OllamaURL      string  // Ollama 本地服务地址
	DailyBudgetUSD float64 // 每日 LLM 预算上限（美元）
}

// GitHubConfig 描述论文数据源（Papers We Love 仓库）配置。
type GitHubConfig struct {
	Token       string // GitHub Personal Access Token（空则匿名访问，受 60/hour 限流）
	DefaultRepo string // 默认同步仓库，格式 "owner/repo"，如 papers-we-love/papers-we-love
}

// CoreConfig 描述 Rust core 服务（向量化/记忆引擎/梦境整合）的连接配置。
// spec §2.1：Go 后端通过 localhost HTTP 调用 Rust core，core 不暴露公网端口。
type CoreConfig struct {
	BaseURL string  // Rust core HTTP 基址，默认 http://127.0.0.1:8788
	Timeout float64 // 请求超时（秒），梦境整合较慢，默认 60
}

// Load 从环境变量加载配置，绝对化路径并做启动校验。
// 失败时返回错误，由调用方 fail-fast（而非带到运行时才 401）。
func Load() (*Config, error) {
	cfg := &Config{
		// NRO_DATA_DIR 为空时由 resolvePaths() 填充默认值
		DataDir: getEnv("NRO_DATA_DIR", ""),
		Server: ServerConfig{
			Host: getEnv("SERVER_HOST", "0.0.0.0"),
			Port: getEnvInt("SERVER_PORT", 8000),
		},
		LLM: LLMConfig{
			Provider:       getEnv("LLM_PROVIDER", "deepseek"),
			APIBase:        getEnv("LLM_API_BASE", "https://api.deepseek.com/v1"),
			APIKey:         getEnv("LLM_API_KEY", ""),
			Model:          getEnv("LLM_MODEL", "deepseek-chat"),
			MaxTokens:      getEnvInt("LLM_MAX_TOKENS", 4096),
			Temperature:    getEnvFloat("LLM_TEMPERATURE", 0.3),
			Timeout:        getEnvFloat("LLM_TIMEOUT", 120.0),
			OllamaURL:      getEnv("OLLAMA_BASE_URL", "http://localhost:11434"),
			DailyBudgetUSD: getEnvFloat("DAILY_LLM_BUDGET_USD", 3.0),
		},
		GitHub: GitHubConfig{
			Token:       getEnv("GITHUB_TOKEN", ""),
			DefaultRepo: getEnv("DEFAULT_GITHUB_REPO", "papers-we-love/papers-we-love"),
		},
		Core: CoreConfig{
			BaseURL: getEnv("CORE_BASE_URL", "http://127.0.0.1:8788"),
			Timeout: getEnvFloat("CORE_TIMEOUT", 60.0),
		},
	}
	// 路径绝对化（痛点②修复核心）
	if err := cfg.resolvePaths(); err != nil {
		return nil, err
	}
	// 启动校验（避免运行时才暴露配置错误）
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

// resolvePaths 将数据目录解析为绝对路径，并派生 db/logs/backups 子目录。
// 优先级见包注释。这是修复"重启数据丢失"的核心逻辑。
func (c *Config) resolvePaths() error {
	// 若未显式指定 DataDir，取默认值
	if c.DataDir == "" {
		exePath, err := os.Executable()
		if err == nil {
			// 默认：可执行文件同级 data 目录（绿色单机部署）
			c.DataDir = filepath.Join(filepath.Dir(exePath), "data")
		} else {
			// 兜底：用户主目录
			home, _ := os.UserHomeDir()
			c.DataDir = filepath.Join(home, ".nuclear-research-ox")
		}
	}
	// 若为相对路径，基于可执行文件目录解析为绝对路径（不再依赖 cwd）
	if !filepath.IsAbs(c.DataDir) {
		exePath, err := os.Executable()
		if err != nil {
			return fmt.Errorf("无法获取可执行文件路径以解析相对数据目录: %w", err)
		}
		c.DataDir = filepath.Join(filepath.Dir(exePath), c.DataDir)
	}
	c.DataDir = filepath.Clean(c.DataDir)

	// 派生子路径（全部绝对路径）
	c.DBPath = filepath.Join(c.DataDir, "db", "reading_assistant.db")
	c.LogDir = filepath.Join(c.DataDir, "logs")
	c.BackupDir = filepath.Join(c.DataDir, "backups")

	// 确保目录存在
	for _, dir := range []string{c.DataDir, filepath.Dir(c.DBPath), c.LogDir, c.BackupDir} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return fmt.Errorf("创建数据目录 %s 失败: %w", dir, err)
		}
	}
	return nil
}

// Validate 校验关键配置，缺失则返回明确错误。
// 注意：ollama 走本地无需 API key，予以豁免；其余 provider 缺 key 直接报错并指引。
func (c *Config) Validate() error {
	if c.LLM.Provider != "ollama" && strings.TrimSpace(c.LLM.APIKey) == "" {
		return fmt.Errorf("LLM_API_KEY 未配置（provider=%s）；请在 .env 中设置 LLM_API_KEY，或改用 LLM_PROVIDER=ollama 走本地模型", c.LLM.Provider)
	}
	return nil
}

// --- 环境变量读取辅助函数 ---

// getEnv 读取字符串环境变量，缺失时返回 def。
func getEnv(key, def string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return def
}

// getEnvInt 读取整型环境变量，缺失或非法时返回 def。
func getEnvInt(key string, def int) int {
	if v, ok := os.LookupEnv(key); ok {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

// getEnvFloat 读取浮点环境变量，缺失或非法时返回 def。
func getEnvFloat(key string, def float64) float64 {
	if v, ok := os.LookupEnv(key); ok {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}
