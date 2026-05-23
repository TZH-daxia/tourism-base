import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { knowledgeApi, type ChatImage, type ChatSessionSummary, type ChatSource, type RecommendationCard } from '../api/knowledge'

export interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  images?: ChatImage[]
  sources?: ChatSource[]
  thinkingTime?: number
  pending?: boolean
  ragReferenced?: boolean
  stopped?: boolean
}

export interface Session {
  session_id: string
  backend_id: string
  title: string
  messages: Message[]
  updated_at: string
  created_at?: string
  message_count?: number
  history_loaded?: boolean
}

const LS_SESSIONS = 'tourism_sessions'
const LS_CURRENT = 'tourism_currentId'
const LS_RAG = 'tourism_rag'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<Session[]>(JSON.parse(localStorage.getItem(LS_SESSIONS) || '[]'))
  const currentId = ref<string>(localStorage.getItem(LS_CURRENT) || '')
  const loading = ref(false)
  const ragEnabled = ref(localStorage.getItem(LS_RAG) !== '0')
  const recommendationCards = ref<RecommendationCard[]>([])
  const quickPrompts = ref<string[]>([])

  let abortCtrl: AbortController | null = null

  const currentSession = computed(() => sessions.value.find(item => item.session_id === currentId.value))
  const currentMessages = computed(() => currentSession.value?.messages || [])

  function persist() {
    localStorage.setItem(LS_SESSIONS, JSON.stringify(sessions.value))
    localStorage.setItem(LS_CURRENT, currentId.value)
    localStorage.setItem(LS_RAG, ragEnabled.value ? '1' : '0')
  }

  function getBackendSid(session: Session): string | undefined {
    if (session.backend_id) return session.backend_id
    if (session.session_id.startsWith('local_')) return undefined
    return session.session_id
  }

  function sortSessions() {
    sessions.value.sort((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at))
  }

  function createSession() {
    const now = new Date().toISOString()
    const id = `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    sessions.value.unshift({
      session_id: id,
      backend_id: '',
      title: '',
      messages: [],
      updated_at: now,
      created_at: now,
      message_count: 0,
      history_loaded: true,
    })
    currentId.value = id
    persist()
  }

  function switchSession(id: string) {
    currentId.value = id
    persist()
  }

  async function renameSession(id: string, title: string) {
    const session = sessions.value.find(item => item.session_id === id)
    if (!session) return
    const nextTitle = title.trim()
    const backendId = getBackendSid(session)
    if (backendId) await knowledgeApi.renameSession(backendId, nextTitle)
    session.title = nextTitle
    session.updated_at = new Date().toISOString()
    sortSessions()
    persist()
  }

  async function deleteSession(id: string) {
    const session = sessions.value.find(item => item.session_id === id)
    const backendId = session ? getBackendSid(session) : undefined
    if (backendId) await knowledgeApi.deleteSession(backendId)
    sessions.value = sessions.value.filter(item => item.session_id !== id)
    if (currentId.value === id) currentId.value = sessions.value[0]?.session_id || ''
    persist()
  }

  async function fetchRecommendations() {
    try {
      recommendationCards.value = await knowledgeApi.getRecommendations()
      if (!quickPrompts.value.length && recommendationCards.value[0]?.queries?.length) {
        quickPrompts.value = recommendationCards.value[0].queries.slice(0, 3)
      }
    } catch {
      recommendationCards.value = []
    }
  }

  function mergeBackendSessions(items: ChatSessionSummary[]) {
    const localOnly = sessions.value.filter(item => !getBackendSid(item))
    const localByBackendId = new Map<string, Session>()
    for (const session of sessions.value) {
      const backendId = getBackendSid(session)
      if (backendId) localByBackendId.set(backendId, session)
    }

    const mergedRemote: Session[] = items.map(item => {
      const existing = localByBackendId.get(item.session_id)
      return {
        session_id: existing?.session_id || item.session_id,
        backend_id: item.session_id,
        title: item.title || existing?.title || '',
        messages: existing?.messages || [],
        updated_at: item.updated_at,
        created_at: item.created_at,
        message_count: item.message_count,
        history_loaded: existing?.history_loaded || false,
      }
    })

    sessions.value = [...localOnly, ...mergedRemote]
    sortSessions()

    if (!sessions.value.find(item => item.session_id === currentId.value)) {
      currentId.value = sessions.value[0]?.session_id || ''
    }
    persist()
  }

  async function refreshSessions() {
    try {
      const data = await knowledgeApi.getSessions()
      mergeBackendSessions(data)
    } catch {
      persist()
    }
  }

  async function sendMessage(text: string) {
    if (!text.trim() || loading.value) return
    if (abortCtrl) abortCtrl.abort()
    let session = currentSession.value
    if (!session) {
      createSession()
      session = currentSession.value
    }
    if (!session) return

    abortCtrl = new AbortController()
    loading.value = true
    const startedAt = Date.now()
    const now = new Date().toISOString()
    const userMessage: Message = { role: 'user', content: text, timestamp: now }
    const assistantMessage: Message = {
      role: 'assistant',
      content: '',
      timestamp: now,
      images: [],
      sources: [],
      thinkingTime: 0,
      pending: true,
    }
    session.messages.push(userMessage, assistantMessage)
    session.updated_at = new Date().toISOString()
    session.message_count = session.messages.length
    session.history_loaded = true
    sortSessions()
    persist()

    let fullContent = ''
    let ragReferenced = false
    try {
      for await (const chunk of knowledgeApi.ragChatStream(text, getBackendSid(session), abortCtrl.signal, ragEnabled.value)) {
        const last = session.messages[session.messages.length - 1]
        if (!last || last.role !== 'assistant') continue
        if (chunk.type === 'token' && chunk.token) {
          if (!fullContent) last.thinkingTime = Math.round((Date.now() - startedAt) / 100) / 10
          fullContent += chunk.token
          last.content = fullContent
          ragReferenced = ragReferenced || Boolean(chunk.ragReferenced)
          if (chunk.sessionId && !session.backend_id) {
            session.backend_id = chunk.sessionId
            session.session_id = chunk.sessionId
            currentId.value = chunk.sessionId
          }
        } else if (chunk.type === 'done') {
          last.content = fullContent || last.content
          last.pending = false
          last.ragReferenced = ragReferenced || Boolean(chunk.ragReferenced)
          last.images = chunk.images || last.images || []
          last.sources = chunk.sources || last.sources || []
          last.thinkingTime = Math.round((Date.now() - startedAt) / 100) / 10
          if (chunk.recommendations?.length) {
            quickPrompts.value = chunk.recommendations.slice(0, 3)
          }
          if (chunk.sessionId && !session.backend_id) {
            session.backend_id = chunk.sessionId
            session.session_id = chunk.sessionId
            currentId.value = chunk.sessionId
          }
          session.updated_at = new Date().toISOString()
          session.message_count = session.messages.length
          sortSessions()
          persist()
        } else if (chunk.type === 'error') {
          last.pending = false
          last.content = fullContent || chunk.error || '[错误] 请求失败，请重试'
          session.message_count = session.messages.length
        }
      }
    } catch (error: any) {
      const last = session.messages[session.messages.length - 1]
      if (last && last.role === 'assistant') {
        if (error?.name === 'AbortError') {
          if (fullContent || last.content) {
            last.stopped = true
            last.pending = false
            last.content = fullContent || last.content
            last.thinkingTime = Math.round((Date.now() - startedAt) / 100) / 10
          } else {
            session.messages.pop()
          }
        } else {
          last.pending = false
          last.content = fullContent || `[错误] ${error?.message || '请求失败，请重试'}`
        }
      }
    } finally {
      loading.value = false
      abortCtrl = null
      session.updated_at = new Date().toISOString()
      session.message_count = session.messages.length
      sortSessions()
      persist()
      await refreshSessions()
    }
  }

  function stopGeneration() {
    if (abortCtrl) {
      abortCtrl.abort()
      abortCtrl = null
    }
    loading.value = false
    const session = currentSession.value
    const last = session?.messages.at(-1)
    if (last?.role === 'assistant') {
      if (!last.content) {
        session?.messages.pop()
      } else {
        last.stopped = true
        last.pending = false
      }
    }
    if (session) {
      session.updated_at = new Date().toISOString()
      session.message_count = session.messages.length
      sortSessions()
      persist()
    }
  }

  async function loadHistory(sessionId: string) {
    const session = sessions.value.find(item => item.session_id === sessionId)
    if (!session) return
    const backendId = getBackendSid(session)
    if (!backendId) return
    try {
      const data = await knowledgeApi.getHistory(backendId)
      session.messages = data.messages.map(message => ({
        role: message.role,
        content: message.content,
        timestamp: message.timestamp || new Date().toISOString(),
        images: message.images || [],
        sources: message.sources || [],
        pending: false,
      }))
      session.message_count = session.messages.length
      session.history_loaded = true
      persist()
    } catch {
      // best effort
    }
  }

  return {
    sessions,
    currentId,
    loading,
    ragEnabled,
    currentSession,
    currentMessages,
    recommendationCards,
    quickPrompts,
    createSession,
    switchSession,
    renameSession,
    deleteSession,
    refreshSessions,
    fetchRecommendations,
    sendMessage,
    stopGeneration,
    loadHistory,
    persist,
  }
})
