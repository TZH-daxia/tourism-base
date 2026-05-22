<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { knowledgeApi, type RuntimeModelSettings } from '../../api/knowledge'
import { useChatStore, type Message, type Session } from '../../stores/chat'

const props = defineProps<{ kbVersion: number }>()
const emit = defineEmits<{ 'open-kb': []; logout: [] }>()

const store = useChatStore()
const inputMessage = ref('')
const messagesContainer = ref<HTMLDivElement>()
const inputRef = ref<HTMLInputElement>()
const sessionGroupsRef = ref<HTMLDivElement>()
const openMenuId = ref('')
const deletingSessionId = ref('')
const copiedKey = ref('')
const showSettingsMenu = ref(false)
const showModelSettings = ref(false)
const settingsSaving = ref(false)
const settingsError = ref('')
const settingsSuccess = ref('')
const runtimeSettings = ref<RuntimeModelSettings>({
  api_key: '',
  base_url: '',
  model: '',
  vision_required: true,
  warning: '请优先使用支持视觉的模型，否则文档里的图片信息可能无法被正确理解。',
})
const liveNow = ref(Date.now())
let liveTimer: number | null = null

function focusInput() {
  nextTick(() => inputRef.value?.focus())
}

const hasMessages = computed(() => store.currentMessages.length > 0)

const groupedSessions = computed(() => {
  const groups: Record<string, typeof store.sessions> = { '今天': [], '近 7 天': [], '更早': [] }
  const now = Date.now()
  for (const session of [...store.sessions].sort((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at))) {
    const age = now - +new Date(session.updated_at)
    if (age < 24 * 3600 * 1000) groups['今天'].push(session)
    else if (age < 7 * 24 * 3600 * 1000) groups['近 7 天'].push(session)
    else groups['更早'].push(session)
  }
  return Object.entries(groups).filter(([, value]) => value.length)
})

function getTitle(session: { title: string; messages: { content: string }[] }) {
  if (session.title) return session.title
  return session.messages[0]?.content?.slice(0, 18) || '新的旅程'
}

function isAssistantPending(message: Message) {
  return message.role === 'assistant' && Boolean(message.pending)
}

function showWaitingSkeleton(message: Message) {
  return isAssistantPending(message) && !message.content
}

function displayThinkingTime(message: Message) {
  if (isAssistantPending(message)) {
    const startedAt = +new Date(message.timestamp)
    return Math.max(0, Math.round((liveNow.value - startedAt) / 100) / 10)
  }
  return message.thinkingTime ?? 0
}

function waitingLabel(message: Message) {
  const seconds = displayThinkingTime(message)
  return `思考中 ${seconds.toFixed(1)}s`
}

function escapeHtml(raw: string) {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderInlineMarkdown(line: string) {
  return line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

function isMarkdownTableSeparator(line: string) {
  return /^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*(?:\s*:?-{3,}:?\s*)?\|?\s*$/.test(line)
}

function splitMarkdownTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => renderInlineMarkdown(cell.trim()))
}

function renderMessageHtml(content: string) {
  const normalized = escapeHtml(content || '')
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()

  if (!normalized) return ''

  const blocks = normalized.split(/\n{2,}/)
  const htmlBlocks = blocks.map(block => {
    const lines = block.split('\n').map(line => line.trimEnd()).filter(Boolean)
    if (!lines.length) return ''

    if (lines.length >= 2 && lines[0].includes('|') && isMarkdownTableSeparator(lines[1])) {
      const headers = splitMarkdownTableRow(lines[0]).map(cell => `<th>${cell}</th>`).join('')
      const rows = lines
        .slice(2)
        .filter(line => line.includes('|'))
        .map(line => {
          const cells = splitMarkdownTableRow(line).map(cell => `<td>${cell}</td>`).join('')
          return `<tr>${cells}</tr>`
        })
        .join('')
      return `<div class="md-table-wrap"><table><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table></div>`
    }

    if (lines.every(line => /^[-*]\s+/.test(line))) {
      const items = lines.map(line => `<li>${renderInlineMarkdown(line.replace(/^[-*]\s+/, ''))}</li>`)
      return `<ul>${items.join('')}</ul>`
    }

    return lines
      .map(line => {
        if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)) return '<hr />'
        if (/^##\s+/.test(line)) return `<h3>${renderInlineMarkdown(line.replace(/^##\s+/, ''))}</h3>`
        if (/^#\s+/.test(line)) return `<h2>${renderInlineMarkdown(line.replace(/^#\s+/, ''))}</h2>`
        if (/^[-*]\s+/.test(line)) return `<p>${renderInlineMarkdown(line.replace(/^[-*]\s+/, '• '))}</p>`
        return `<p>${renderInlineMarkdown(line)}</p>`
      })
      .join('')
  })

  return htmlBlocks.join('')
}

async function send(message?: string) {
  const content = (message ?? inputMessage.value).trim()
  if (!content || store.loading) return
  inputMessage.value = ''
  await store.sendMessage(content)
  await nextTick()
  scrollToBottom()
  focusInput()
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function startNewChat() {
  store.createSession()
  openMenuId.value = ''
  focusInput()
}

async function useRecommendation(city: string, query: string) {
  if (!store.currentSession) startNewChat()
  await send(query || `${city}有什么好玩的？`)
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function formatDate(ts: string) {
  return new Date(ts).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

async function copyMessage(message: Message, index: number) {
  try {
    await navigator.clipboard.writeText(message.content)
    copiedKey.value = `${message.timestamp}_${index}`
    window.setTimeout(() => {
      if (copiedKey.value === `${message.timestamp}_${index}`) copiedKey.value = ''
    }, 1200)
  } catch {
    copiedKey.value = ''
  }
}

async function loadRuntimeModelSettings() {
  try {
    runtimeSettings.value = await knowledgeApi.getRuntimeModelSettings()
    settingsError.value = ''
  } catch (error: any) {
    settingsError.value = error?.message || '获取模型设置失败'
  }
}

async function saveRuntimeModelSettings() {
  settingsSaving.value = true
  settingsError.value = ''
  settingsSuccess.value = ''
  try {
    runtimeSettings.value = await knowledgeApi.updateRuntimeModelSettings({
      api_key: runtimeSettings.value.api_key,
      base_url: runtimeSettings.value.base_url,
      model: runtimeSettings.value.model,
    })
    settingsSuccess.value = '模型设置已生效'
  } catch (error: any) {
    settingsError.value = error?.message || '保存模型设置失败'
  } finally {
    settingsSaving.value = false
  }
}

function toggleSettingsMenu(event?: MouseEvent) {
  event?.stopPropagation()
  showSettingsMenu.value = !showSettingsMenu.value
  if (showSettingsMenu.value) {
    void loadRuntimeModelSettings()
  }
}

function openModelSettings(event?: MouseEvent) {
  event?.stopPropagation()
  showSettingsMenu.value = false
  showModelSettings.value = true
  settingsSuccess.value = ''
}

function closeModelSettings() {
  showModelSettings.value = false
}

function handleDemoLogout(event?: MouseEvent) {
  event?.stopPropagation()
  showSettingsMenu.value = false
  showModelSettings.value = false
  emit('logout')
}

function openKnowledgeBackstage(event?: MouseEvent) {
  event?.stopPropagation()
  showSettingsMenu.value = false
  emit('open-kb')
}

function handleSessionClick(session: Session) {
  openMenuId.value = ''
  store.switchSession(session.session_id)
  void store.loadHistory(session.session_id)
  focusInput()
}

function toggleSessionMenu(sessionId: string, event: MouseEvent) {
  event.stopPropagation()
  openMenuId.value = openMenuId.value === sessionId ? '' : sessionId
}

function askDeleteSession(sessionId: string, event: MouseEvent) {
  event.stopPropagation()
  openMenuId.value = ''
  deletingSessionId.value = sessionId
}

async function confirmDeleteSession() {
  if (!deletingSessionId.value) return
  await store.deleteSession(deletingSessionId.value)
  deletingSessionId.value = ''
  focusInput()
}

function cancelDeleteSession() {
  deletingSessionId.value = ''
}

function handleGlobalClick() {
  openMenuId.value = ''
  showSettingsMenu.value = false
}

watch(() => store.currentMessages.length, scrollToBottom)
watch(() => store.currentId, () => {
  scrollToBottom()
  focusInput()
})
watch(() => props.kbVersion, () => {
  void store.fetchRecommendations()
})

onMounted(async () => {
  if (!store.currentSession) store.createSession()
  await store.fetchRecommendations()
  await loadRuntimeModelSettings()
  await nextTick()
  scrollToBottom()
  focusInput()
  liveTimer = window.setInterval(() => {
    liveNow.value = Date.now()
  }, 200)
  document.addEventListener('click', handleGlobalClick)
})

onBeforeUnmount(() => {
  if (liveTimer) window.clearInterval(liveTimer)
  document.removeEventListener('click', handleGlobalClick)
})
</script>

<template>
  <div class="chat-shell">
    <aside class="sidebar">
      <div class="brand-card">
        <div class="brand-eyebrow">Tourism RAG</div>
        <div class="brand-title">游侠智库</div>
        <div class="brand-desc">把城市攻略、交通、美食、酒店和线路收成一张可对话的旅游地图。</div>
      </div>

      <button class="new-chat-btn" @click="startNewChat">开启新旅程</button>

      <div ref="sessionGroupsRef" class="session-groups">
        <div v-for="[label, items] in groupedSessions" :key="label" class="session-group">
          <div class="session-label">{{ label }}</div>
          <div
            v-for="session in items"
            :key="session.session_id"
            class="session-item"
            :class="{ active: store.currentId === session.session_id }"
            @click="handleSessionClick(session)"
          >
            <div class="session-main">
              <div class="session-title">{{ getTitle(session) }}</div>
              <div class="session-meta">{{ formatDate(session.updated_at) }} · {{ session.messages.length }} 条</div>
            </div>
            <div class="session-menu-wrap" @click.stop>
              <button class="session-menu-btn" type="button" aria-label="会话操作" @click="toggleSessionMenu(session.session_id, $event)">⋯</button>
              <Transition name="fade">
                <div v-if="openMenuId === session.session_id" class="session-menu">
                  <button class="session-menu-item danger" type="button" @click="askDeleteSession(session.session_id, $event)">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 7h2v8h-2v-8zm4 0h2v8h-2v-8zM7 10h2v8H7v-8z" />
                    </svg>
                    <span>删除</span>
                  </button>
                </div>
              </Transition>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-dock" @click.stop>
        <button class="settings-entry" type="button" @click="toggleSettingsMenu($event)">
          <div class="settings-avatar">游</div>
          <div class="settings-copy">
            <strong>游侠旅者</strong>
            <span>demo@tourism.local</span>
          </div>
          <span class="settings-caret">{{ showSettingsMenu ? '▴' : '▾' }}</span>
        </button>

        <Transition name="fade">
          <div v-if="showSettingsMenu" class="settings-menu">
            <button class="settings-menu-item" type="button" @click="openKnowledgeBackstage($event)">
              <div>
                <strong>知识库后台管理</strong>
                <span>上传、查看和维护旅游资料</span>
              </div>
            </button>

            <button class="settings-menu-item" type="button" @click="openModelSettings($event)">
              <div>
                <strong>模型切换</strong>
                <span>OpenAI 兼容接口</span>
              </div>
            </button>

            <button class="settings-menu-item danger" type="button" @click="handleDemoLogout($event)">
              <div>
                <strong>退出登录</strong>
                <span>Demo 入口，不执行真实退出</span>
              </div>
            </button>
          </div>
        </Transition>
      </div>
    </aside>

    <main class="chat-main">
      <header class="hero" :class="{ condensed: hasMessages }">
        <div class="hero-copy">
          <div class="hero-kicker">山海之间，检索即答案</div>
          <h1>让旅游知识库像旅行管家一样回答你</h1>
          <p>先识别城市，再串联城市索引集合和内容 chunks 集合，把交通、景点、酒店、美食、线路一次组织给你。</p>
        </div>
        <div class="hero-actions">
          <div class="toggle-card">
            <div class="toggle-copy">
              <strong>知识库检索</strong>
              <span>
                当前状态：
                <b class="toggle-state" :class="store.ragEnabled ? 'enabled' : 'disabled'">
                  {{ store.ragEnabled ? '已开启' : '已关闭' }}
                </b>
                {{ store.ragEnabled ? '，优先命中旅游知识库' : '，仅进行普通AI问答' }}
              </span>
            </div>
            <button class="hero-btn ghost toggle-btn" @click="store.ragEnabled = !store.ragEnabled; store.persist()">
              切换检索状态
            </button>
          </div>
        </div>
      </header>

      <section class="recommend-strip" :class="{ compact: hasMessages }">
        <div class="recommend-title">热门推荐问法</div>
        <div class="recommend-row">
          <button
            v-for="card in store.recommendationCards"
            :key="card.city"
            class="city-pill"
            @click="useRecommendation(card.city, card.queries[0])"
          >
            <span class="city-name">{{ card.city }}</span>
            <span class="city-meta">{{ card.doc_types.join(' · ') }}</span>
          </button>
          <button
            v-for="prompt in store.quickPrompts"
            :key="prompt"
            class="prompt-pill"
            @click="send(prompt)"
          >
            {{ prompt }}
          </button>
        </div>
      </section>

      <section class="messages-panel">
        <div v-if="!store.currentMessages.length" class="empty-state">
          <div class="compass"></div>
          <div class="empty-title">输入城市名，开始一段可检索的旅程</div>
          <div class="empty-desc">比如：`三亚有什么好玩的？`、`杭州住哪里方便？`、`厦门有哪些值得去的景点图片？`</div>
        </div>

        <div v-else ref="messagesContainer" class="messages">
          <div v-for="(msg, index) in store.currentMessages" :key="`${msg.timestamp}_${index}`" class="message" :class="[msg.role, { pending: isAssistantPending(msg) }]">
            <div class="bubble">
              <div v-if="msg.role === 'assistant'" class="message-topline">
                <span v-if="isAssistantPending(msg)" class="thinking-pill">{{ waitingLabel(msg) }}</span>
                <span v-else-if="displayThinkingTime(msg)" class="thinking-pill subtle">思考 {{ displayThinkingTime(msg).toFixed(1) }}s</span>
                <span v-if="msg.ragReferenced && !isAssistantPending(msg)" class="knowledge-badge">知识库已命中</span>
              </div>

              <div v-if="showWaitingSkeleton(msg)" class="waiting-state">
                <div class="waiting-line strong"></div>
                <div class="waiting-line"></div>
                <div class="waiting-line short"></div>
              </div>
              <div v-else class="message-text" v-html="renderMessageHtml(msg.content)"></div>

              <div v-if="msg.images?.length" class="image-grid">
                <figure v-for="image in msg.images" :key="image.url" class="image-card">
                  <img :src="image.url" :alt="image.alt" />
                  <figcaption>
                    <strong>{{ image.alt || image.title || '旅游图片' }}</strong>
                    <span>{{ image.doc_type || image.city || '知识库图片' }}</span>
                  </figcaption>
                </figure>
              </div>

              <div v-if="msg.sources?.length" class="source-list">
                <span v-for="source in msg.sources" :key="`${source.file_name}-${source.doc_type}`" class="source-chip">
                  {{ source.city || '资料' }} · {{ source.doc_type || '知识' }}
                </span>
              </div>

              <div class="message-meta-row">
                <div class="message-meta-group">
                  <span class="message-meta">{{ formatTime(msg.timestamp) }}</span>
                  <button
                    v-if="!showWaitingSkeleton(msg) && msg.content"
                    class="icon-action"
                    :class="{ copied: copiedKey === `${msg.timestamp}_${index}` }"
                    type="button"
                    :aria-label="copiedKey === `${msg.timestamp}_${index}` ? '已复制' : '复制消息'"
                    @click="copyMessage(msg, index)"
                  >
                    <svg v-if="copiedKey !== `${msg.timestamp}_${index}`" viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M9 9h11v11H9zM4 4h11v2H6v9H4z" />
                    </svg>
                    <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M9.2 16.6 4.9 12.3l1.4-1.4 2.9 2.9 8.5-8.5 1.4 1.4z" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <footer class="composer">
        <div class="composer-top">
          <div class="composer-hint">推荐问题会常驻在输入框上方，点击即可直接发问。</div>
        </div>
        <div class="composer-row">
          <input
            ref="inputRef"
            v-model="inputMessage"
            type="text"
            :disabled="store.loading"
            placeholder="想问哪个城市怎么玩、住哪、吃什么，或者想看图片？"
            @keydown.enter="send()"
          />
          <button v-if="!store.loading" class="send-btn" :disabled="!inputMessage.trim()" @click="send()">出发</button>
          <button v-else class="send-btn stop" @click="store.stopGeneration()">停止</button>
        </div>
      </footer>
    </main>

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showModelSettings" class="settings-modal-overlay" @click.self="closeModelSettings">
          <div class="settings-modal">
            <div class="settings-modal-header">
              <div>
                <div class="settings-modal-eyebrow">Model Routing</div>
                <h3>模型切换</h3>
                <p>配置 OpenAI 兼容接口的模型、Base URL 和 API Key。建议优先使用支持视觉的模型，以免文档内图片内容无法正确理解。</p>
              </div>
              <button class="settings-modal-close" type="button" aria-label="关闭模型切换" @click="closeModelSettings">
                ×
              </button>
            </div>

            <div class="model-panel standalone">
              <div class="model-warning">{{ runtimeSettings.warning }}</div>

              <div class="settings-grid">
                <label class="field">
                  <span>API Key</span>
                  <input v-model="runtimeSettings.api_key" type="password" placeholder="sk-..." />
                </label>

                <label class="field">
                  <span>Base URL</span>
                  <input v-model="runtimeSettings.base_url" type="text" placeholder="https://api.openai.com/v1" />
                </label>
              </div>

              <label class="field">
                <span>模型名</span>
                <input v-model="runtimeSettings.model" type="text" placeholder="gpt-4.1-mini" />
              </label>

              <div v-if="settingsError" class="settings-feedback error">{{ settingsError }}</div>
              <div v-else-if="settingsSuccess" class="settings-feedback success">{{ settingsSuccess }}</div>

              <div class="settings-modal-actions">
                <button class="confirm-btn ghost" type="button" @click="closeModelSettings">取消</button>
                <button class="save-model-btn" type="button" :disabled="settingsSaving" @click="saveRuntimeModelSettings()">
                  {{ settingsSaving ? '保存中...' : '保存并生效' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="deletingSessionId" class="confirm-overlay" @click.self="cancelDeleteSession">
          <div class="confirm-card">
            <div class="confirm-eyebrow">Session Action</div>
            <h3>删除这段会话？</h3>
            <p>删除后，这段对话记录将从当前列表中移除。如果它已经同步到后端，也会一起删除。</p>
            <div class="confirm-actions">
              <button class="confirm-btn ghost" type="button" @click="cancelDeleteSession">取消</button>
              <button class="confirm-btn danger" type="button" @click="confirmDeleteSession">确认删除</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.chat-shell {
  position: absolute;
  z-index: 1;
  inset: 18px 18px 0;
  display: grid;
  grid-template-columns: minmax(268px, 300px) minmax(0, 1fr);
  align-items: stretch;
  gap: 18px;
}

.sidebar,
.chat-main {
  height: 100%;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  backdrop-filter: blur(18px);
  box-shadow: none;
  overflow: hidden;
}

.sidebar {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 18px;
  gap: 18px;
}

.brand-card {
  padding: 18px;
  border-radius: 22px;
  color: #fff9f2;
  background:
    linear-gradient(145deg, rgba(12, 84, 90, 0.96), rgba(14, 124, 134, 0.9)),
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.14), transparent 35%);
}

.brand-eyebrow {
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  opacity: 0.76;
}

.brand-title {
  margin-top: 8px;
  font-family: 'Cormorant Garamond', serif;
  font-size: 36px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.brand-desc {
  margin-top: 10px;
  line-height: 1.7;
  color: rgba(255, 250, 242, 0.82);
}

.new-chat-btn {
  border: none;
  border-radius: 18px;
  padding: 14px 18px;
  background: linear-gradient(135deg, #e3943b, #d26835);
  color: #fff7ef;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 14px 30px rgba(210, 104, 53, 0.22);
}

.session-groups {
  flex: 1;
  min-height: 0;
  overflow: auto;
  margin-right: -18px;
  padding-right: 18px;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
}

.settings-dock {
  position: relative;
  padding-top: 10px;
  border-top: 1px solid rgba(128, 92, 53, 0.08);
  opacity: 1;
}

.settings-entry {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid #ccb08d;
  border-radius: 20px;
  padding: 12px 14px;
  background: linear-gradient(180deg, #fffefb 0%, #f5ebdc 100%);
  color: var(--text);
  cursor: pointer;
  text-align: left;
  opacity: 1;
  box-shadow:
    0 16px 32px rgba(51, 37, 22, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
}

.settings-avatar {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #0f7d88, #d26835);
  color: #fffdf8;
  font-weight: 700;
}

.settings-copy {
  min-width: 0;
  flex: 1;
}

.settings-copy strong,
.settings-copy span,
.settings-menu-item strong,
.settings-menu-item span,
.field span {
  display: block;
}

.settings-copy strong,
.settings-menu-item strong {
  font-size: 14px;
}

.settings-copy span,
.settings-menu-item span {
  margin-top: 3px;
  color: var(--text-tertiary);
  font-size: 12px;
}

.settings-caret {
  color: var(--text-tertiary);
  font-size: 14px;
}

.settings-menu {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 10px);
  z-index: 4;
  padding: 12px;
  border-radius: 20px;
  border: 1px solid #caa883;
  background: linear-gradient(180deg, #fffdfb 0%, #f4e8d8 100%);
  opacity: 1;
  box-shadow:
    0 30px 60px rgba(40, 30, 18, 0.22),
    0 10px 20px rgba(40, 30, 18, 0.14),
    inset 0 1px 0 rgba(255, 255, 255, 0.97);
}

.settings-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: none;
  border-radius: 16px;
  padding: 12px;
  background: #fffaf4;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  opacity: 1;
  box-shadow:
    inset 0 0 0 1px rgba(128, 92, 53, 0.14),
    0 1px 2px rgba(51, 37, 22, 0.04);
}

.settings-menu-item + .settings-menu-item {
  margin-top: 10px;
}

.settings-menu-item.danger {
  color: var(--red);
}

.model-panel {
  padding: 12px;
  border-radius: 18px;
  background: #fff8ef;
  border: 1px solid rgba(128, 92, 53, 0.16);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.96),
    0 2px 6px rgba(51, 37, 22, 0.05);
}

.model-panel.standalone {
  margin-top: 0;
  padding: 18px;
  border-radius: 22px;
}

.model-warning {
  padding: 10px 12px;
  border-radius: 14px;
  background: #fff1d8;
  color: #8c5517;
  font-size: 12px;
  line-height: 1.6;
  border: 1px solid rgba(221, 139, 47, 0.22);
}

.field {
  display: grid;
  gap: 6px;
  margin-top: 10px;
}

.field span {
  color: var(--text-secondary);
  font-size: 12px;
}

.field input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: 14px;
  border: 1px solid #cfb79c;
  background: #ffffff;
  color: var(--text);
  box-shadow:
    inset 0 1px 2px rgba(46, 37, 24, 0.04),
    0 1px 0 rgba(255, 255, 255, 0.88);
}

.field input:focus {
  outline: none;
  border-color: rgba(14, 124, 134, 0.34);
  box-shadow:
    0 0 0 3px rgba(14, 124, 134, 0.1),
    inset 0 1px 2px rgba(46, 37, 24, 0.04);
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 10px;
}

.settings-feedback {
  margin-top: 10px;
  font-size: 12px;
}

.settings-feedback.error {
  color: var(--red);
}

.settings-feedback.success {
  color: var(--green);
}

.save-model-btn {
  width: 100%;
  margin-top: 12px;
  border: none;
  border-radius: 14px;
  padding: 11px 14px;
  background: linear-gradient(135deg, #0f7d88, #0b626a);
  color: #f4fffd;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 10px 20px rgba(15, 125, 136, 0.18);
}

.session-group + .session-group {
  margin-top: 16px;
}

.session-label {
  margin-bottom: 10px;
  color: var(--text-tertiary);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.session-item {
  position: relative;
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 18px;
  padding: 12px 12px 12px 14px;
  background: rgba(255, 255, 255, 0.45);
  cursor: pointer;
}

.session-item + .session-item {
  margin-top: 10px;
}

.session-item.active {
  border-color: rgba(14, 124, 134, 0.26);
  background: rgba(14, 124, 134, 0.09);
}

.session-main {
  min-width: 0;
  flex: 1;
}

.session-title {
  font-weight: 600;
  color: var(--text);
}

.session-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.session-menu-wrap {
  position: relative;
  flex-shrink: 0;
}

.session-menu-btn {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}

.session-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 3;
  min-width: 92px;
  padding: 8px;
  border-radius: 16px;
  border: 1px solid rgba(128, 92, 53, 0.12);
  background: rgba(255, 252, 246, 0.98);
  box-shadow: 0 18px 34px rgba(40, 30, 18, 0.14);
}

.session-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
  border: none;
  border-radius: 12px;
  padding: 10px 12px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
}

.session-menu-item svg,
.icon-action svg {
  width: 16px;
  height: 16px;
  fill: currentColor;
}

.session-menu-item.danger {
  color: var(--red);
}

.chat-main {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  min-height: 0;
  min-width: 0;
  padding: 18px;
  gap: 14px;
}

.hero {
  display: flex;
  justify-content: space-between;
  align-items: stretch;
  gap: 20px;
  min-height: clamp(148px, 22vh, 168px);
  padding: 20px 22px;
  border-radius: 24px;
  background:
    linear-gradient(135deg, rgba(255, 253, 247, 0.92), rgba(255, 244, 223, 0.82)),
    radial-gradient(circle at right, rgba(14, 124, 134, 0.08), transparent 38%);
  border: 1px solid rgba(128, 92, 53, 0.1);
  transition: box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.hero-copy {
  min-width: 0;
  flex: 1 1 auto;
}

.hero.condensed {
  border-color: rgba(14, 124, 134, 0.16);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45);
}

.hero-kicker {
  color: var(--primary);
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.hero h1 {
  margin: 10px 0 12px;
  font-family: 'Cormorant Garamond', serif;
  font-size: clamp(34px, 3.4vw, 46px);
  line-height: 0.98;
  color: #2b2318;
}

.hero.condensed h1 {
  margin-bottom: 12px;
}

.hero p {
  max-width: 760px;
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.75;
  text-wrap: pretty;
}

.hero-actions {
  display: flex;
  align-items: stretch;
  justify-content: center;
  flex: 0 1 360px;
  width: min(360px, 100%);
  min-width: 320px;
}

.toggle-card {
  width: 100%;
  height: 100%;
  min-height: 154px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  padding: 18px;
  border-radius: 22px;
  background: #fffaf2;
  border: 1px solid rgba(128, 92, 53, 0.12);
}

.toggle-copy {
  min-height: 0;
}

.toggle-copy strong,
.toggle-copy span {
  display: block;
}

.toggle-copy strong {
  font-size: 15px;
  color: var(--text);
}

.toggle-copy span {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 20px;
  height: 20px;
  white-space: nowrap;
}

.toggle-state {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 50px;
  margin: 0 4px;
  padding: 0 8px;
  border-radius: 999px;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.toggle-state.enabled {
  background: rgba(23, 152, 92, 0.16);
  color: #18794e;
}

.toggle-state.disabled {
  background: rgba(191, 75, 61, 0.14);
  color: #b23f35;
}

.toggle-btn {
  width: 100%;
  min-height: 48px;
  flex: 0 0 48px;
}

.hero-btn {
  border-radius: 18px;
  padding: 14px 16px;
  font-weight: 700;
  cursor: pointer;
}

.hero-btn.solid {
  border: none;
  background: linear-gradient(135deg, #0f7d88, #085f67);
  color: #f3fffd;
}

.hero-btn.ghost {
  border: 1px solid rgba(14, 124, 134, 0.18);
  background: #eef7f7;
  color: var(--primary);
}

.recommend-strip {
  min-height: 104px;
  max-height: 116px;
  padding: 14px 16px;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  border-radius: 22px;
  background: rgba(255, 253, 247, 0.78);
  border: 1px solid rgba(128, 92, 53, 0.1);
  transition: border-color 0.18s ease, background 0.18s ease;
}

.recommend-strip::-webkit-scrollbar {
  display: none;
}

.recommend-strip.compact {
  border-color: rgba(221, 139, 47, 0.14);
  background: rgba(255, 250, 242, 0.84);
}

.recommend-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
}

.recommend-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
  align-items: start;
}

.city-pill,
.prompt-pill {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow: hidden;
  border-radius: 16px;
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid transparent;
  cursor: pointer;
  text-align: left;
}

.city-pill {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-start;
  background: rgba(14, 124, 134, 0.1);
  color: var(--primary);
}

.city-name {
  flex-shrink: 0;
  font-weight: 700;
  white-space: nowrap;
}

.city-meta {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: rgba(14, 124, 134, 0.82);
}

.prompt-pill {
  display: flex;
  align-items: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: rgba(221, 139, 47, 0.12);
  color: #9b5b19;
}

.messages-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border-radius: 24px;
  background: rgba(255, 251, 245, 0.76);
  border: 1px solid rgba(128, 92, 53, 0.1);
}

.empty-state {
  height: 100%;
  display: grid;
  place-items: center;
  text-align: center;
  padding: 36px;
}

.compass {
  width: 92px;
  height: 92px;
  border-radius: 50%;
  background:
    radial-gradient(circle at center, rgba(255, 255, 255, 0.92) 0 26%, transparent 27%),
    conic-gradient(from 0deg, rgba(14, 124, 134, 0.95), rgba(221, 139, 47, 0.92), rgba(14, 124, 134, 0.95));
  box-shadow: 0 18px 44px rgba(14, 124, 134, 0.18);
}

.empty-title {
  margin-top: 18px;
  font-family: 'Cormorant Garamond', serif;
  font-size: 34px;
  font-weight: 700;
}

.empty-desc {
  margin-top: 10px;
  max-width: 620px;
  line-height: 1.8;
  color: var(--text-secondary);
}

.messages {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scrollbar-gutter: stable both-edges;
  overscroll-behavior: contain;
  padding: 24px clamp(18px, 2.3vw, 28px) 136px;
}

.message {
  display: flex;
  margin-bottom: 18px;
}

.message.user {
  justify-content: flex-end;
}

.bubble {
  width: min(940px, 88%);
  padding: 18px 20px;
  border-radius: 24px;
  background: var(--surface-strong);
  border: 1px solid rgba(128, 92, 53, 0.08);
  box-shadow: 0 18px 36px rgba(70, 45, 22, 0.08);
}

.message.user .bubble {
  width: fit-content;
  max-width: min(560px, 72%);
  background: linear-gradient(135deg, #0f7d88, #0c6068);
  color: #f8fffe;
}

.message.pending .bubble {
  min-height: 138px;
}

.message-topline {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--text-tertiary);
}

.thinking-pill,
.knowledge-badge {
  border-radius: 999px;
  padding: 4px 10px;
}

.thinking-pill {
  background: rgba(221, 139, 47, 0.12);
  color: #9b5b19;
}

.thinking-pill.subtle {
  background: rgba(46, 37, 24, 0.06);
  color: var(--text-secondary);
}

.knowledge-badge {
  background: rgba(14, 124, 134, 0.12);
  color: var(--primary);
}

.waiting-state {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.waiting-line {
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(14, 124, 134, 0.12), rgba(221, 139, 47, 0.16), rgba(14, 124, 134, 0.12));
  background-size: 200% 100%;
  animation: pulse-slide 1.4s linear infinite;
}

.waiting-line.strong {
  width: 72%;
}

.waiting-line.short {
  width: 48%;
}

.message-text {
  margin: 10px 0 0;
  line-height: 1.88;
  font-family: inherit;
  font-size: 15px;
}

.message-text :deep(h2),
.message-text :deep(h3),
.message-text :deep(p),
.message-text :deep(ul),
.message-text :deep(hr),
.message-text :deep(.md-table-wrap) {
  margin: 0;
}

.message-text :deep(h2),
.message-text :deep(h3) {
  margin-top: 10px;
  color: inherit;
  font-size: 16px;
  line-height: 1.6;
}

.message-text :deep(h2):first-child,
.message-text :deep(h3):first-child,
.message-text :deep(p):first-child,
.message-text :deep(ul):first-child,
.message-text :deep(.md-table-wrap):first-child {
  margin-top: 0;
}

.message-text :deep(p + p),
.message-text :deep(p + ul),
.message-text :deep(p + .md-table-wrap),
.message-text :deep(ul + p),
.message-text :deep(.md-table-wrap + p),
.message-text :deep(.md-table-wrap + ul),
.message-text :deep(h2 + p),
.message-text :deep(h3 + p),
.message-text :deep(h2 + ul),
.message-text :deep(h3 + ul),
.message-text :deep(h2 + .md-table-wrap),
.message-text :deep(h3 + .md-table-wrap),
.message-text :deep(ul + ul),
.message-text :deep(ul + .md-table-wrap),
.message-text :deep(hr + p),
.message-text :deep(p + hr),
.message-text :deep(.md-table-wrap + hr) {
  margin-top: 8px;
}

.message-text :deep(ul) {
  padding-left: 18px;
}

.message-text :deep(li + li) {
  margin-top: 6px;
}

.message-text :deep(hr) {
  border: none;
  border-top: 1px solid rgba(128, 92, 53, 0.18);
}

.message-text :deep(.md-table-wrap) {
  overflow-x: auto;
}

.message-text :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.message-text :deep(th),
.message-text :deep(td) {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid rgba(128, 92, 53, 0.12);
  vertical-align: top;
}

.message-text :deep(th) {
  font-weight: 700;
  color: inherit;
  background: rgba(14, 124, 134, 0.05);
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.image-card {
  margin: 0;
  overflow: hidden;
  border-radius: 18px;
  background: #fffaf2;
  border: 1px solid rgba(128, 92, 53, 0.12);
}

.image-card img {
  display: block;
  width: 100%;
  height: 148px;
  object-fit: cover;
}

.image-card figcaption {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px 12px;
}

.image-card strong {
  font-size: 13px;
}

.image-card span {
  font-size: 12px;
  color: var(--text-secondary);
}

.source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.source-chip {
  border-radius: 999px;
  padding: 5px 10px;
  background: rgba(46, 37, 24, 0.06);
  color: var(--text-secondary);
  font-size: 12px;
}

.message-meta-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  margin-top: 12px;
}

.message-meta-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.message-meta {
  font-size: 11px;
  color: var(--text-tertiary);
}

.message.user .message-meta {
  color: rgba(248, 255, 254, 0.72);
}

.icon-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 10px;
  padding: 0;
  background: rgba(46, 37, 24, 0.06);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.message.user .icon-action {
  background: rgba(255, 255, 255, 0.14);
  color: rgba(248, 255, 254, 0.84);
}

.icon-action.copied {
  background: rgba(31, 143, 87, 0.14);
  color: var(--green);
}

.message.user .icon-action.copied {
  background: rgba(223, 255, 239, 0.18);
  color: #effff6;
}

.composer {
  position: relative;
  padding: 16px 18px 10px;
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255, 250, 242, 0.96), rgba(250, 243, 231, 0.88)),
    radial-gradient(circle at 20% 0%, rgba(14, 124, 134, 0.06), transparent 32%);
  border: 1px solid rgba(128, 92, 53, 0.1);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    0 14px 30px rgba(70, 45, 22, 0.06);
}

.composer-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.composer-hint {
  color: var(--text-secondary);
  font-size: 13px;
}

.composer-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
}

.composer-row input {
  min-width: 0;
  height: 56px;
  padding: 0 18px;
  border-radius: 18px;
  border: 1px solid rgba(128, 92, 53, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(255, 250, 242, 0.94));
  box-shadow:
    inset 0 1px 2px rgba(255, 255, 255, 0.7),
    0 10px 20px rgba(46, 37, 24, 0.04);
  outline: none;
  color: var(--text);
  transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.composer-row input:focus {
  border-color: rgba(14, 124, 134, 0.3);
  box-shadow:
    inset 0 1px 2px rgba(255, 255, 255, 0.78),
    0 0 0 4px rgba(14, 124, 134, 0.08);
}

.send-btn {
  min-width: 104px;
  border: none;
  border-radius: 18px;
  padding: 0 20px;
  background: linear-gradient(135deg, #e3943b, #d26835);
  color: #fff7ef;
  font-weight: 700;
  cursor: pointer;
}

.send-btn.stop {
  background: linear-gradient(135deg, #d75b49, #b33d35);
}

.settings-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 58;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(35, 24, 16, 0.34);
  backdrop-filter: blur(8px);
}

.settings-modal {
  width: min(720px, 100%);
  padding: 24px;
  border-radius: 28px;
  background: rgba(255, 250, 242, 0.985);
  border: 1px solid rgba(128, 92, 53, 0.14);
  box-shadow: 0 24px 60px rgba(35, 24, 16, 0.18);
}

.settings-modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.settings-modal-eyebrow {
  color: var(--primary);
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.settings-modal-header h3 {
  margin: 10px 0 8px;
  font-family: 'Cormorant Garamond', serif;
  font-size: 34px;
}

.settings-modal-header p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.settings-modal-close {
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 14px;
  background: rgba(46, 37, 24, 0.06);
  color: var(--text-secondary);
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
}

.settings-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}

.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(35, 24, 16, 0.34);
  backdrop-filter: blur(8px);
}

.confirm-card {
  width: min(420px, 100%);
  padding: 24px;
  border-radius: 24px;
  background: rgba(255, 250, 242, 0.98);
  border: 1px solid rgba(128, 92, 53, 0.14);
  box-shadow: 0 24px 60px rgba(35, 24, 16, 0.16);
}

.confirm-eyebrow {
  color: var(--primary);
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.confirm-card h3 {
  margin: 10px 0 8px;
  font-family: 'Cormorant Garamond', serif;
  font-size: 34px;
}

.confirm-card p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 22px;
}

.confirm-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 16px;
  padding: 12px 16px;
  white-space: nowrap;
  font-weight: 700;
  cursor: pointer;
}

.confirm-btn.ghost {
  background: rgba(46, 37, 24, 0.06);
  color: var(--text);
}

.confirm-btn.danger {
  background: linear-gradient(135deg, #d75b49, #b33d35);
  color: #fff7ef;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

@keyframes pulse-slide {
  from {
    background-position: 200% 0;
  }
  to {
    background-position: 0 0;
  }
}

@media (max-width: 1100px) {
  .chat-shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    display: none;
  }

  .hero,
  .hero-actions {
    flex-direction: column;
  }

  .hero-actions {
    min-width: 0;
  }

  .settings-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1320px) {
  .chat-shell {
    gap: 14px;
  }

  .hero {
    flex-wrap: wrap;
  }

  .hero-actions {
    flex: 1 1 100%;
    width: 100%;
    min-width: 0;
  }

  .toggle-card {
    min-height: 138px;
  }
}

@media (max-height: 860px) {
  .chat-shell {
    inset: 12px 12px 0;
    gap: 12px;
  }

  .sidebar,
  .chat-main {
    border-radius: 22px;
  }

  .sidebar {
    padding: 14px;
    gap: 14px;
  }

  .brand-card {
    padding: 16px;
  }

  .brand-title {
    font-size: 32px;
  }

  .new-chat-btn {
    padding: 12px 16px;
  }

  .chat-main {
    padding: 14px;
    gap: 12px;
  }

  .hero {
    min-height: 144px;
    padding: 18px;
  }

  .recommend-strip {
    min-height: 92px;
    max-height: 102px;
    padding: 12px 14px;
  }

  .messages {
    padding-bottom: 118px;
  }

  .composer {
    padding: 14px 16px 8px;
  }
}

@media (max-height: 740px) {
  .sidebar {
    gap: 12px;
  }

  .brand-card {
    padding: 14px;
  }

  .brand-title {
    font-size: 28px;
  }

  .brand-desc,
  .hero p,
  .composer-top {
    display: none;
  }

  .hero {
    min-height: 0;
    padding: 16px;
  }

  .hero h1,
  .hero.condensed h1 {
    margin-bottom: 0;
    font-size: clamp(28px, 3vw, 34px);
  }

  .recommend-strip {
    min-height: 82px;
    max-height: 90px;
  }

  .recommend-row {
    margin-top: 8px;
  }

  .messages {
    padding-top: 18px;
    padding-bottom: 108px;
  }

  .composer-row input {
    height: 50px;
  }
}

@media (max-width: 720px) {
  .chat-shell {
    inset: 10px 10px 0;
    gap: 10px;
  }

  .chat-main {
    padding: 12px;
    grid-template-rows: auto auto minmax(0, 1fr) auto;
  }

  .hero h1,
  .hero.condensed h1 {
    font-size: 34px;
  }

  .recommend-row {
    grid-template-columns: 1fr;
  }

  .settings-modal {
    padding: 18px;
    border-radius: 24px;
  }

  .settings-modal-header {
    gap: 12px;
  }

  .settings-modal-header h3 {
    font-size: 30px;
  }

  .session-groups {
    margin-right: -12px;
    padding-right: 12px;
  }

  .bubble {
    width: 100%;
  }

  .message.user .bubble {
    max-width: 88%;
  }

  .composer-row {
    grid-template-columns: 1fr;
  }

  .message-meta-row {
    justify-content: flex-start;
  }
}
</style>
