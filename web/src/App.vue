<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import ChatView from './components/chat/ChatView.vue'
import KnowledgeUpload from './components/knowledge/KnowledgeUpload.vue'
import LandingPortal from './components/landing/LandingPortal.vue'
import LoginDemoModal from './components/landing/LoginDemoModal.vue'

type AuthSession = {
  role: 'root' | 'guest'
  displayName: string
  email: string
}

const showKb = ref(false)
const showKbAuth = ref(false)
const kbVersion = ref(0)
const showLogin = ref(false)
const kbPassword = ref('')
const kbPasswordError = ref('')
const kbPasswordInput = ref<HTMLInputElement>()
const loginError = ref('')
const authSession = ref<AuthSession | null>(null)
const resetGuestState = ref(false)

const KB_ADMIN_PASSWORD = '0513'
const ROOT_ACCOUNT = 'root'
const ROOT_PASSWORD = '0513'
const AUTH_STORAGE_KEY = 'tourism_auth_session'

const entered = computed(() => Boolean(authSession.value))
const isRoot = computed(() => authSession.value?.role === 'root')

function handleKbUpdated() {
  kbVersion.value += 1
}

function persistAuthSession() {
  if (authSession.value) {
    sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(authSession.value))
  } else {
    sessionStorage.removeItem(AUTH_STORAGE_KEY)
  }
}

function requestOpenKb() {
  if (!isRoot.value) return
  kbPassword.value = ''
  kbPasswordError.value = ''
  showKbAuth.value = true
}

function cancelKbAuth() {
  showKbAuth.value = false
  kbPassword.value = ''
  kbPasswordError.value = ''
}

function confirmKbAuth() {
  if (kbPassword.value.trim() !== KB_ADMIN_PASSWORD) {
    kbPasswordError.value = '管理员密码不正确，请重新输入。'
    return
  }
  showKbAuth.value = false
  kbPassword.value = ''
  kbPasswordError.value = ''
  showKb.value = true
}

function openLogin() {
  loginError.value = ''
  showLogin.value = true
}

function closeLogin() {
  showLogin.value = false
  loginError.value = ''
}

function handleLogin(payload: { role: 'root' | 'guest'; account?: string; password?: string }) {
  if (payload.role === 'guest') {
    resetGuestState.value = true
    authSession.value = {
      role: 'guest',
      displayName: '游客体验',
      email: '本次数据仅本地有效',
    }
    persistAuthSession()
    showLogin.value = false
    loginError.value = ''
    return
  }

  if (payload.account?.trim() !== ROOT_ACCOUNT || payload.password !== ROOT_PASSWORD) {
    loginError.value = '账号或密码不正确，请重新输入。'
    return
  }

  resetGuestState.value = false
  authSession.value = {
    role: 'root',
    displayName: '系统管理员',
    email: 'root@tourism.local',
  }
  persistAuthSession()
  showLogin.value = false
  loginError.value = ''
}

function handleLogout() {
  showKb.value = false
  showKbAuth.value = false
  showLogin.value = false
  authSession.value = null
  resetGuestState.value = false
  kbPassword.value = ''
  kbPasswordError.value = ''
  loginError.value = ''
  persistAuthSession()
}

watch(showKbAuth, value => {
  if (value) {
    nextTick(() => kbPasswordInput.value?.focus())
  }
})

onMounted(() => {
  const saved = sessionStorage.getItem(AUTH_STORAGE_KEY)
  if (!saved) return
  try {
    const parsed = JSON.parse(saved) as AuthSession
    if (parsed?.role === 'root' || parsed?.role === 'guest') {
      authSession.value = parsed
      resetGuestState.value = false
    }
  } catch {
    sessionStorage.removeItem(AUTH_STORAGE_KEY)
  }
})
</script>

<template>
  <div class="app-shell" :class="{ entered }">
    <div class="backdrop"></div>
    <div class="grain"></div>

    <LandingPortal v-if="!entered" @open-login="openLogin" />

    <template v-else>
      <ChatView
        :kb-version="kbVersion"
        :auth-role="authSession?.role || 'guest'"
        :display-name="authSession?.displayName || '游客体验'"
        :display-email="authSession?.email || '本次数据仅本地有效'"
        :reset-guest-state="resetGuestState"
        @open-kb="requestOpenKb"
        @logout="handleLogout"
      />
      <KnowledgeUpload v-if="isRoot" :show="showKb" @close="showKb = false" @updated="handleKbUpdated" />
    </template>

    <LoginDemoModal v-if="showLogin" :error="loginError" @close="closeLogin" @login="handleLogin" />

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showKbAuth" class="kb-auth-overlay" @click.self="cancelKbAuth">
          <div class="kb-auth-card">
            <div class="kb-auth-eyebrow">Admin Access</div>
            <h3>输入管理员密码</h3>
            <p>确认身份后才能进入知识库后台管理。</p>
            <label class="kb-auth-field">
              <span>管理员密码</span>
              <input
                ref="kbPasswordInput"
                v-model="kbPassword"
                type="password"
                placeholder="请输入管理员密码"
                @keydown.enter.prevent="confirmKbAuth"
              />
            </label>
            <div v-if="kbPasswordError" class="kb-auth-error">{{ kbPasswordError }}</div>
            <div class="kb-auth-actions">
              <button class="kb-auth-btn ghost" type="button" @click="cancelKbAuth">取消</button>
              <button class="kb-auth-btn" type="button" @click="confirmKbAuth">确认</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap');

:root {
  --bg: #f8f4ea;
  --surface: rgba(255, 250, 240, 0.88);
  --surface-strong: #fffdf7;
  --border: rgba(128, 92, 53, 0.18);
  --text: #2e2518;
  --text-secondary: #6e5d4b;
  --text-tertiary: #9f8d79;
  --primary: #0e7c86;
  --primary-soft: rgba(14, 124, 134, 0.12);
  --primary-light: rgba(14, 124, 134, 0.2);
  --accent: #dd8b2f;
  --accent-soft: rgba(221, 139, 47, 0.14);
  --green: #1f8f57;
  --red: #bf4b3d;
  --shadow: 0 24px 80px rgba(70, 45, 22, 0.12);
  --radius: 26px;
  --radius-sm: 16px;
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  margin: 0;
  width: 100%;
  height: 100%;
  min-height: 100%;
}

body {
  min-height: 100vh;
  min-height: 100dvh;
  overflow: hidden;
  font-family: 'Noto Sans SC', sans-serif;
  background:
    radial-gradient(circle at top left, rgba(240, 211, 167, 0.65), transparent 34%),
    radial-gradient(circle at right 12%, rgba(117, 190, 199, 0.22), transparent 28%),
    linear-gradient(180deg, #f7f1e1 0%, #f2ead7 52%, #efe3ca 100%);
  color: var(--text);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.app-shell {
  position: relative;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  min-height: 100vh;
  min-height: 100dvh;
  overflow: hidden;
}

.app-shell.entered {
  background: transparent;
}

.backdrop,
.grain {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.backdrop {
  background:
    radial-gradient(circle at 14% 18%, rgba(255, 255, 255, 0.8), transparent 15%),
    radial-gradient(circle at 86% 22%, rgba(13, 125, 135, 0.08), transparent 16%),
    radial-gradient(circle at 50% 100%, rgba(222, 152, 66, 0.1), transparent 24%);
}

.grain {
  opacity: 0.08;
  background-image:
    linear-gradient(transparent 0, rgba(0, 0, 0, 0.08) 100%),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180' viewBox='0 0 180 180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='1.05' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E");
  mix-blend-mode: multiply;
}

button,
input {
  font: inherit;
}

::selection {
  background: rgba(14, 124, 134, 0.18);
}

::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-thumb {
  background: rgba(100, 75, 48, 0.18);
  border-radius: 999px;
}

.kb-auth-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(43, 31, 16, 0.34);
  backdrop-filter: blur(8px);
}

.kb-auth-card {
  width: min(420px, 100%);
  padding: 24px;
  border-radius: 24px;
  background: rgba(255, 250, 241, 0.98);
  border: 1px solid rgba(128, 92, 53, 0.16);
  box-shadow: 0 24px 60px rgba(43, 31, 16, 0.18);
}

.kb-auth-eyebrow {
  color: var(--primary);
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.kb-auth-card h3 {
  margin: 10px 0 8px;
  font-family: 'Cormorant Garamond', serif;
  font-size: 34px;
}

.kb-auth-card p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.kb-auth-field {
  display: grid;
  gap: 8px;
  margin-top: 18px;
}

.kb-auth-field span {
  font-size: 13px;
  color: var(--text-secondary);
}

.kb-auth-field input {
  height: 46px;
  padding: 0 14px;
  border-radius: 14px;
  border: 1px solid rgba(128, 92, 53, 0.16);
  background: rgba(255, 255, 255, 0.86);
}

.kb-auth-error {
  margin-top: 12px;
  color: var(--red);
  font-size: 13px;
}

.kb-auth-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

.kb-auth-btn {
  border: none;
  border-radius: 14px;
  padding: 10px 16px;
  background: #0f7d88;
  color: #f6fffe;
  font-weight: 700;
  cursor: pointer;
}

.kb-auth-btn.ghost {
  border: 1px solid rgba(128, 92, 53, 0.14);
  background: rgba(255, 255, 255, 0.7);
  color: var(--text);
}
</style>
