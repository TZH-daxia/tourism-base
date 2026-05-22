<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{ close: []; login: [] }>()

const account = ref('')
const password = ref('')

function handleLogin() {
  emit('login')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div class="login-overlay" @click.self="emit('close')">
        <div class="login-card">
          <div class="login-eyebrow">Demo Login</div>
          <h3>进入游侠智库</h3>
          <p>这里先保留一个登录演示入口。当前不校验账号信息，不论输入什么内容，点击登录都会直接进入系统。</p>

          <label class="login-field">
            <span>账号</span>
            <input v-model="account" type="text" placeholder="输入任意账号名" />
          </label>

          <label class="login-field">
            <span>密码</span>
            <input v-model="password" type="password" placeholder="输入任意密码" />
          </label>

          <div class="login-actions">
            <button class="login-btn ghost" type="button" @click="emit('close')">取消</button>
            <button class="login-btn solid" type="button" @click="handleLogin">登录并进入</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.login-overlay {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(4, 12, 16, 0.5);
  backdrop-filter: blur(12px);
}

.login-card {
  width: min(460px, 100%);
  padding: 28px;
  border-radius: 28px;
  background:
    linear-gradient(180deg, rgba(255, 252, 245, 0.98), rgba(246, 236, 220, 0.96));
  border: 1px solid rgba(128, 92, 53, 0.14);
  box-shadow:
    0 28px 80px rgba(7, 15, 18, 0.24),
    inset 0 1px 0 rgba(255, 255, 255, 0.86);
  color: #2e2518;
}

.login-eyebrow {
  color: #0e7c86;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.login-card h3 {
  margin: 10px 0 8px;
  font-family: 'Cormorant Garamond', serif;
  font-size: 42px;
}

.login-card p {
  margin: 0;
  color: #6e5d4b;
  line-height: 1.75;
}

.login-field {
  display: grid;
  gap: 8px;
  margin-top: 16px;
}

.login-field span {
  color: #6e5d4b;
  font-size: 12px;
}

.login-field input {
  width: 100%;
  height: 46px;
  border: 1px solid rgba(128, 92, 53, 0.16);
  border-radius: 16px;
  padding: 0 14px;
  background: rgba(255, 255, 255, 0.92);
  color: #2e2518;
}

.login-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 22px;
}

.login-btn {
  border: none;
  border-radius: 16px;
  padding: 12px 18px;
  font-weight: 700;
  cursor: pointer;
}

.login-btn.ghost {
  background: rgba(46, 37, 24, 0.06);
  color: #2e2518;
}

.login-btn.solid {
  background: linear-gradient(135deg, #0f7d88, #d26835);
  color: #fff8f0;
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
</style>
