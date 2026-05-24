export interface TaskTimelineItem {
  step: string
  progress: number
  status: string
  detail?: string
  timestamp?: string
}

export interface TaskStatus {
  task_id: string
  file_name: string
  status: string
  progress: number
  current_step: string
  error: string
  city?: string
  doc_type?: string
  product_id?: string
  suggested_queries?: string[]
  timeline?: TaskTimelineItem[]
  stats?: Record<string, unknown>
}

export interface RecommendationCard {
  city: string
  product_id: string
  doc_types: string[]
  queries: string[]
}

export interface RuntimeModelSettings {
  api_key: string
  base_url: string
  model: string
  is_default: boolean
  vision_required: boolean
  warning: string
}

export interface RuntimeModelTestResult {
  ok: boolean
  message: string
}

export interface KnowledgeUploadResponse {
  task_id: string
  file_name: string
  status: string
}

export interface ChatImage {
  url: string
  alt: string
  title?: string
  city?: string
  doc_type?: string
  source_file?: string
}

export interface ChatSource {
  file_name: string
  url?: string
  doc_type?: string
  city?: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  images?: ChatImage[]
  sources?: ChatSource[]
}

export interface ChatHistoryTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatSessionSummary {
  session_id: string
  title: string
  updated_at: string
  created_at: string
  message_count: number
}

export interface StreamChunk {
  type: 'token' | 'done' | 'error'
  token?: string
  sessionId?: string
  sources?: ChatSource[]
  images?: ChatImage[]
  recommendations?: string[]
  ragReferenced?: boolean
  confirmAnswer?: boolean
  error?: string
}

export const knowledgeApi = {
  async upload(file: File): Promise<KnowledgeUploadResponse> {
    const fd = new FormData()
    fd.append('file', file)
    const resp = await fetch('/api/knowledge/upload', { method: 'POST', body: fd })
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || '上传失败')
    return resp.json()
  },

  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    const resp = await fetch(`/api/knowledge/status/${taskId}`)
    if (!resp.ok) throw new Error('获取任务状态失败')
    return resp.json()
  },

  async getTasks(params?: { search?: string; status?: string }): Promise<TaskStatus[]> {
    const qs = new URLSearchParams()
    if (params?.search) qs.set('search', params.search)
    if (params?.status) qs.set('status', params.status)
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    const resp = await fetch(`/api/knowledge/tasks${suffix}`)
    if (!resp.ok) throw new Error('获取任务列表失败')
    return resp.json()
  },

  async getRecommendations(): Promise<RecommendationCard[]> {
    const resp = await fetch('/api/knowledge/recommendations')
    if (!resp.ok) throw new Error('获取推荐城市失败')
    return resp.json()
  },

  async getRuntimeModelSettings(): Promise<RuntimeModelSettings> {
    const resp = await fetch('/api/knowledge/runtime-model-settings')
    if (!resp.ok) throw new Error('获取模型设置失败')
    return resp.json()
  },

  async updateRuntimeModelSettings(payload: {
    api_key: string
    base_url: string
    model: string
  }): Promise<RuntimeModelSettings> {
    const resp = await fetch('/api/knowledge/runtime-model-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || '保存模型设置失败')
    return resp.json()
  },

  async resetRuntimeModelSettings(): Promise<RuntimeModelSettings> {
    const resp = await fetch('/api/knowledge/runtime-model-settings', { method: 'DELETE' })
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || '恢复默认模型失败')
    return resp.json()
  },

  async testRuntimeModelSettings(payload: {
    api_key: string
    base_url: string
    model: string
  }): Promise<RuntimeModelTestResult> {
    const resp = await fetch('/api/knowledge/runtime-model-settings/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || '模型测试失败')
    return resp.json()
  },

  async deleteTask(taskId: string): Promise<void> {
    const resp = await fetch(`/api/knowledge/task/${taskId}`, { method: 'DELETE' })
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || '删除文件失败')
  },

  async deleteSession(sessionId: string): Promise<void> {
    const resp = await fetch(`/api/knowledge/chat/${sessionId}`, { method: 'DELETE' })
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || '删除会话失败')
  },

  async renameSession(sessionId: string, title: string): Promise<void> {
    const resp = await fetch(`/api/knowledge/chat/${sessionId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || '重命名会话失败')
  },

  async getHistory(sessionId: string): Promise<{ session_id: string; messages: ChatMessage[]; total: number }> {
    const resp = await fetch(`/api/knowledge/chat/${sessionId}/history`)
    if (!resp.ok) throw new Error('获取历史失败')
    return resp.json()
  },

  async getSessions(): Promise<ChatSessionSummary[]> {
    const resp = await fetch('/api/knowledge/chat/sessions')
    if (!resp.ok) throw new Error('获取会话列表失败')
    return resp.json()
  },

  async *ragChatStream(
    message: string,
    sessionId: string | undefined,
    signal: AbortSignal,
    ragEnabled = true,
    guestMode = false,
    history: ChatHistoryTurn[] = [],
  ): AsyncGenerator<StreamChunk> {
    const resp = await fetch('/api/knowledge/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        session_id: sessionId || null,
        rag_enabled: ragEnabled,
        guest_mode: guestMode,
        history,
      }),
      signal,
    })

    if (!resp.ok) {
      yield { type: 'error', error: `HTTP ${resp.status}` }
      return
    }

    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const parts = buf.split('\n')
      buf = parts.pop() || ''

      for (const line of parts) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data: ')) continue
        try {
          const payload = JSON.parse(trimmed.slice(6))
          if (payload.error) {
            yield { type: 'error', error: payload.error, sessionId: payload.session_id }
            return
          }
          if (payload.done) {
            yield {
              type: 'done',
              sessionId: payload.session_id,
              sources: payload.sources || [],
              images: payload.images || [],
              recommendations: payload.recommendations || [],
              ragReferenced: payload.rag_referenced,
            }
            return
          }
          if (payload.token) {
            yield {
              type: 'token',
              token: payload.token,
              sessionId: payload.session_id,
              sources: payload.sources || [],
              images: payload.images || [],
              ragReferenced: payload.rag_referenced,
              confirmAnswer: payload.confirm_answer,
            }
          }
        } catch {
          // ignore malformed sse line
        }
      }
    }

    yield { type: 'done' }
  },
}
