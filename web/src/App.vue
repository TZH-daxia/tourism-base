<script setup lang="ts">
import { ref } from 'vue'

import ChatView from './components/chat/ChatView.vue'
import KnowledgeUpload from './components/knowledge/KnowledgeUpload.vue'
import LandingPortal from './components/landing/LandingPortal.vue'
import LoginDemoModal from './components/landing/LoginDemoModal.vue'

const showKb = ref(false)
const kbVersion = ref(0)
const showLogin = ref(false)
const entered = ref(false)

function handleKbUpdated() {
  kbVersion.value += 1
}

function openLogin() {
  showLogin.value = true
}

function closeLogin() {
  showLogin.value = false
}

function handleLogin() {
  showLogin.value = false
  entered.value = true
}

function handleLogout() {
  showKb.value = false
  showLogin.value = false
  entered.value = false
}
</script>

<template>
  <div class="app-shell" :class="{ entered }">
    <div class="backdrop"></div>
    <div class="grain"></div>

    <LandingPortal v-if="!entered" @open-login="openLogin" />

    <template v-else>
      <ChatView :kb-version="kbVersion" @open-kb="showKb = true" @logout="handleLogout" />
      <KnowledgeUpload :show="showKb" @close="showKb = false" @updated="handleKbUpdated" />
    </template>

    <LoginDemoModal v-if="showLogin" @close="closeLogin" @login="handleLogin" />
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
}

body {
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
  height: 100%;
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
</style>
