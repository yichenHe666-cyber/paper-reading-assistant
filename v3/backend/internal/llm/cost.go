// Package llm 的成本追踪与持久化。
//
// 文件概述：cost.go 实现 CostRecorder 接口的数据库版本 DBRecorder：
//   - estimateCost：按 (provider, model) 价格表估算单次调用美元成本；
//   - Record：将 provider/model/用量/成本写入 llm_calls 表，供前端成本监控展示。
//
// 价格表维护约定：
//   LLM 价格频繁调整，此处仅放常用 provider 的参考价（每 1M token，美元）。
//   未知模型返回 0 成本（不阻断调用，仅记录用量），实际计费以 provider 账单为准。
//   新增模型时同步更新 priceTable，并在注释标注来源与生效日期。
package llm

import (
	"database/sql"
	"fmt"
	"sync/atomic"
	"time"
)

// pricePerMillion 是每 1M（1,000,000）token 的美元价格。
// key 为 "provider/model" 全小写，与 provider.go 的 capabilityMatrix 对齐。
//
// 参考来源（截至 2025 年公开定价，仅供估算）：
//   - DeepSeek-chat：输入 $0.27 / 输出 $1.10 每 1M（缓存未命中）
//   - DeepSeek-reasoner：输入 $0.55 / 输出 $2.19 每 1M
//   - Ollama：本地部署，成本记 0
// 实际计费请以 provider 官方账单为准；本表仅用于预算预警与展示。
var pricePerMillion = map[string]struct{ In, Out float64 }{
	"deepseek/deepseek-chat":     {In: 0.27, Out: 1.10},
	"deepseek/deepseek-v4-flash": {In: 0.27, Out: 1.10},
	"deepseek/deepseek-reasoner": {In: 0.55, Out: 2.19},
	"deepseek/deepseek-v4-pro":   {In: 0.55, Out: 2.19},
	// ollama 本地：0 成本（key 不存在则 estimateCost 返回 0，无需显式登记）
}

// callCounter 是 llm_calls.id 的本地自增计数，配合时间戳保证唯一。
// 进程级即可，id 仅用于主键，不要求全局跨进程唯一（数据库内已够用）。
var callCounter uint64

// DBRecorder 是写入 SQLite llm_calls 表的 CostRecorder 实现。
type DBRecorder struct {
	db *sql.DB
}

// NewDBRecorder 构造一个基于已打开数据库的记录器。
// db 应为 store.Open 返回的连接（已启用 WAL）。
func NewDBRecorder(db *sql.DB) *DBRecorder {
	return &DBRecorder{db: db}
}

// Record 实现 CostRecorder 接口：估算成本并写入 llm_calls 表。
//
// 失败时返回 error，但 client.go 调用处会忽略（成本记录失败不影响主流程）。
// id 用 "时间戳纳秒-自增计数" 生成，进程内唯一性足够。
func (r *DBRecorder) Record(provider, model string, usage Usage) error {
	cost := estimateCost(provider, model, usage)
	id := fmt.Sprintf("call-%d-%d", time.Now().UnixNano(), atomic.AddUint64(&callCounter, 1))

	_, err := r.db.Exec(
		`INSERT INTO llm_calls(id, provider, model, prompt_tokens, completion_tokens, total_tokens, cost_usd)
		 VALUES(?, ?, ?, ?, ?, ?, ?)`,
		id, provider, model,
		usage.PromptTokens, usage.CompletionTokens, usage.TotalTokens, cost,
	)
	if err != nil {
		return fmt.Errorf("写入 llm_calls 失败: %w", err)
	}
	return nil
}

// estimateCost 按 (provider, model) 价格表估算美元成本。
// 未知模型返回 0（安全降级，不阻断记录）。
func estimateCost(provider, model string, usage Usage) float64 {
	key := normalizeKey(provider, model)
	price, ok := pricePerMillion[key]
	if !ok {
		// 未知模型：成本记 0，但仍记录用量（usage），便于事后核对
		return 0
	}
	// 成本 = 输入token * 输入单价 + 输出token * 输出单价（每 1M token 计价）
	in := float64(usage.PromptTokens) * price.In / 1_000_000
	out := float64(usage.CompletionTokens) * price.Out / 1_000_000
	return in + out
}
