/// <reference types="vite/client" />

// 显式声明 import.meta.env 字段，避免 TS 推断为 any。
interface ImportMetaEnv {
  readonly VITE_API_BASE: string // 可选，缺省走相对路径 /api（由 vite proxy 转发）
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
