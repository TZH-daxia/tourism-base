<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

type LoginPayload = {
  role: 'root' | 'guest'
  account?: string
  password?: string
}

const props = defineProps<{ error?: string }>()
const emit = defineEmits<{ close: []; login: [payload: LoginPayload] }>()

const account = ref('')
const password = ref('')
const accountInput = ref<HTMLInputElement>()

const canSubmit = computed(() => Boolean(account.value.trim() && password.value.trim()))

function submitLogin() {
  emit('login', {
    role: 'root',
    account: account.value.trim(),
    password: password.value,
  })
}

function submitGuest() {
  emit('login', { role: 'guest' })
}

watch(
  () => props.error,
  value => {
    if (value) {
      nextTick(() => {
        accountInput.value?.focus()
        accountInput.value?.select()
      })
    }
  },
)

onMounted(() => {
  nextTick(() => accountInput.value?.focus())
})
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div class="login-overlay" @click.self="emit('close')">
        <div class="login-card">
          <div class="login-head">
            <div class="login-eyebrow">Ranger Access</div>
            <h3>进入游侠智库</h3>
            <p>请选择进入方式</p>
          </div>

          <div class="access-stack">
            <button class="access-card access-card--action" type="button" @click="submitGuest">
              <span class="access-card__label">游客登录</span>
              <span class="access-card__meta">本次访问仅本地有效</span>
            </button>

            <section class="access-card access-card--panel">
              <div class="access-card__header">
                <span class="access-card__label">管理员登录</span>
                <span class="access-card__meta">使用正式账号进入</span>
              </div>

              <label class="login-field">
                <span>账号</span>
                <input
                  ref="accountInput"
                  v-model="account"
                  type="text"
                  placeholder="请输入账号"
                  @keydown.enter.prevent="submitLogin"
                />
              </label>

              <label class="login-field">
                <span>密码</span>
                <input
                  v-model="password"
                  type="password"
                  placeholder="请输入密码"
                  @keydown.enter.prevent="submitLogin"
                />
              </label>

              <div v-if="error" class="login-error">{{ error }}</div>

              <button class="access-card access-card--action access-card--submit" type="button" :disabled="!canSubmit" @click="submitLogin">
                <span class="access-card__label">管理员登录</span>
              </button>
            </section>
          </div>

          <div class="login-actions">
            <button class="ghost-btn" type="button" @click="emit('close')">取消</button>
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
  padding: 24px;
  background:
    radial-gradient(circle at 50% 0%, rgba(13, 121, 130, 0.14), transparent 30%),
    rgba(10, 14, 17, 0.56);
  backdrop-filter: blur(14px);
}

.login-card {
  width: min(430px, 100%);
  padding: 28px;
  border-radius: 28px;
  background: rgba(250, 245, 236, 0.97);
  border: 1px solid rgba(125, 100, 72, 0.14);
  box-shadow:
    0 32px 90px rgba(8, 16, 20, 0.24),
    inset 0 1px 0 rgba(255, 255, 255, 0.84);
  color: #243137;
}

.login-head {
  display: grid;
  gap: 8px;
  text-align: center;
}

.login-eyebrow {
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #0d7982;
}

.login-head h3 {
  margin: 0;
  font-size: 30px;
  line-height: 1.1;
  font-weight: 700;
  color: #223137;
}

.login-head p {
  margin: 0;
  color: #6a6258;
  font-size: 13px;
}

.access-stack {
  display: grid;
  gap: 14px;
  margin-top: 22px;
}

.access-card {
  width: 100%;
  border-radius: 20px;
  border: 1px solid rgba(128, 111, 92, 0.14);
  background: rgba(255, 255, 255, 0.74);
  box-shadow: 0 12px 28px rgba(15, 27, 31, 0.06);
}

.access-card--action {
  min-height: 66px;
  padding: 12px 18px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.access-card--action:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgba(13, 121, 130, 0.26);
  box-shadow: 0 16px 28px rgba(13, 121, 130, 0.08);
}

.access-card--action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.access-card--panel {
  padding: 18px;
}

.access-card__header {
  display: grid;
  gap: 4px;
  margin-bottom: 6px;
  text-align: center;
}

.access-card__label {
  font-size: 15px;
  font-weight: 700;
  color: #223137;
}

.access-card__meta {
  font-size: 12px;
  color: #766c61;
}

.access-card--submit {
  margin-top: 14px;
  min-height: 58px;
}

.login-field {
  display: grid;
  gap: 7px;
  margin-top: 12px;
}

.login-field span {
  font-size: 12px;
  color: #6e665c;
}

.login-field input {
  width: 100%;
  height: 46px;
  padding: 0 14px;
  border-radius: 14px;
  border: 1px solid rgba(128, 111, 92, 0.16);
  background: rgba(255, 255, 255, 0.92);
  color: #243137;
}

.login-field input:focus {
  outline: none;
  border-color: rgba(13, 121, 130, 0.38);
  box-shadow: 0 0 0 4px rgba(13, 121, 130, 0.1);
}

.login-error {
  margin-top: 12px;
  text-align: center;
  font-size: 13px;
  color: #bc4f42;
}

.login-actions {
  display: flex;
  justify-content: center;
  margin-top: 18px;
}

.ghost-btn {
  min-width: 104px;
  height: 42px;
  border: none;
  border-radius: 14px;
  background: rgba(46, 37, 24, 0.06);
  color: #2f2619;
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

@media (max-width: 640px) {
  .login-card {
    padding: 24px;
    border-radius: 24px;
  }
}
</style>
