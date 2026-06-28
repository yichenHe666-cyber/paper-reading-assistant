// 论文库状态：多数据源（arXiv/OpenAlex/ACL/Company）AI 论文聚合。
//
// 负责：分页论文列表、筛选条件、数据源列表、同步与 AI 难度分类。
// 错误一律抛给调用方（页面层 catch 后 pushToast），store 内不做 UI 反馈。
import { create } from 'zustand'
import {
  classifyPaper as apiClassifyPaper,
  listPapers as apiListPapers,
  listSources as apiListSources,
  syncSources as apiSyncSources,
  type Paper,
  type PaperFilter,
  type Source,
  type SyncResult,
} from '@/api'

interface LibraryState {
  papers: Paper[]
  total: number // 满足当前筛选的总数
  page: number // 当前页（1-based）
  pageSize: number // 每页条数（默认 20）
  filter: PaperFilter // 当前筛选条件（不含 page/page_size，那俩单独存）
  loading: boolean // 论文列表加载中
  sources: Source[] // 数据源列表
  sourcesLoading: boolean
  syncing: boolean // 同步中
  classifying: boolean // AI 分类中

  loadPapers: () => Promise<void> // 用当前 filter+page+pageSize 调 listPapers
  setFilter: (f: Partial<PaperFilter>) => Promise<void> // 合并筛选条件并重置到第 1 页，重新加载
  setPage: (p: number) => Promise<void> // 切换页码，重新加载
  loadSources: () => Promise<void>
  syncAll: () => Promise<SyncResult[]> // 调 syncSources()，同步后刷新源列表与论文
  syncOne: (sourceId: string) => Promise<SyncResult[]>
  classifyAll: () => Promise<number> // 全量 AI 分类
  classifyOne: (paperId: string) => Promise<number>
  reset: () => void
}

export const useLibraryStore = create<LibraryState>((set, get) => ({
  papers: [],
  total: 0,
  page: 1,
  pageSize: 20,
  filter: {},
  loading: false,
  sources: [],
  sourcesLoading: false,
  syncing: false,
  classifying: false,

  loadPapers: async () => {
    set({ loading: true })
    try {
      const { filter, page, pageSize } = get()
      const resp = await apiListPapers({ ...filter, page, page_size: pageSize })
      set({ papers: resp.papers, total: resp.total, loading: false })
    } catch (err) {
      set({ loading: false })
      throw err
    }
  },

  setFilter: async (f) => {
    set({ filter: { ...get().filter, ...f }, page: 1 })
    await get().loadPapers()
  },

  setPage: async (p) => {
    set({ page: p })
    await get().loadPapers()
  },

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

  syncAll: async () => {
    set({ syncing: true })
    try {
      const { results } = await apiSyncSources()
      set({ syncing: false })
      await Promise.all([get().loadSources(), get().loadPapers()])
      return results
    } catch (err) {
      set({ syncing: false })
      throw err
    }
  },

  syncOne: async (sourceId) => {
    set({ syncing: true })
    try {
      const { results } = await apiSyncSources(sourceId)
      set({ syncing: false })
      await Promise.all([get().loadSources(), get().loadPapers()])
      return results
    } catch (err) {
      set({ syncing: false })
      throw err
    }
  },

  classifyAll: async () => {
    set({ classifying: true })
    try {
      const resp = await apiClassifyPaper()
      set({ classifying: false })
      await get().loadPapers()
      return resp.classified
    } catch (err) {
      set({ classifying: false })
      throw err
    }
  },

  classifyOne: async (paperId) => {
    set({ classifying: true })
    try {
      const resp = await apiClassifyPaper(paperId)
      set({ classifying: false })
      await get().loadPapers()
      return resp.classified
    } catch (err) {
      set({ classifying: false })
      throw err
    }
  },

  reset: () =>
    set({ papers: [], total: 0, page: 1, filter: {}, sources: [] }),
}))
