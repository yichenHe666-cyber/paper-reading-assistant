// 全局错误边界：捕获子组件渲染期异常，避免整应用白屏。
//
// spec §4.3 要求"杜绝脚本注入导致的白屏"；Markdown 渲染、JSON 解析等
// 任意子组件抛错时，ErrorBoundary 拦截并展示可恢复的 fallback，
// 而非让整棵 React 树崩溃。用户可点"重置"回到稳定状态。
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  message: string
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, message: '' }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || '未知渲染错误' }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 仅控制台记录，不上报（首期无监控后端）
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] 渲染异常:', error, info.componentStack)
  }

  handleReset = () => {
    this.setState({ hasError: false, message: '' })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
          <h2 className="text-lg font-semibold text-red-600">页面渲染出错</h2>
          <p className="max-w-md text-sm text-brand-700">
            {this.state.message}
          </p>
          <button
            type="button"
            onClick={this.handleReset}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm text-white hover:bg-brand-600"
          >
            重置并重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
