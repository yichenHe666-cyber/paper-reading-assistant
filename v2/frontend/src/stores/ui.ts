// 全局 UI 状态：toast 通知、加载指示。
//
// 与持久化业务数据分离，避免无谓重渲染。
import { create } from 'zustand'

export interface Toast {
  id: string
  kind: 'info' | 'success' | 'error'
  message: string
}

interface UIState {
  toasts: Toast[]
  globalLoading: boolean
  pushToast: (kind: Toast['kind'], message: string) => void
  dismissToast: (id: string) => void
  setGlobalLoading: (v: boolean) => void
}

let toastSeq = 0

export const useUIStore = create<UIState>((set) => ({
  toasts: [],
  globalLoading: false,
  pushToast: (kind, message) => {
    const id = `t${++toastSeq}`
    set((s) => ({ toasts: [...s.toasts, { id, kind, message }] }))
    // 3.5s 自动消失
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, 3500)
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  setGlobalLoading: (v) => set({ globalLoading: v }),
}))
