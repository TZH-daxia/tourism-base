<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

import { knowledgeApi, type TaskStatus } from '../../api/knowledge'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: []; updated: [] }>()

const tasks = ref<TaskStatus[]>([])
const uploading = ref(false)
const loadingTasks = ref(false)
const errorMsg = ref('')
const fileInput = ref<HTMLInputElement>()
const pollingTimer = ref<number | null>(null)
const searchKeyword = ref('')
const statusFilter = ref<'all' | 'processing' | 'completed' | 'failed'>('all')
const collapsedTaskIds = ref<string[]>([])
const initializedCollapsedTaskIds = ref<string[]>([])
const deletingTaskId = ref('')
const deletingTaskName = ref('')

const summary = computed(() => ({
  total: tasks.value.length,
  processing: tasks.value.filter(item => item.status === 'processing').length,
  completed: tasks.value.filter(item => item.status === 'completed').length,
  failed: tasks.value.filter(item => item.status === 'failed' || item.status === 'error').length,
}))

async function loadTasks() {
  loadingTasks.value = true
  errorMsg.value = ''
  try {
    const data = await knowledgeApi.getTasks({
      search: searchKeyword.value.trim(),
      status: statusFilter.value === 'all' ? '' : statusFilter.value,
    })
    tasks.value = Array.isArray(data) ? data : []
    const currentTaskIds = new Set(tasks.value.map(item => item.task_id))
    collapsedTaskIds.value = collapsedTaskIds.value.filter(id => currentTaskIds.has(id))
    initializedCollapsedTaskIds.value = initializedCollapsedTaskIds.value.filter(id => currentTaskIds.has(id))
    for (const task of tasks.value) {
      if (!task.timeline?.length) continue
      if (!initializedCollapsedTaskIds.value.includes(task.task_id)) {
        initializedCollapsedTaskIds.value = [...initializedCollapsedTaskIds.value, task.task_id]
        collapsedTaskIds.value = [...collapsedTaskIds.value, task.task_id]
      }
    }
  } catch (error: any) {
    errorMsg.value = error?.message || '获取已上传文件失败，请稍后重试。'
  } finally {
    loadingTasks.value = false
  }
}

async function refreshTasks() {
  await loadTasks()
  if (!props.show) return
  if (tasks.value.some(item => item.status === 'processing')) startPolling()
  else stopPolling()
}

function startPolling() {
  if (pollingTimer.value) return
  pollingTimer.value = window.setInterval(async () => {
    await loadTasks()
    if (!tasks.value.some(item => item.status === 'processing')) stopPolling()
  }, 2500)
}

function stopPolling() {
  if (pollingTimer.value) {
    window.clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

watch(
  () => props.show,
  async value => {
    if (value) await refreshTasks()
    else stopPolling()
  },
)

watch([searchKeyword, statusFilter], () => {
  if (props.show) void refreshTasks()
})

onUnmounted(stopPolling)

async function handleFile(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!ext || !['pdf', 'md'].includes(ext)) {
    errorMsg.value = '仅支持 PDF 和 Markdown 文件。'
    return
  }

  errorMsg.value = ''
  uploading.value = true
  try {
    await knowledgeApi.upload(file)
    await refreshTasks()
    emit('updated')
  } catch (error: any) {
    errorMsg.value = error?.message || '上传失败，请稍后重试。'
  } finally {
    uploading.value = false
  }
}

function onFileInput(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) void handleFile(file)
  ;(event.target as HTMLInputElement).value = ''
}

async function deleteTask(taskId: string) {
  try {
    await knowledgeApi.deleteTask(taskId)
    await refreshTasks()
    emit('updated')
  } catch (error: any) {
    errorMsg.value = error?.message || '删除失败，请稍后重试。'
  }
}

function isTimelineCollapsed(taskId: string) {
  return collapsedTaskIds.value.includes(taskId)
}

function toggleTimeline(taskId: string) {
  if (isTimelineCollapsed(taskId)) {
    collapsedTaskIds.value = collapsedTaskIds.value.filter(id => id !== taskId)
  } else {
    collapsedTaskIds.value = [...collapsedTaskIds.value, taskId]
  }
}

function askDeleteTask(taskId: string, fileName: string) {
  deletingTaskId.value = taskId
  deletingTaskName.value = fileName
}

function cancelDeleteTask() {
  deletingTaskId.value = ''
  deletingTaskName.value = ''
}

async function confirmDeleteTask() {
  if (!deletingTaskId.value) return
  await deleteTask(deletingTaskId.value)
  cancelDeleteTask()
}

function pct(task: TaskStatus) {
  if (task.status === 'completed') return 100
  return Math.min(99, Math.max(6, Math.round((task.progress || 0) * 100)))
}

function tone(task: TaskStatus) {
  if (task.status === 'completed') return 'success'
  if (task.status === 'failed' || task.status === 'error') return 'danger'
  return 'pending'
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="show" class="overlay" @click.self="emit('close')">
        <div class="panel">
          <header class="panel-head">
            <div>
              <div class="eyebrow">Knowledge Flow</div>
              <h2>知识库后台管理</h2>
              <p>从文件入队、切分、向量生成到最终入库，整个上传流程都会在这里持续显示。</p>
            </div>
            <button class="close-btn" @click="emit('close')">关闭</button>
          </header>

          <div class="panel-body">
            <section class="stats-grid">
              <div class="stat-card"><span>总文件</span><strong>{{ summary.total }}</strong></div>
              <div class="stat-card sea"><span>处理中</span><strong>{{ summary.processing }}</strong></div>
              <div class="stat-card sun"><span>已完成</span><strong>{{ summary.completed }}</strong></div>
              <div class="stat-card sand"><span>失败</span><strong>{{ summary.failed }}</strong></div>
            </section>

            <section class="upload-box" @click="fileInput?.click()">
              <div class="upload-copy">
                <strong>{{ uploading ? '资料上传中...' : '拖拽或点击上传旅游资料' }}</strong>
                <span>支持 PDF 和 Markdown。文件名前两到四个字会参与城市识别，再按交通、景点、酒店、美食、线路等类型写入知识库。</span>
              </div>
              <button class="upload-btn" type="button">选择文件</button>
              <input ref="fileInput" type="file" accept=".pdf,.md" hidden @change="onFileInput" />
            </section>

            <section class="toolbar">
              <input v-model="searchKeyword" type="text" placeholder="按文件名搜索" />
              <div class="filters">
                <button :class="{ active: statusFilter === 'all' }" @click="statusFilter = 'all'">全部</button>
                <button :class="{ active: statusFilter === 'processing' }" @click="statusFilter = 'processing'">处理中</button>
                <button :class="{ active: statusFilter === 'completed' }" @click="statusFilter = 'completed'">已完成</button>
                <button :class="{ active: statusFilter === 'failed' }" @click="statusFilter = 'failed'">失败</button>
              </div>
            </section>

            <div v-if="errorMsg" class="error-box">
              <span>{{ errorMsg }}</span>
              <button class="retry-btn" type="button" @click="refreshTasks">重新获取</button>
            </div>

            <section class="task-list">
              <div v-if="loadingTasks && !tasks.length" class="empty-box">
                正在读取已上传文件，请稍候...
              </div>

              <article v-for="task in tasks" :key="task.task_id" class="task-card">
                <div class="task-top">
                  <div>
                    <h3>{{ task.file_name }}</h3>
                    <div class="task-meta">
                      <span>{{ task.city || '未识别城市' }}</span>
                      <span>{{ task.doc_type || '待识别类型' }}</span>
                      <span>{{ task.stats?.chunks || 0 }} chunks</span>
                    </div>
                  </div>
                  <div class="task-actions">
                    <span class="status-pill" :class="tone(task)">{{ task.current_step || task.status }}</span>
                    <button v-if="task.timeline?.length" class="ghost-btn" type="button" @click="toggleTimeline(task.task_id)">
                      {{ isTimelineCollapsed(task.task_id) ? '展开过程' : '折叠过程' }}
                    </button>
                    <button class="delete-btn" type="button" @click="askDeleteTask(task.task_id, task.file_name)">删除</button>
                  </div>
                </div>

                <div class="progress-bar">
                  <div class="progress-fill" :style="{ width: `${pct(task)}%` }"></div>
                </div>

                <div v-if="task.suggested_queries?.length" class="recommend-tags">
                  <span v-for="query in task.suggested_queries" :key="query">{{ query }}</span>
                </div>

                <div v-if="task.timeline?.length && !isTimelineCollapsed(task.task_id)" class="timeline">
                  <div v-for="(item, index) in task.timeline.slice(-5)" :key="`${task.task_id}-${index}`" class="timeline-item">
                    <div class="timeline-dot" :class="item.status"></div>
                    <div>
                      <strong>{{ item.step }}</strong>
                      <span>{{ Math.round((item.progress || 0) * 100) }}%</span>
                      <p v-if="item.detail">{{ item.detail }}</p>
                    </div>
                  </div>
                </div>
              </article>

              <div v-if="!loadingTasks && !tasks.length" class="empty-box">
                暂无匹配的知识库文件。上传后，这里会展示每一份文件的处理进度和最终状态。
              </div>
            </section>
          </div>
        </div>
      </div>
    </Transition>

    <Transition name="fade">
      <div v-if="deletingTaskId" class="overlay confirm-overlay" @click.self="cancelDeleteTask">
        <div class="confirm-card">
          <div class="eyebrow">Delete Confirm</div>
          <h3>删除这份资料？</h3>
          <p>
            删除后，资料卡片和对应知识库数据都会被移除。
            <strong>{{ deletingTaskName }}</strong>
          </p>
          <div class="confirm-actions">
            <button class="close-btn ghost" type="button" @click="cancelDeleteTask">取消</button>
            <button class="danger-btn" type="button" @click="confirmDeleteTask">确认删除</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(43, 31, 16, 0.34);
  backdrop-filter: blur(8px);
}

.panel {
  width: min(1120px, 100%);
  max-height: min(92vh, 980px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 24px 24px 18px;
  border-radius: 28px;
  background: rgba(255, 250, 241, 0.96);
  border: 1px solid rgba(128, 92, 53, 0.16);
  box-shadow: 0 30px 80px rgba(43, 31, 16, 0.2);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
  padding-right: 8px;
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  margin-top: 16px;
  padding-right: 8px;
}

.eyebrow {
  color: var(--primary);
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.panel-head h2 {
  margin: 10px 0 8px;
  font-family: 'Cormorant Garamond', serif;
  font-size: 42px;
}

.panel-head p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.close-btn,
.upload-btn,
.delete-btn,
.retry-btn,
.filters button {
  cursor: pointer;
}

.close-btn {
  border: 1px solid rgba(128, 92, 53, 0.14);
  border-radius: 14px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.7);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin: 0 0 18px;
}

.stat-card {
  padding: 16px 18px;
  border-radius: 18px;
  background: #fffef9;
  border: 1px solid rgba(128, 92, 53, 0.08);
}

.stat-card span {
  display: block;
  color: var(--text-tertiary);
  font-size: 12px;
}

.stat-card strong {
  display: block;
  margin-top: 10px;
  font-size: 28px;
}

.sea {
  background: rgba(14, 124, 134, 0.08);
}

.sun {
  background: rgba(221, 139, 47, 0.1);
}

.sand {
  background: rgba(191, 75, 61, 0.08);
}

.upload-box {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 20px 22px;
  border-radius: 22px;
  border: 1px dashed rgba(14, 124, 134, 0.28);
  background: linear-gradient(135deg, rgba(14, 124, 134, 0.09), rgba(221, 139, 47, 0.1));
}

.upload-copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.upload-copy span {
  color: var(--text-secondary);
  line-height: 1.7;
}

.upload-btn {
  border: none;
  border-radius: 16px;
  padding: 12px 16px;
  background: #0f7d88;
  color: #f6fffe;
  font-weight: 700;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 18px 0 14px;
}

.toolbar input {
  flex: 1;
  height: 46px;
  padding: 0 16px;
  border-radius: 16px;
  border: 1px solid rgba(128, 92, 53, 0.16);
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filters button {
  border: 1px solid rgba(128, 92, 53, 0.14);
  background: #fffef9;
  border-radius: 999px;
  padding: 9px 14px;
}

.filters button.active {
  border-color: rgba(14, 124, 134, 0.24);
  background: rgba(14, 124, 134, 0.08);
  color: var(--primary);
}

.error-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(191, 75, 61, 0.1);
  color: var(--red);
}

.retry-btn {
  flex-shrink: 0;
  border: none;
  border-radius: 12px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.9);
  color: var(--red);
  font-weight: 700;
}

.task-list {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.task-card {
  padding: 18px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid rgba(128, 92, 53, 0.12);
}

.task-top {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.task-top h3 {
  margin: 0;
}

.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
  color: var(--text-tertiary);
  font-size: 12px;
}

.task-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.status-pill {
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 700;
}

.status-pill.success {
  background: rgba(31, 143, 87, 0.12);
  color: var(--green);
}

.status-pill.pending {
  background: rgba(14, 124, 134, 0.12);
  color: var(--primary);
}

.status-pill.danger {
  background: rgba(191, 75, 61, 0.1);
  color: var(--red);
}

.delete-btn {
  border: none;
  background: transparent;
  color: var(--red);
  font-weight: 700;
}

.ghost-btn {
  border: 1px solid rgba(128, 92, 53, 0.14);
  border-radius: 999px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.76);
  color: var(--text-secondary);
  font-weight: 700;
}

.progress-bar {
  height: 8px;
  margin-top: 14px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(128, 92, 53, 0.08);
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0f7d88, #e3943b);
}

.recommend-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.recommend-tags span {
  border-radius: 999px;
  padding: 6px 10px;
  background: rgba(221, 139, 47, 0.1);
  color: #9b5b19;
  font-size: 12px;
}

.timeline {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 12px 1fr;
  gap: 10px;
}

.timeline-item strong {
  margin-right: 8px;
}

.timeline-item span,
.timeline-item p {
  color: var(--text-secondary);
  font-size: 12px;
}

.timeline-item p {
  margin: 4px 0 0;
}

.timeline-dot {
  margin-top: 4px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(128, 92, 53, 0.2);
}

.timeline-dot.completed {
  background: var(--green);
}

.timeline-dot.processing {
  background: var(--primary);
}

.timeline-dot.failed,
.timeline-dot.error {
  background: var(--red);
}

.empty-box {
  padding: 28px;
  text-align: center;
  border-radius: 20px;
  border: 1px dashed rgba(128, 92, 53, 0.16);
  color: var(--text-secondary);
}

.confirm-overlay {
  z-index: 45;
}

.confirm-card {
  width: min(420px, 100%);
  padding: 24px;
  border-radius: 24px;
  background: rgba(255, 250, 241, 0.98);
  border: 1px solid rgba(128, 92, 53, 0.16);
  box-shadow: 0 24px 60px rgba(43, 31, 16, 0.18);
}

.confirm-card h3 {
  margin: 10px 0 8px;
  font-family: 'Cormorant Garamond', serif;
  font-size: 34px;
}

.confirm-card p {
  margin: 0;
  line-height: 1.7;
  color: var(--text-secondary);
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

.close-btn.ghost {
  background: rgba(255, 255, 255, 0.7);
}

.danger-btn {
  border: none;
  border-radius: 14px;
  padding: 10px 14px;
  background: linear-gradient(135deg, #d75b49, #b33d35);
  color: #fff8f4;
  font-weight: 700;
  cursor: pointer;
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

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .upload-box,
  .toolbar,
  .task-top {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }

  .error-box {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (max-width: 640px) {
  .overlay {
    padding: 12px;
  }

  .panel {
    padding: 18px 18px 14px;
  }

  .panel-body {
    padding-right: 2px;
  }

  .panel-head h2 {
    font-size: 34px;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
