// 应用入口。
//
// 痛点③修复要点：
//   - 显式引入 CJK 字体栈样式（styles/index.css）；
//   - 使用 React Router 而非散落 session_state，刷新可从 URL 恢复；
//   - 根节点 lang=zh-CN（已在 index.html 设置），保证字体回退与读音正确。
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
