<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { knowledgeApi, type RuntimeModelSettings } from '../../api/knowledge'
import { useChatStore, type Message, type Session } from '../../stores/chat'

const props = defineProps<{
  kbVersion: number
  authRole: 'root' | 'guest'
  displayName: string
  displayEmail: string
  resetGuestState: boolean
}>()
const emit = defineEmits<{ 'open-kb': []; logout: [] }>()

type ModelTestStatus = 'idle' | 'success' | 'failed'

interface CustomModelProfile {
  id: string
  name: string
  api_key: string
  base_url: string
  model: string
  last_test_status: ModelTestStatus
  last_test_message: string
  updated_at: string
}

const MODEL_PROFILES_KEY = 'tourism_model_profiles'
const ACTIVE_MODEL_PROFILE_KEY = 'tourism_active_model_profile'
const DEFAULT_MODEL_ID = 'default'
const MODEL_GUARD_MESSAGE = '当前启用的自定义模型还不能正常使用。请先在“模型切换”里完成测试并确认通过，或切回默认模型后再继续发送消息。'

const store = useChatStore()
const inputMessage = ref('')
const messagesContainer = ref<HTMLDivElement>()
const inputRef = ref<HTMLInputElement>()
const sessionGroupsRef = ref<HTMLDivElement>()
const openMenuId = ref('')
const deletingSessionId = ref('')
const renamingSessionId = ref('')
const renameDraft = ref('')
const renamingBusy = ref(false)
const renameError = ref('')
const copiedKey = ref('')
const showSettingsMenu = ref(false)
const showModelSettings = ref(false)
const settingsSaving = ref(false)
const settingsTesting = ref(false)
const settingsError = ref('')
const settingsSuccess = ref('')
const deletingModelProfileId = ref('')
const runtimeSettings = ref<RuntimeModelSettings>({
  api_key: '',
  base_url: '',
  model: '',
  is_default: true,
  vision_required: true,
  warning: '请优先使用支持视觉的模型，否则文档里的图片信息可能无法被正确理解。',
})
const composerModelWarning = ref('')
const modelProfiles = ref<CustomModelProfile[]>([])
const selectedModelId = ref(DEFAULT_MODEL_ID)
const activeModelId = ref(DEFAULT_MODEL_ID)
const showModelProfileEditor = ref(false)
const editingModelProfileId = ref('')
const modelEditorStatus = ref<ModelTestStatus>('idle')
const modelEditorMessage = ref('')
const modelForm = ref({
  name: '',
  api_key: '',
  base_url: '',
  model: '',
})
const liveNow = ref(Date.now())
const EMPTY_TITLE = '输入城市名，开始一段可检索的旅程'
const EMPTY_DESC = '比如：三亚有什么好玩的？、杭州住哪里方便？、厦门有哪些值得去的景点图片？'
const emptyTitleText = ref(EMPTY_TITLE)
const emptyDescText = ref(EMPTY_DESC)
const streamedIntroSessionId = ref('')
const isStreamingIntro = ref(false)
let liveTimer: number | null = null
let introTimer: number | null = null

function focusInput() {
  nextTick(() => inputRef.value?.focus())
}

const hasMessages = computed(() => store.currentMessages.length > 0)
const selectedModelProfile = computed(() => modelProfiles.value.find(item => item.id === selectedModelId.value) || null)
const activeCustomModelProfile = computed(() => modelProfiles.value.find(item => item.id === activeModelId.value) || null)
const isDefaultModelSelected = computed(() => selectedModelId.value === DEFAULT_MODEL_ID)
const canManageWorkspace = computed(() => props.authRole === 'root')
const ragEnabledCopy = '当前状态： 已开启 ，优先命中旅游知识库'
const ragDisabledCopy = '当前状态： 已关闭 ，仅进行普通AI问答'
const toggleReserveCopy = ragEnabledCopy.length >= ragDisabledCopy.length ? ragEnabledCopy : ragDisabledCopy

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

function getMessageCount(session: Session) {
  return session.message_count ?? session.messages.length
}

function isAssistantPending(message: Message) {
  return message.role === 'assistant' && Boolean(message.pending)
}

function hasVisibleContent(message: Message) {
  return Boolean(message.content && message.content.trim())
}

function showWaitingSkeleton(message: Message) {
  return isAssistantPending(message) && !hasVisibleContent(message)
}

function displayThinkingTime(message: Message) {
  if (isAssistantPending(message) && !message.content) {
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

function normalizeMarkdownTableLines(content: string) {
  const normalized = escapeHtml(content || '')
    .replace(/\r\n?/g, '\n')
    .replace(/\uFF5C/g, '|')
    .replace(/[\u200B-\u200D\uFEFF]/g, '')
    .trim()

  if (!normalized) return []

  const rawLines = normalized.split('\n').map(line => line.trimEnd())
  const lines: string[] = []

  for (let index = 0; index < rawLines.length; index += 1) {
    const current = rawLines[index]
    const trimmed = current.trim()

    if (!trimmed) {
      const previous = lines[lines.length - 1]?.trim() || ''
      let nextIndex = index + 1
      while (nextIndex < rawLines.length && !rawLines[nextIndex].trim()) nextIndex += 1
      const next = rawLines[nextIndex]?.trim() || ''
      if (previous.includes('|') && next.includes('|')) continue
      lines.push('')
      continue
    }

    lines.push(current)
  }

  return lines
}

function renderMessageHtml(content: string) {
  const lines = normalizeMarkdownTableLines(content)
  if (!lines.length) return ''

  const htmlBlocks: string[] = []
  for (let index = 0; index < lines.length; ) {
    const current = lines[index]?.trim() || ''
    if (!current) {
      index += 1
      continue
    }

    if (current.includes('|')) {
      let lookahead = index + 1
      while (lookahead < lines.length && !lines[lookahead].trim()) lookahead += 1
      if (lookahead < lines.length && isMarkdownTableSeparator(lines[lookahead].trim())) {
        const tableLines = [current, lines[lookahead].trim()]
        index = lookahead + 1
        while (index < lines.length) {
          const row = lines[index].trim()
          if (!row) {
            index += 1
            continue
          }
          if (!row.includes('|')) break
          tableLines.push(row)
          index += 1
        }

        const headers = splitMarkdownTableRow(tableLines[0]).map(cell => `<th>${cell}</th>`).join('')
        const rows = tableLines
          .slice(2)
          .map(line => {
            const cells = splitMarkdownTableRow(line).map(cell => `<td>${cell}</td>`).join('')
            return `<tr>${cells}</tr>`
          })
          .join('')
        htmlBlocks.push(`<div class="md-table-wrap"><table><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table></div>`)
        continue
      }
    }

    const paragraphLines: string[] = []
    while (index < lines.length) {
      const line = lines[index].trim()
      if (!line) break
      paragraphLines.push(line)
      index += 1
    }

    if (!paragraphLines.length) {
      index += 1
      continue
    }

    if (paragraphLines.every(line => /^[-*]\s+/.test(line))) {
      const items = paragraphLines.map(line => `<li>${renderInlineMarkdown(line.replace(/^[-*]\s+/, ''))}</li>`)
      htmlBlocks.push(`<ul>${items.join('')}</ul>`)
      continue
    }

    if (paragraphLines.every(line => /^>\s?/.test(line))) {
      const quote = paragraphLines
        .map(line => renderInlineMarkdown(line.replace(/^>\s?/, '')))
        .join('<br />')
      htmlBlocks.push(`<blockquote>${quote}</blockquote>`)
      continue
    }

    htmlBlocks.push(
      paragraphLines
        .map(line => {
          if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)) return '<hr />'
          if (/^###\s+/.test(line)) return `<h4>${renderInlineMarkdown(line.replace(/^###\s+/, ''))}</h4>`
          if (/^##\s+/.test(line)) return `<h3>${renderInlineMarkdown(line.replace(/^##\s+/, ''))}</h3>`
          if (/^#\s+/.test(line)) return `<h2>${renderInlineMarkdown(line.replace(/^#\s+/, ''))}</h2>`
          if (/^[-*]\s+/.test(line)) return `<p>${renderInlineMarkdown(line.replace(/^[-*]\s+/, '• '))}</p>`
          return `<p>${renderInlineMarkdown(line)}</p>`
        })
        .join(''),
    )
  }

  return htmlBlocks.join('')
}

function loadStoredModelProfiles() {
  try {
    const raw = JSON.parse(localStorage.getItem(MODEL_PROFILES_KEY) || '[]')
    modelProfiles.value = Array.isArray(raw) ? raw : []
  } catch {
    modelProfiles.value = []
  }
}

function persistModelProfiles() {
  localStorage.setItem(MODEL_PROFILES_KEY, JSON.stringify(modelProfiles.value))
  localStorage.setItem(ACTIVE_MODEL_PROFILE_KEY, activeModelId.value)
}

function hydrateModelForm(profile: CustomModelProfile | null) {
  modelForm.value = profile
    ? {
        name: profile.name,
        api_key: profile.api_key,
        base_url: profile.base_url,
        model: profile.model,
      }
    : {
        name: '',
        api_key: '',
        base_url: '',
        model: '',
      }
}

function resetModelEditorState() {
  editingModelProfileId.value = ''
  modelEditorStatus.value = 'idle'
  modelEditorMessage.value = ''
}

function selectModelProfile(id: string) {
  selectedModelId.value = id
  settingsError.value = ''
  settingsSuccess.value = ''
  hydrateModelForm(id === DEFAULT_MODEL_ID ? null : selectedModelProfile.value)
}

async function activateDefaultModel(event?: MouseEvent) {
  event?.stopPropagation()
  settingsError.value = ''
  settingsSuccess.value = ''
  try {
    const data = await knowledgeApi.resetRuntimeModelSettings()
    composerModelWarning.value = ''
    localStorage.setItem(ACTIVE_MODEL_PROFILE_KEY, DEFAULT_MODEL_ID)
    syncRuntimeSelection(data, DEFAULT_MODEL_ID)
  } catch (error: any) {
    settingsError.value = error?.message || '切换到默认配置失败'
  }
}

async function activateCustomModel(id: string, event?: MouseEvent) {
  event?.stopPropagation()
  const profile = modelProfiles.value.find(item => item.id === id)
  if (!profile) return
  selectedModelId.value = id
  settingsError.value = ''
  settingsSuccess.value = ''
  if (profile.last_test_status !== 'success') {
    settingsError.value = '请先测试并保存该模型，再切换为当前使用配置。'
    openModelProfileEditor()
    return
  }
  try {
    const data = await knowledgeApi.updateRuntimeModelSettings({
      api_key: profile.api_key,
      base_url: profile.base_url,
      model: profile.model,
    })
    composerModelWarning.value = ''
    localStorage.setItem(ACTIVE_MODEL_PROFILE_KEY, id)
    syncRuntimeSelection(data, id)
  } catch (error: any) {
    settingsError.value = error?.message || '切换自定义模型失败'
  }
}

function openModelProfileEditor() {
  if (selectedModelId.value === DEFAULT_MODEL_ID) return
  settingsError.value = ''
  settingsSuccess.value = ''
  hydrateModelForm(selectedModelProfile.value)
  editingModelProfileId.value = selectedModelProfile.value?.id || ''
  modelEditorStatus.value = selectedModelProfile.value?.last_test_status || 'idle'
  modelEditorMessage.value = selectedModelProfile.value?.last_test_message || ''
  showModelProfileEditor.value = true
}

function openModelProfileEditorFor(id: string, event?: MouseEvent) {
  event?.stopPropagation()
  selectModelProfile(id)
  nextTick(() => {
    openModelProfileEditor()
  })
}

function closeModelProfileEditor() {
  showModelProfileEditor.value = false
  settingsError.value = ''
  settingsSuccess.value = ''
  resetModelEditorState()
  hydrateModelForm(selectedModelProfile.value)
}

function syncRuntimeSelection(data: RuntimeModelSettings, preferredProfileId = '') {
  loadStoredModelProfiles()
  runtimeSettings.value = data
  if (data.is_default) {
    modelProfiles.value = modelProfiles.value.filter(
      item => !(item.name === '当前使用配置' && item.model === data.model && item.base_url === data.base_url),
    )
    activeModelId.value = DEFAULT_MODEL_ID
  } else {
    const preferredMatch =
      preferredProfileId &&
      modelProfiles.value.find(
        item =>
          item.id === preferredProfileId &&
          item.api_key === data.api_key &&
          item.base_url === data.base_url &&
          item.model === data.model,
      )
    const match =
      preferredMatch ||
      modelProfiles.value.find(
        item => item.api_key === data.api_key && item.base_url === data.base_url && item.model === data.model,
      )
    if (match) {
      activeModelId.value = match.id
      match.last_test_status = 'success'
      match.last_test_message = '当前配置可以直接使用。'
      match.updated_at = new Date().toISOString()
    } else {
      const importedId = `custom_${Date.now()}`
      modelProfiles.value.unshift({
        id: importedId,
        name: '当前使用配置',
        api_key: data.api_key,
        base_url: data.base_url,
        model: data.model,
        last_test_status: 'success',
        last_test_message: '当前配置可以直接使用。',
        updated_at: new Date().toISOString(),
      })
      activeModelId.value = importedId
    }
  }

  const storedSelected = localStorage.getItem(ACTIVE_MODEL_PROFILE_KEY)
  if (storedSelected && (storedSelected === DEFAULT_MODEL_ID || modelProfiles.value.some(item => item.id === storedSelected))) {
    selectedModelId.value = storedSelected
  } else {
    selectedModelId.value = activeModelId.value
  }
  hydrateModelForm(selectedModelId.value === DEFAULT_MODEL_ID ? null : selectedModelProfile.value)
  persistModelProfiles()
}

function createCustomModelProfile() {
  settingsError.value = ''
  settingsSuccess.value = ''
  resetModelEditorState()
  modelForm.value = {
    name: '',
    api_key: '',
    base_url: '',
    model: '',
  }
  showModelProfileEditor.value = true
}

function ensureActiveModelReady() {
  if (activeModelId.value === DEFAULT_MODEL_ID) {
    composerModelWarning.value = ''
    return true
  }
  const profile = activeCustomModelProfile.value
  if (profile?.last_test_status === 'success') {
    composerModelWarning.value = ''
    return true
  }
  composerModelWarning.value = MODEL_GUARD_MESSAGE
  settingsError.value = MODEL_GUARD_MESSAGE
  showModelSettings.value = true
  return false
}

async function send(message?: string) {
  const content = (message ?? inputMessage.value).trim()
  if (!content || store.loading) return
  if (!ensureActiveModelReady()) return
  composerModelWarning.value = ''
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

function clearIntroTimer() {
  if (introTimer) {
    window.clearTimeout(introTimer)
    introTimer = null
  }
}

function showEmptyIntroImmediately() {
  clearIntroTimer()
  isStreamingIntro.value = false
  emptyTitleText.value = EMPTY_TITLE
  emptyDescText.value = EMPTY_DESC
}

function streamText(fullText: string, target: typeof emptyTitleText, charDelay: number, onDone?: () => void, index = 0) {
  if (index === 0) target.value = ''
  if (index >= fullText.length) {
    onDone?.()
    return
  }
  target.value += fullText[index]
  introTimer = window.setTimeout(() => {
    streamText(fullText, target, charDelay, onDone, index + 1)
  }, charDelay)
}

function playNewSessionIntro(sessionId: string) {
  if (!sessionId || streamedIntroSessionId.value === sessionId) {
    showEmptyIntroImmediately()
    return
  }
  streamedIntroSessionId.value = sessionId
  isStreamingIntro.value = true
  clearIntroTimer()
  emptyTitleText.value = ''
  emptyDescText.value = ''
  streamText(EMPTY_TITLE, emptyTitleText, 34, () => {
    introTimer = window.setTimeout(() => {
      streamText(EMPTY_DESC, emptyDescText, 18, () => {
        isStreamingIntro.value = false
      })
    }, 80)
  })
}

function startNewChat() {
  store.createSession()
  openMenuId.value = ''
  playNewSessionIntro(store.currentId)
  focusInput()
}

function toggleRagState(event?: MouseEvent) {
  store.ragEnabled = !store.ragEnabled
  store.persist()
  const target = event?.currentTarget as HTMLElement | null
  if (!target) return
  target.animate(
    [
      { transform: 'scale(1)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.72), 0 8px 18px rgba(14,124,134,0.08)' },
      { transform: 'scale(0.985)', boxShadow: 'inset 0 0 0 1px rgba(14,124,134,0.18), 0 0 0 6px rgba(14,124,134,0.12), 0 14px 24px rgba(14,124,134,0.16)' },
      { transform: 'scale(1)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.72), 0 8px 18px rgba(14,124,134,0.08)' },
    ],
    { duration: 320, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' },
  )
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
    const data = await knowledgeApi.getRuntimeModelSettings()
    syncRuntimeSelection(data)
    settingsError.value = ''
  } catch (error: any) {
    settingsError.value = error?.message || '获取模型设置失败'
  }
}

async function saveRuntimeModelSettings() {
  const isCreatingProfile = !editingModelProfileId.value
  const targetProfileId = isCreatingProfile ? '' : editingModelProfileId.value || selectedModelProfile.value?.id || ''

  if (!showModelProfileEditor.value && isDefaultModelSelected.value) {
    settingsError.value = '默认配置不支持直接编辑，请新增一个自定义模型后再保存。'
    return
  }
  if (!modelForm.value.api_key.trim() || !modelForm.value.base_url.trim() || !modelForm.value.model.trim()) {
    settingsError.value = '请完整填写 API Key、Base URL 和模型名。'
    return
  }
  settingsSaving.value = true
  settingsError.value = ''
  settingsSuccess.value = ''
  try {
    const nextProfile: CustomModelProfile = {
      id: targetProfileId || `custom_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      name: modelForm.value.model.trim(),
      api_key: modelForm.value.api_key.trim(),
      base_url: modelForm.value.base_url.trim().replace(/\/+$/, ''),
      model: modelForm.value.model.trim(),
      last_test_status: modelEditorStatus.value,
      last_test_message: modelEditorMessage.value || '已保存，请先点击测试；测试通过后再次保存即可直接使用。',
      updated_at: new Date().toISOString(),
    }
    modelProfiles.value = [nextProfile, ...modelProfiles.value.filter(item => item.id !== nextProfile.id)]
    persistModelProfiles()
    selectedModelId.value = nextProfile.id
    const shouldUseNow = nextProfile.last_test_status === 'success'
    if (shouldUseNow) {
      const data = await knowledgeApi.updateRuntimeModelSettings({
        api_key: nextProfile.api_key,
        base_url: nextProfile.base_url,
        model: nextProfile.model,
      })
      activeModelId.value = nextProfile.id
      localStorage.setItem(ACTIVE_MODEL_PROFILE_KEY, nextProfile.id)
      syncRuntimeSelection(data, nextProfile.id)
      settingsSuccess.value = ''
      composerModelWarning.value = ''
    } else {
      selectModelProfile(nextProfile.id)
      settingsSuccess.value = isCreatingProfile
        ? '自定义模型已新增。请先点击测试，测试通过后再次保存即可直接使用。'
        : '自定义模型已保存。请先点击测试，测试通过后再次保存即可直接使用。'
    }
    showModelProfileEditor.value = false
    resetModelEditorState()
  } catch (error: any) {
    settingsError.value = error?.message || '保存模型设置失败'
  } finally {
    settingsSaving.value = false
  }
}

async function testSelectedModelProfile() {
  const TEST_FAILURE_MESSAGE = '测试未通过，请检查配置信息后重试。'
  if (!modelForm.value.api_key.trim() || !modelForm.value.base_url.trim() || !modelForm.value.model.trim()) {
    settingsError.value = '请先完整填写 API Key、Base URL 和模型名，再进行测试。'
    return
  }
  settingsTesting.value = true
  settingsError.value = ''
  settingsSuccess.value = ''
  try {
    const result = await knowledgeApi.testRuntimeModelSettings({
      api_key: modelForm.value.api_key.trim(),
      base_url: modelForm.value.base_url.trim(),
      model: modelForm.value.model.trim(),
    })
    const nextStatus: ModelTestStatus = result.ok ? 'success' : 'failed'
    modelEditorStatus.value = nextStatus
    modelEditorMessage.value = result.ok ? result.message : TEST_FAILURE_MESSAGE
    if (result.ok) {
      settingsSuccess.value = ''
      composerModelWarning.value = ''
    } else {
      settingsError.value = ''
    }
  } catch (error: any) {
    modelEditorStatus.value = 'failed'
    modelEditorMessage.value = TEST_FAILURE_MESSAGE
    settingsError.value = ''
  } finally {
    settingsTesting.value = false
  }
}

async function removeSelectedModelProfile() {
  if (selectedModelId.value === DEFAULT_MODEL_ID) return
  settingsError.value = ''
  settingsSuccess.value = ''
  try {
    const removingId = selectedModelId.value
    const wasActive = activeModelId.value === removingId
    modelProfiles.value = modelProfiles.value.filter(item => item.id !== removingId)
    if (wasActive) {
      activeModelId.value = DEFAULT_MODEL_ID
      localStorage.setItem(ACTIVE_MODEL_PROFILE_KEY, DEFAULT_MODEL_ID)
    }
    persistModelProfiles()
    if (wasActive) {
      const data = await knowledgeApi.resetRuntimeModelSettings()
      syncRuntimeSelection(data, DEFAULT_MODEL_ID)
      settingsSuccess.value = '已删除自定义模型，并切回默认配置。'
    } else {
      selectModelProfile(modelProfiles.value[0]?.id || DEFAULT_MODEL_ID)
      settingsSuccess.value = '自定义模型已删除。'
    }
  } catch (error: any) {
    settingsError.value = error?.message || '删除自定义模型失败'
  }
}

function removeModelProfile(id: string, event?: MouseEvent) {
  event?.stopPropagation()
  deletingModelProfileId.value = id
}

async function confirmDeleteModelProfile() {
  if (!deletingModelProfileId.value) return
  selectedModelId.value = deletingModelProfileId.value
  deletingModelProfileId.value = ''
  await removeSelectedModelProfile()
}

function cancelDeleteModelProfile() {
  deletingModelProfileId.value = ''
}

function toggleSettingsMenu(event?: MouseEvent) {
  event?.stopPropagation()
  showSettingsMenu.value = !showSettingsMenu.value
  if (showSettingsMenu.value && canManageWorkspace.value) {
    void loadRuntimeModelSettings()
  }
}

function openModelSettings(event?: MouseEvent) {
  if (!canManageWorkspace.value) return
  event?.stopPropagation()
  showSettingsMenu.value = false
  showModelSettings.value = true
  settingsSuccess.value = ''
  void loadRuntimeModelSettings()
}

function closeModelSettings() {
  showModelSettings.value = false
  showModelProfileEditor.value = false
  deletingModelProfileId.value = ''
  settingsError.value = ''
  settingsSuccess.value = ''
  resetModelEditorState()
}

function handleDemoLogout(event?: MouseEvent) {
  event?.stopPropagation()
  showSettingsMenu.value = false
  showModelSettings.value = false
  store.handleLogoutCleanup()
  emit('logout')
}

function openKnowledgeBackstage(event?: MouseEvent) {
  if (!canManageWorkspace.value) return
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

function askRenameSession(session: Session, event: MouseEvent) {
  event.stopPropagation()
  openMenuId.value = ''
  renamingSessionId.value = session.session_id
  renameDraft.value = getTitle(session)
  renameError.value = ''
  nextTick(() => {
    const input = document.querySelector('.rename-input') as HTMLInputElement | null
    input?.focus()
    input?.select()
  })
}

async function confirmRenameSession() {
  if (!renamingSessionId.value || !renameDraft.value.trim()) {
    renameError.value = '请输入新的会话名称'
    return
  }
  renamingBusy.value = true
  renameError.value = ''
  try {
    await store.renameSession(renamingSessionId.value, renameDraft.value)
    renamingSessionId.value = ''
    renameDraft.value = ''
    focusInput()
  } catch (error: any) {
    renameError.value = error?.message || '重命名失败，请稍后重试'
  } finally {
    renamingBusy.value = false
  }
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

function cancelRenameSession() {
  renamingSessionId.value = ''
  renameDraft.value = ''
  renameError.value = ''
}

function handleGlobalClick() {
  openMenuId.value = ''
  showSettingsMenu.value = false
}

watch(() => store.currentMessages.length, scrollToBottom)
watch(() => store.currentMessages.length, length => {
  if (length > 0) showEmptyIntroImmediately()
})
watch(() => store.currentId, () => {
  scrollToBottom()
  focusInput()
  if (!store.currentMessages.length && !isStreamingIntro.value) showEmptyIntroImmediately()
})
watch(() => props.kbVersion, () => {
  void store.fetchRecommendations()
})

onMounted(async () => {
  store.initialize(props.authRole === 'guest' ? 'guest' : 'member', props.authRole === 'guest' && props.resetGuestState)
  await store.refreshSessions()
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
  clearIntroTimer()
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
              <div class="session-meta">{{ formatDate(session.updated_at) }} · {{ getMessageCount(session) }} 条</div>
            </div>
            <div class="session-menu-wrap" @click.stop>
              <button class="session-menu-btn" type="button" aria-label="会话操作" @click="toggleSessionMenu(session.session_id, $event)">⋯</button>
              <Transition name="fade">
                <div v-if="openMenuId === session.session_id" class="session-menu">
                  <button class="session-menu-item" type="button" @click="askRenameSession(session, $event)">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M4 17.2V20h2.8l8.3-8.3-2.8-2.8L4 17.2zm10.5-9.7 2.8 2.8 1.4-1.4a1 1 0 0 0 0-1.4l-1.4-1.4a1 1 0 0 0-1.4 0l-1.4 1.4z" />
                    </svg>
                    <span>重命名</span>
                  </button>
                  <button class="session-menu-item danger" type="button" @click="askDeleteSession(session.session_id, $event)">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 7h2v8h-2v-8zm4 0h2v8h-2v-8zM7 10h2v8H7v-8z" />
                    </svg>
                    <span>删除会话</span>
                  </button>
                </div>
              </Transition>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-dock" @click.stop>
        <button class="settings-entry" type="button" @click="toggleSettingsMenu($event)">
          <div class="settings-avatar">{{ props.authRole === 'root' ? '管' : '游' }}</div>
          <div class="settings-copy">
            <strong>{{ props.displayName }}</strong>
            <span>{{ props.displayEmail }}</span>
          </div>
          <span class="settings-caret">{{ showSettingsMenu ? '▴' : '▾' }}</span>
        </button>

        <Transition name="fade">
          <div v-if="showSettingsMenu" class="settings-menu">
            <button v-if="canManageWorkspace" class="settings-menu-item" type="button" @click="openKnowledgeBackstage($event)">
              <div>
                <strong>知识库后台管理</strong>
                <span>上传、查看和维护旅游资料</span>
              </div>
            </button>

            <button v-if="canManageWorkspace" class="settings-menu-item" type="button" @click="openModelSettings($event)">
              <div>
                <strong>模型切换</strong>
                <span>OpenAI 兼容接口</span>
              </div>
            </button>

            <button class="settings-menu-item danger" type="button" @click="handleDemoLogout($event)">
              <div>
                <strong>退出登录</strong>
                <span>退出当前账号并返回登录页</span>
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
              <span class="toggle-copy-reserve" aria-hidden="true">
                {{ toggleReserveCopy }}
              </span>
              <span class="toggle-copy-live">
                当前状态：
                <b class="toggle-state" :class="store.ragEnabled ? 'enabled' : 'disabled'">
                  {{ store.ragEnabled ? '已开启' : '已关闭' }}
                </b>
                {{ store.ragEnabled ? '，优先命中旅游知识库' : '，仅进行普通AI问答' }}
              </span>
            </div>
            <button class="hero-btn ghost toggle-btn" @click="toggleRagState($event)">
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
          <div class="empty-title">{{ emptyTitleText }}</div>
          <div class="empty-desc">{{ emptyDescText }}</div>
        </div>

        <div v-else ref="messagesContainer" class="messages">
          <div v-for="(msg, index) in store.currentMessages" :key="`${msg.timestamp}_${index}`" class="message" :class="[msg.role, { pending: isAssistantPending(msg) }]">
            <div class="bubble">
              <div v-if="msg.role === 'assistant'" class="message-topline">
                <span v-if="!showWaitingSkeleton(msg) && displayThinkingTime(msg)" class="thinking-pill">思考 {{ displayThinkingTime(msg).toFixed(1) }}s</span>
                <span v-if="msg.ragReferenced && !isAssistantPending(msg)" class="knowledge-badge">知识库已命中</span>
              </div>

              <div v-if="showWaitingSkeleton(msg)" class="waiting-state">
                <div class="waiting-header">
                  <span class="thinking-pill">{{ waitingLabel(msg) }}</span>
                </div>
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
        <div v-if="composerModelWarning" class="composer-feedback error">{{ composerModelWarning }}</div>
      </footer>
    </main>

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showModelSettings" class="settings-modal-overlay">
          <div class="settings-modal">
            <div class="settings-modal-header">
              <div>
                <div class="settings-modal-eyebrow">Model Routing</div>
                <h3>模型切换</h3>
                <p>管理默认配置和自定义模型。默认配置仅展示状态说明，自定义模型可按需编辑和切换。</p>
              </div>
              <button class="settings-modal-close" type="button" aria-label="关闭模型切换" @click="closeModelSettings">
                ×
              </button>
            </div>

            <div class="model-panel standalone model-switch-panel">
              <div class="model-warning">{{ runtimeSettings.warning }}</div>

              <div class="model-switch-layout" :class="{ blurred: showModelProfileEditor }">
                <div class="model-profile-stack">
                  <div class="model-profile-list">
                  <button
                    class="model-profile-card"
                    :class="{ active: activeModelId === DEFAULT_MODEL_ID }"
                    type="button"
                    @click="activateDefaultModel($event)"
                  >
                    <div class="model-profile-main">
                      <div>
                        <strong>默认配置</strong>
                        <span>系统托管，直接可用</span>
                      </div>
                      <em>{{ activeModelId === DEFAULT_MODEL_ID ? '当前使用中' : '' }}</em>
                    </div>
                  </button>

                  <div
                    v-for="profile in modelProfiles"
                    :key="profile.id"
                    class="model-profile-card custom with-actions"
                    :class="{ active: activeModelId === profile.id }"
                    @click="activateCustomModel(profile.id, $event)"
                  >
                    <div class="model-profile-main">
                      <div>
                        <strong>{{ profile.model || profile.name || '未填写模型名' }}</strong>
                      </div>
                      <em>
                        {{
                          activeModelId === profile.id
                            ? '当前使用中'
                            : profile.last_test_status === 'failed'
                                ? '测试失败'
                                : profile.last_test_status === 'idle'
                                  ? '待测试'
                                  : ''
                        }}
                      </em>
                    </div>

                    <div class="model-card-actions">
                      <button class="model-card-action" type="button" @click="openModelProfileEditorFor(profile.id, $event)">编辑</button>
                      <button class="model-card-action danger" type="button" @click="removeModelProfile(profile.id, $event)">删除</button>
                    </div>
                  </div>
                  </div>
                  <button class="add-model-btn" type="button" @click="createCustomModelProfile">新增自定义</button>
                </div>
              </div>

              <div v-if="!showModelProfileEditor && settingsError" class="settings-feedback error">{{ settingsError }}</div>
              <div v-else-if="!showModelProfileEditor && settingsSuccess" class="settings-feedback success">{{ settingsSuccess }}</div>
            </div>

            <Transition name="fade">
              <div v-if="showModelProfileEditor" class="model-editor-popover">
                <div class="model-editor-popover-card">
                  <div class="model-editor-popover-head">
                    <div>
                      <div class="settings-modal-eyebrow">Custom Model</div>
                      <h4>{{ modelForm.model || '新增自定义模型' }}</h4>
                    </div>
                    <button class="settings-modal-close" type="button" aria-label="关闭自定义模型配置" @click="closeModelProfileEditor">
                      ×
                    </button>
                  </div>

                  <label class="field">
                    <span>API Key</span>
                    <input v-model="modelForm.api_key" type="text" placeholder="sk-..." />
                  </label>

                  <label class="field">
                    <span>Base URL</span>
                    <input v-model="modelForm.base_url" type="text" placeholder="https://api.openai.com/v1" />
                  </label>

                  <label class="field">
                    <span>模型名</span>
                    <input v-model="modelForm.model" type="text" placeholder="gpt-4.1-mini" />
                  </label>

                  <div v-if="modelEditorMessage" class="model-test-hint" :class="modelEditorStatus">
                    {{ modelEditorMessage }}
                  </div>

                  <div v-if="settingsError" class="settings-feedback error">{{ settingsError }}</div>
                  <div v-else-if="settingsSuccess" class="settings-feedback success">{{ settingsSuccess }}</div>

                  <div class="settings-modal-actions model-editor-footer">
                    <button class="editor-action" type="button" :disabled="settingsTesting" @click="testSelectedModelProfile">
                      {{ settingsTesting ? '测试中...' : '测试' }}
                    </button>
                    <button class="save-model-btn" type="button" :disabled="settingsSaving" @click="saveRuntimeModelSettings()">
                      {{ settingsSaving ? '保存中...' : '保存' }}
                    </button>
                    <button class="confirm-btn ghost long" type="button" @click="closeModelProfileEditor">取消</button>
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="deletingModelProfileId" class="confirm-overlay" @click.self="cancelDeleteModelProfile">
          <div class="confirm-card">
            <div class="confirm-eyebrow">Model Action</div>
            <h3>删除这个自定义模型？</h3>
            <p>删除后，这条自定义模型配置会从当前列表移除；如果它正在使用中，也会切回默认配置。</p>
            <div class="confirm-actions">
              <button class="confirm-btn ghost" type="button" @click="cancelDeleteModelProfile">取消</button>
              <button class="confirm-btn danger" type="button" @click="confirmDeleteModelProfile">确认删除</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="renamingSessionId" class="confirm-overlay" @click.self="cancelRenameSession">
          <div class="confirm-card rename-card">
            <div class="confirm-eyebrow">Session Action</div>
            <h3>重命名会话</h3>
            <p>给这段会话换一个更容易识别的标题，方便后续继续查看。</p>
            <label class="rename-field">
              <span>会话名称</span>
              <input v-model="renameDraft" class="rename-input" type="text" maxlength="40" placeholder="输入新的会话名称" @keydown.enter.prevent="confirmRenameSession" />
            </label>
            <div v-if="renameError" class="settings-feedback error">{{ renameError }}</div>
            <div class="confirm-actions">
              <button class="confirm-btn ghost" type="button" @click="cancelRenameSession">取消</button>
              <button class="confirm-btn" type="button" :disabled="renamingBusy" @click="confirmRenameSession">
                {{ renamingBusy ? '保存中...' : '确认重命名' }}
              </button>
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

.settings-menu-note {
  margin-bottom: 10px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(14, 124, 134, 0.08);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.7;
  box-shadow: inset 0 0 0 1px rgba(14, 124, 134, 0.12);
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

.model-switch-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 14px;
  min-height: 0;
  height: 100%;
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

.model-switch-layout {
  position: relative;
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
  align-items: start;
  min-height: 0;
  height: 100%;
  transition:
    filter 180ms ease,
    opacity 180ms ease;
}

.model-switch-layout.blurred {
  filter: blur(5px);
  opacity: 0.38;
  pointer-events: none;
  user-select: none;
}

.model-profile-list {
  display: grid;
  gap: 10px;
  align-content: start;
  min-height: 0;
  max-height: none;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 8px 40px 0;
  margin-right: -4px;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scroll-padding-bottom: 48px;
}

.model-profile-stack {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 12px;
  min-height: 0;
  height: 100%;
  max-height: none;
  overflow: hidden;
}

.model-profile-list::-webkit-scrollbar {
  width: 8px;
}

.model-profile-list::-webkit-scrollbar-track {
  margin-block: 6px;
  background: transparent;
}

.model-profile-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(128, 92, 53, 0.26);
  border: 2px solid rgba(255, 250, 242, 0.95);
}

.model-profile-list::-webkit-scrollbar-thumb:hover {
  background: rgba(128, 92, 53, 0.4);
}

.model-profile-card,
.add-model-btn {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid rgba(128, 92, 53, 0.12);
  border-radius: 18px;
  padding: 14px 16px;
  background: #fffdf9;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 160ms ease,
    background 160ms ease;
}

.model-profile-card {
  min-height: 84px;
  overflow: hidden;
  scroll-margin-bottom: 28px;
}

.model-profile-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.model-profile-card.with-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: default;
  position: relative;
  min-height: 90px;
  padding: 12px 16px 10px;
  align-items: flex-start;
}

.model-profile-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 84px;
  width: 100%;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  min-height: 24px;
}

.model-profile-main > div {
  min-width: 0;
  flex: 1;
}

.model-profile-card.with-actions .model-profile-main {
  grid-template-columns: 1fr;
  padding-right: 92px;
}

.model-profile-card.with-actions .model-profile-main em {
  position: absolute;
  top: 50%;
  right: 16px;
  width: 84px;
  transform: translateY(-50%);
}

.model-profile-card strong,
.model-editor-popover-head h4 {
  display: block;
}

.model-profile-card span {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.model-profile-card em {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-height: 24px;
  font-style: normal;
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: right;
  white-space: nowrap;
}

.model-profile-card.active {
  border-color: rgba(14, 124, 134, 0.24);
  background: rgba(238, 249, 249, 0.98);
  box-shadow: inset 0 0 0 1px rgba(14, 124, 134, 0.16);
}

.model-profile-card:hover,
.add-model-btn:hover {
  border-color: rgba(14, 124, 134, 0.2);
}

.add-model-btn {
  display: flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  background: rgba(255, 248, 238, 0.98);
  color: #9b5b19;
  font-weight: 700;
}

.model-editor-popover {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  pointer-events: none;
}

.model-editor-popover-card {
  width: min(520px, 100%);
  height: min(438px, 100%);
  max-height: min(438px, 100%);
  overflow: auto;
  padding: 16px;
  border-radius: 22px;
  background: rgba(255, 252, 246, 0.98);
  border: 1px solid rgba(128, 92, 53, 0.14);
  box-shadow: 0 26px 60px rgba(35, 24, 16, 0.22);
  pointer-events: auto;
}

.model-editor-popover-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.model-editor-popover-head h4 {
  margin: 0;
  font-size: 20px;
}

.editor-action {
  border: 1px solid rgba(128, 92, 53, 0.12);
  border-radius: 14px;
  padding: 8px 12px;
  background: #fffaf4;
  color: var(--text-secondary);
  font-weight: 700;
  cursor: pointer;
}

.editor-action.primary {
  background: linear-gradient(135deg, #0f7d88, #0b626a);
  border: none;
  color: #f4fffd;
}

.editor-action.danger {
  color: var(--red);
}

.model-card-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 88px));
  gap: 8px;
  justify-content: start;
  margin-top: 2px;
  padding-bottom: 0;
  justify-self: start;
  align-self: flex-start;
}

.model-card-action {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(128, 92, 53, 0.12);
  border-radius: 12px;
  padding: 7px 10px;
  background: #fffaf4;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.model-card-action.danger {
  color: var(--red);
}

.model-test-hint {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 14px;
  font-size: 12px;
  line-height: 1.6;
}

.model-test-hint.success {
  background: rgba(31, 143, 87, 0.08);
  color: var(--green);
}

.model-test-hint.failed {
  background: rgba(191, 75, 61, 0.08);
  color: var(--red);
}

.model-test-hint.idle {
  background: rgba(221, 139, 47, 0.08);
  color: #9b5b19;
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
  border: none;
  border-radius: 14px;
  padding: 9px 14px;
  background: linear-gradient(135deg, #0f7d88, #0b626a);
  color: #f4fffd;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 10px 20px rgba(15, 125, 136, 0.18);
}

.model-editor-footer {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.model-editor-footer .editor-action,
.model-editor-footer .save-model-btn,
.model-editor-footer .confirm-btn {
  width: 100%;
  margin-top: 0;
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.session-menu-btn:hover {
  background: rgba(128, 92, 53, 0.1);
  color: var(--text);
}

.session-menu-btn:active {
  transform: translateY(1px);
}

.session-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 3;
  min-width: 132px;
  padding: 10px;
  border-radius: 18px;
  border: 1px solid rgba(128, 92, 53, 0.14);
  background: linear-gradient(180deg, rgba(255, 253, 248, 0.99), rgba(251, 244, 235, 0.98));
  box-shadow:
    0 20px 40px rgba(40, 30, 18, 0.14),
    inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.session-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  white-space: nowrap;
  border: none;
  border-radius: 14px;
  padding: 11px 14px;
  background: linear-gradient(180deg, rgba(255, 238, 235, 0.98), rgba(255, 228, 222, 0.98));
  color: #b54639;
  cursor: pointer;
  font-weight: 700;
  box-shadow:
    inset 0 0 0 1px rgba(205, 91, 74, 0.16),
    0 8px 18px rgba(179, 61, 53, 0.08);
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
}

.session-menu-item + .session-menu-item {
  margin-top: 8px;
}

.session-menu-item:hover {
  filter: saturate(1.02);
  transform: translateY(-1px);
  box-shadow:
    inset 0 0 0 1px rgba(205, 91, 74, 0.22),
    0 12px 22px rgba(179, 61, 53, 0.12);
}

.session-menu-item svg,
.icon-action svg {
  width: 16px;
  height: 16px;
  fill: currentColor;
}

.session-menu-item.danger {
  color: #b54639;
}

.session-menu-item:not(.danger) {
  background: linear-gradient(180deg, rgba(239, 248, 248, 0.98), rgba(226, 242, 242, 0.98));
  color: #0f6e76;
  box-shadow:
    inset 0 0 0 1px rgba(14, 124, 134, 0.12),
    0 8px 18px rgba(14, 124, 134, 0.08);
}

.chat-main {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  min-height: 0;
  min-width: 0;
  padding: 18px;
  gap: 10px;
}

.hero {
  display: flex;
  justify-content: space-between;
  align-items: stretch;
  gap: 20px;
  min-height: clamp(134px, 19vh, 148px);
  padding: 17px 20px;
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
  justify-content: flex-start;
  flex: 0 0 auto;
  width: auto;
  min-width: 0;
}

.toggle-card {
  width: fit-content;
  max-width: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 22px;
  background: #fffaf2;
  border: 1px solid rgba(128, 92, 53, 0.12);
}

.toggle-copy {
  position: relative;
  min-height: 0;
  width: 100%;
  min-width: 31ch;
  max-width: 100%;
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
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 18px;
  height: 18px;
  white-space: nowrap;
}

.toggle-copy-reserve {
  visibility: hidden;
}

.toggle-copy-live {
  position: absolute;
  inset: auto 0 0 0;
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
  min-height: 44px;
  flex: 0 0 44px;
}

.hero-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 18px;
  padding: 14px 16px;
  font-weight: 700;
  line-height: 1.15;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.22s ease, filter 0.22s ease, background 0.22s ease;
}

.hero-btn:hover {
  filter: saturate(1.04);
}

.hero-btn:active {
  transform: translateY(1px) scale(0.992);
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
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.72),
    0 8px 18px rgba(14, 124, 134, 0.08);
}

.recommend-strip {
  min-height: 136px;
  max-height: 148px;
  padding: 14px 16px 16px;
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
  max-width: 100%;
  line-height: 1.8;
  color: var(--text-secondary);
  white-space: nowrap;
}

.messages {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scrollbar-gutter: stable both-edges;
  overscroll-behavior: contain;
  padding: 18px clamp(18px, 2.3vw, 28px) 34px;
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
  padding: 14px 18px;
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
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
}

.thinking-pill {
  background: rgba(221, 139, 47, 0.12);
  color: #9b5b19;
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

.waiting-header {
  display: flex;
  align-items: center;
  min-height: 24px;
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
.message-text :deep(h4),
.message-text :deep(p),
.message-text :deep(ul),
.message-text :deep(blockquote),
.message-text :deep(hr),
.message-text :deep(.md-table-wrap) {
  margin: 0;
}

.message-text :deep(h2),
.message-text :deep(h3),
.message-text :deep(h4) {
  margin-top: 10px;
  color: inherit;
  font-size: 16px;
  line-height: 1.6;
}

.message-text :deep(h2):first-child,
.message-text :deep(h3):first-child,
.message-text :deep(h4):first-child,
.message-text :deep(p):first-child,
.message-text :deep(ul):first-child,
.message-text :deep(blockquote):first-child,
.message-text :deep(.md-table-wrap):first-child {
  margin-top: 0;
}

.message-text :deep(p + p),
.message-text :deep(p + ul),
.message-text :deep(p + .md-table-wrap),
.message-text :deep(p + blockquote),
.message-text :deep(ul + p),
.message-text :deep(ul + blockquote),
.message-text :deep(.md-table-wrap + p),
.message-text :deep(.md-table-wrap + ul),
.message-text :deep(.md-table-wrap + blockquote),
.message-text :deep(h2 + p),
.message-text :deep(h3 + p),
.message-text :deep(h4 + p),
.message-text :deep(h2 + blockquote),
.message-text :deep(h3 + blockquote),
.message-text :deep(h4 + blockquote),
.message-text :deep(h2 + ul),
.message-text :deep(h3 + ul),
.message-text :deep(h4 + ul),
.message-text :deep(h2 + .md-table-wrap),
.message-text :deep(h3 + .md-table-wrap),
.message-text :deep(h4 + .md-table-wrap),
.message-text :deep(blockquote + p),
.message-text :deep(blockquote + ul),
.message-text :deep(blockquote + .md-table-wrap),
.message-text :deep(blockquote + blockquote),
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

.message-text :deep(blockquote) {
  padding: 12px 14px;
  border-left: 3px solid rgba(74, 113, 255, 0.34);
  background: rgba(243, 246, 255, 0.92);
  border-radius: 0 14px 14px 0;
  color: rgba(39, 47, 79, 0.92);
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
  padding: 12px 16px 8px;
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255, 250, 242, 0.96), rgba(250, 243, 231, 0.88)),
    radial-gradient(circle at 20% 0%, rgba(14, 124, 134, 0.06), transparent 32%);
  border: 1px solid rgba(128, 92, 53, 0.1);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    0 14px 30px rgba(70, 45, 22, 0.06);
}

.composer-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
}

.composer-feedback {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.6;
}

.composer-feedback.error {
  color: var(--red);
}

.composer-row input {
  min-width: 0;
  height: 52px;
  padding: 0 16px;
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
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  width: min(760px, 100%);
  height: min(720px, calc(100vh - 40px));
  max-height: min(720px, calc(100vh - 40px));
  padding: 24px;
  border-radius: 28px;
  background: rgba(255, 250, 242, 0.985);
  border: 1px solid rgba(128, 92, 53, 0.14);
  box-shadow: 0 24px 60px rgba(35, 24, 16, 0.18);
  overflow: hidden;
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

.settings-modal-actions.vertical {
  flex-direction: column;
  align-items: stretch;
}

.rename-card {
  width: min(460px, 100%);
}

.rename-field {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.rename-field span {
  font-size: 12px;
  color: var(--text-secondary);
}

.rename-input {
  width: 100%;
  height: 44px;
  padding: 0 14px;
  border-radius: 14px;
  border: 1px solid rgba(128, 92, 53, 0.16);
  background: #fffdf8;
  color: var(--text);
}

.rename-input:focus {
  outline: none;
  border-color: rgba(14, 124, 134, 0.28);
  box-shadow: 0 0 0 4px rgba(14, 124, 134, 0.08);
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

.confirm-btn.ghost.long {
  width: 100%;
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

  .model-switch-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1320px) {
  .chat-shell {
    gap: 14px;
  }

  .hero {
    flex-wrap: wrap;
    gap: 14px;
  }

  .hero-actions {
    flex: 1 1 100%;
    width: 100%;
    min-width: 0;
  }

  .toggle-card {
    min-height: 116px;
    padding: 14px;
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
    gap: 10px;
  }

  .hero {
    min-height: 126px;
    padding: 16px;
  }

  .recommend-strip {
    min-height: 120px;
    max-height: 132px;
    padding: 12px 14px 14px;
  }

  .messages {
    padding-bottom: 60px;
  }

  .composer {
    padding: 12px 14px 8px;
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
  .hero p {
    display: none;
  }

  .hero {
    min-height: 0;
    padding: 14px;
  }

  .hero h1,
  .hero.condensed h1 {
    margin-bottom: 0;
    font-size: clamp(26px, 2.8vw, 30px);
  }

  .recommend-strip {
    min-height: 136px;
    max-height: 146px;
  }

  .recommend-row {
    margin-top: 8px;
  }

  .messages {
    padding-top: 18px;
    padding-bottom: 54px;
  }

  .composer-row input {
    height: 48px;
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
    gap: 10px;
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
    min-height: 640px;
    max-height: calc(100vh - 20px);
  }

  .settings-modal-header {
    gap: 12px;
  }

  .settings-modal-header h3 {
    font-size: 30px;
  }

  .model-editor-popover {
    inset: 0;
    padding: 18px;
  }

  .model-editor-popover-head {
    flex-direction: column;
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
