// vite.config.ts — Vite 构建配置。
//
// 痛点③修复要点：
//   - dev server 反向代理 /api → Go 后端，避免前端跨域与编码问题；
//   - 显式 charset=utf-8 由后端响应头保证，前端 fetch 不再依赖浏览器探测；
//   - 构建产物输出到 dist/，供 Go 后端内嵌或 nginx 托管。
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    // 代理 /api 到 Go 后端，避免 CORS 与编码探测；后端响应头显式声明 charset=utf-8
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // SSE 流式不能缓冲，关闭 proxy 默认 buffer
        ws: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    // 生产构建关闭 sourcemap：避免原始 TS 源码（含注释与业务逻辑）随产物
    // 发布给任意访问者，造成信息泄露。调试需要时改用本地 dev server。
    sourcemap: false,
    // 单文件体积警告阈值，便于发现依赖膨胀
    chunkSizeWarningLimit: 800,
  },
})
