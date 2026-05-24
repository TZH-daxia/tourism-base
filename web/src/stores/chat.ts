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

export type AuthMode = 'member' | 'guest'

const STORAGE_KEYS: Record<AuthMode, { sessions: string; current: string; rag: string }> = {
  member: {
    sessions: 'tourism_sessions',
    current: 'tourism_currentId',
    rag: 'tourism_rag',
  },
  guest: {
    sessions: 'tourism_guest_sessions',
    current: 'tourism_guest_currentId',
    rag: 'tourism_guest_rag',
  },
}

const FALLBACK_QUICK_PROMPTS = [
  '三亚亲子四日游怎么安排更轻松？',
  '杭州两天一夜，西湖和茶园怎么串起来？',
  '云南第一次去，昆明大理丽江怎么取舍？',
  '成都夜游、美食和博物馆路线推荐',
]

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<Session[]>([])
  const currentId = ref<string>('')
  const loading = ref(false)
  const ragEnabled = ref(true)
  const recommendationCards = ref<RecommendationCard[]>([])
  const quickPrompts = ref<string[]>([])
  const authMode = ref<AuthMode>('member')

  let abortCtrl: AbortController | null = null

  function hasVisibleContent(value: string) {
    return Boolean(value && value.trim())
  }

  const currentSession = computed(() => sessions.value.find(item => item.session_id === currentId.value))
  const currentMessages = computed(() => currentSession.value?.messages || [])

  function getStorage(mode = authMode.value) {
    return mode === 'guest' ? sessionStorage : localStorage
  }

  function getStorageKeys(mode = authMode.value) {
    return STORAGE_KEYS[mode]
  }

  function readStoredSessions(mode = authMode.value) {
    const storage = getStorage(mode)
    const keys = getStorageKeys(mode)
    try {
      sessions.value = JSON.parse(storage.getItem(keys.sessions) || '[]')
    } catch {
      sessions.value = []
    }
    currentId.value = storage.getItem(keys.current) || ''
    ragEnabled.value = storage.getItem(keys.rag) !== '0'
  }

  function clearPersistedState(mode = authMode.value) {
    const storage = getStorage(mode)
    const keys = getStorageKeys(mode)
    storage.removeItem(keys.sessions)
    storage.removeItem(keys.current)
    storage.removeItem(keys.rag)
  }

  function initialize(mode: AuthMode, reset = false) {
    authMode.value = mode
    if (reset) {
      clearPersistedState(mode)
      sessions.value = []
      currentId.value = ''
      ragEnabled.value = mode === 'guest' ? false : true
      recommendationCards.value = []
      quickPrompts.value = []
      persist()
      return
    }
    readStoredSessions(mode)
    if (mode === 'guest' && !getStorage(mode).getItem(getStorageKeys(mode).rag)) {
      ragEnabled.value = false
      persist()
    }
  }

  function persist() {
    const storage = getStorage()
    const keys = getStorageKeys()
    storage.setItem(keys.sessions, JSON.stringify(sessions.value))
    storage.setItem(keys.current, currentId.value)
    storage.setItem(keys.rag, ragEnabled.value ? '1' : '0')
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
    if (backendId && authMode.value !== 'guest') await knowledgeApi.renameSession(backendId, nextTitle)
    session.title = nextTitle
    session.updated_at = new Date().toISOString()
    sortSessions()
    persist()
  }

  async function deleteSession(id: string) {
    const session = sessions.value.find(item => item.session_id === id)
    const backendId = session ? getBackendSid(session) : undefined
    if (backendId && authMode.value !== 'guest') await knowledgeApi.deleteSession(backendId)
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
      if (!quickPrompts.value.length) {
        quickPrompts.value = [...FALLBACK_QUICK_PROMPTS]
      }
    } catch {
      recommendationCards.value = []
      quickPrompts.value = [...FALLBACK_QUICK_PROMPTS]
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
    if (authMode.value === 'guest') {
      persist()
      return
    }
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
    const historyPayload = session.messages
      .filter(message => !message.pending && Boolean(message.content))
      .map(message => ({ role: message.role, content: message.content }))
      .slice(-8)
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
      for await (const chunk of knowledgeApi.ragChatStream(
        text,
        getBackendSid(session),
        abortCtrl.signal,
        ragEnabled.value,
        authMode.value === 'guest',
        [...historyPayload, { role: 'user', content: text }],
      )) {
        const last = session.messages[session.messages.length - 1]
        if (!last || last.role !== 'assistant') continue
        if (chunk.type === 'token' && chunk.token) {
          const hadVisibleContent = hasVisibleContent(fullContent)
          fullContent += chunk.token
          if (!hadVisibleContent && hasVisibleContent(fullContent)) {
            last.thinkingTime = Math.round((Date.now() - startedAt) / 100) / 10
          }
          last.content = fullContent
          ragReferenced = ragReferenced || Boolean(chunk.ragReferenced)
          if (chunk.sessionId && authMode.value !== 'guest' && !session.backend_id) {
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
          if (!fullContent && !last.thinkingTime) {
            last.thinkingTime = Math.round((Date.now() - startedAt) / 100) / 10
          }
          if (chunk.recommendations?.length) {
            quickPrompts.value = chunk.recommendations.slice(0, 3)
          }
          if (chunk.sessionId && authMode.value !== 'guest' && !session.backend_id) {
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
            if (!last.thinkingTime) {
              last.thinkingTime = Math.round((Date.now() - startedAt) / 100) / 10
            }
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
      if (authMode.value !== 'guest') await refreshSessions()
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
    if (authMode.value === 'guest') return
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

  function handleLogoutCleanup() {
    if (authMode.value === 'guest') {
      clearPersistedState('guest')
      sessions.value = []
      currentId.value = ''
      ragEnabled.value = false
      recommendationCards.value = []
      quickPrompts.value = []
      return
    }

    if (abortCtrl) {
      abortCtrl.abort()
      abortCtrl = null
    }
    loading.value = false
  }

  return {
    authMode,
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
    initialize,
    clearPersistedState,
    handleLogoutCleanup,
    sendMessage,
    stopGeneration,
    loadHistory,
    persist,
  }
})
