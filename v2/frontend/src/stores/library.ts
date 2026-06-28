// 论文与数据源状态。
//
// v0.3.1 契约：用“数据源（Source）”替代旧的“主题（Topic）”。
// LibraryPage 按数据源筛选论文，syncSources 触发同步。
import { create } from 'zustand'
import type { Paper, Source, PaperFilter } from '@/api'
import { listSources as apiListSources, listPapers as apiListPapers } from '@/api'

interface LibraryState {
  sources: Source[]
  papers: Paper[]
  filter: PaperFilter
  sourcesLoading: boolean
  papersLoading: boolean

  loadSources: () => Promise<void>
  applyFilter: (filter: PaperFilter) => Promise<void>
  reset: () => void
}

export const useLibraryStore = create<LibraryState>((set) => ({
  sources: [],
  papers: [],
  filter: {},
  sourcesLoading: false,
  papersLoading: false,

  loadSources: async () => {
    set({ sourcesLoading: true })
    try {
      const list = await apiListSources()
      set({ sources: list, sourcesLoading: false })
    } catch (err) {
      set({ sourcesLoading: false })
      throw err
    }
  },

  applyFilter: async (filter) => {
    set({ filter, papersLoading: true })
    try {
      const resp = await apiListPapers(filter)
      set({ papers: resp.papers, papersLoading: false })
    } catch (err) {
      set({ papersLoading: false })
      throw err
    }
  },

  reset: () => set({ sources: [], papers: [], filter: {} }),
}))
