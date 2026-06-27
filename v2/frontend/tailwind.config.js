/** @type {import('tailwindcss').Config} */
// Tailwind 配置。
//
// 痛点③修复要点：
//   - 显式 CJK 字体栈注入到 font-family，杜绝拉丁字体回退导致的中文方框；
//   - content 路径覆盖 src 全部 tsx，确保 purge 不漏；
//   - 关闭 preflight 与 base 的冲突由 React 接管。
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        // CJK 字体栈：macOS PingFang → Windows YaHei → Linux Noto CJK → Source Han → 兜底 sans-serif
        // 顺序很重要：系统优先匹配可用的，避免被拉丁字体截胡导致中文方框。
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          '"Noto Sans CJK SC"',
          '"Source Han Sans CN"',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
        mono: [
          '"JetBrains Mono"',
          '"SFMono-Regular"',
          'Menlo',
          'Consolas',
          '"Noto Sans Mono CJK SC"',
          'monospace',
        ],
      },
      colors: {
        // 主题色：深色科研工具风格
        brand: {
          50: '#f5f7fa',
          100: '#eaeef3',
          500: '#4a6fa5',
          600: '#3d5d8a',
          700: '#2f4a6e',
          900: '#1a2433',
        },
      },
    },
  },
  plugins: [],
}
