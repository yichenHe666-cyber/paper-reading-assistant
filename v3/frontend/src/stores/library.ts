// 论文与主题状态。
import { create } from 'zustand'
import type { Paper, Topic } from '@/api'
import { listTopics as apiListTopics, listPapers as apiListPapers } from '@/api'

interface LibraryState {
  topics: Topic[]
  papers: Paper[]
  topicsLoading: boolean
  papersLoading: boolean
  selectedTopicId: string | null

  loadTopics: () => Promise<void>
  selectTopic: (id: string | null) => Promise<void>
  reset: () => void
}

export const useLibraryStore = create<LibraryState>((set) => ({
  topics: [],
  papers: [],
  topicsLoading: false,
  papersLoading: false,
  selectedTopicId: null,

  loadTopics: async () => {
    set({ topicsLoading: true })
    try {
      const list = await apiListTopics()
      set({ topics: list, topicsLoading: false })
    } catch (err) {
      set({ topicsLoading: false })
      throw err
    }
  },

  selectTopic: async (id) => {
    if (id === null) {
      set({ selectedTopicId: null, papers: [] })
      return
    }
    set({ selectedTopicId: id, papersLoading: true })
    try {
      const list = await apiListPapers(id)
      set({ papers: list, papersLoading: false })
    } catch (err) {
      set({ papersLoading: false })
      throw err
    }
  },

  reset: () => set({ topics: [], papers: [], selectedTopicId: null }),
}))
