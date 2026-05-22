<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const emit = defineEmits<{ 'open-login': [] }>()

type Particle = {
  x: number
  y: number
  radius: number
  alpha: number
  vx: number
  vy: number
  hue: 'teal' | 'amber' | 'neutral'
}

const antigravity = ref(false)
const particleCanvas = ref<HTMLCanvasElement>()
const pointerX = ref(0)
const pointerY = ref(0)
let gravityTimer: number | null = null
let rafId = 0
let particles: Particle[] = []

const orbitNotes = [
  { label: '三亚 景点', x: '-34vw', y: '-18vh', r: '-10deg', d: '0s' },
  { label: '张家界 酒店', x: '32vw', y: '-15vh', r: '8deg', d: '0.16s' },
  { label: '厦门 美食', x: '-30vw', y: '16vh', r: '8deg', d: '0.28s' },
  { label: '杭州 线路', x: '25vw', y: '21vh', r: '-9deg', d: '0.42s' },
  { label: '云南 交通', x: '-6vw', y: '-28vh', r: '5deg', d: '0.56s' },
]

const parallaxStyle = computed(() => ({
  '--pointer-x': `${pointerX.value}px`,
  '--pointer-y': `${pointerY.value}px`,
}))

function triggerLogin() {
  emit('open-login')
}

function handlePointerMove(event: PointerEvent) {
  const centerX = window.innerWidth / 2
  const centerY = window.innerHeight / 2
  pointerX.value = (event.clientX - centerX) / Math.max(centerX, 1)
  pointerY.value = (event.clientY - centerY) / Math.max(centerY, 1)
}

function resizeCanvas() {
  const canvas = particleCanvas.value
  if (!canvas) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.floor(window.innerWidth * dpr)
  canvas.height = Math.floor(window.innerHeight * dpr)
  canvas.style.width = `${window.innerWidth}px`
  canvas.style.height = `${window.innerHeight}px`
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  seedParticles()
}

function seedParticles() {
  const count = Math.max(120, Math.floor(window.innerWidth / 8))
  const hues: Particle['hue'][] = ['neutral', 'neutral', 'neutral', 'teal', 'amber']
  particles = Array.from({ length: count }, () => ({
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    radius: Math.random() * 1.8 + 0.4,
    alpha: Math.random() * 0.35 + 0.08,
    vx: (Math.random() - 0.5) * 0.12,
    vy: (Math.random() - 0.5) * 0.08,
    hue: hues[Math.floor(Math.random() * hues.length)],
  }))
}

function particleFill(particle: Particle) {
  if (particle.hue === 'teal') return `rgba(88, 173, 191, ${particle.alpha})`
  if (particle.hue === 'amber') return `rgba(225, 174, 83, ${particle.alpha})`
  return `rgba(138, 149, 158, ${particle.alpha})`
}

function particleGlow(particle: Particle) {
  if (particle.hue === 'teal') return `rgba(88, 173, 191, ${particle.alpha * 0.22})`
  if (particle.hue === 'amber') return `rgba(225, 174, 83, ${particle.alpha * 0.2})`
  return `rgba(138, 149, 158, ${particle.alpha * 0.14})`
}

function drawParticles() {
  const canvas = particleCanvas.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx) return

  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)

  const pointerPx = window.innerWidth / 2 + pointerX.value * (window.innerWidth / 2)
  const pointerPy = window.innerHeight / 2 + pointerY.value * (window.innerHeight / 2)
  const linkDistance = 96
  const repelDistance = 160

  for (const particle of particles) {
    const dx = particle.x - pointerPx
    const dy = particle.y - pointerPy
    const distance = Math.hypot(dx, dy)

    if (distance < repelDistance && distance > 0.001) {
      const force = (repelDistance - distance) / repelDistance
      particle.vx += (dx / distance) * force * 0.015
      particle.vy += (dy / distance) * force * 0.015
    }

    particle.vx += (Math.random() - 0.5) * 0.0018
    particle.vy += (Math.random() - 0.5) * 0.0016
    particle.vx *= 0.992
    particle.vy *= 0.992
    particle.x += particle.vx
    particle.y += particle.vy

    if (particle.x < -30) particle.x = window.innerWidth + 30
    if (particle.x > window.innerWidth + 30) particle.x = -30
    if (particle.y < -30) particle.y = window.innerHeight + 30
    if (particle.y > window.innerHeight + 30) particle.y = -30
  }

  for (let i = 0; i < particles.length; i += 1) {
    const a = particles[i]

    for (let j = i + 1; j < particles.length; j += 1) {
      const b = particles[j]
      const dx = a.x - b.x
      const dy = a.y - b.y
      const distance = Math.hypot(dx, dy)

      if (distance < linkDistance) {
        const alpha = (1 - distance / linkDistance) * 0.12
        ctx.strokeStyle = `rgba(146, 160, 171, ${alpha})`
        ctx.lineWidth = 0.6
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
      }
    }
  }

  for (const particle of particles) {
    const glow = ctx.createRadialGradient(particle.x, particle.y, 0, particle.x, particle.y, particle.radius * 8)
    glow.addColorStop(0, particleGlow(particle))
    glow.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = glow
    ctx.beginPath()
    ctx.arc(particle.x, particle.y, particle.radius * 8, 0, Math.PI * 2)
    ctx.fill()

    ctx.fillStyle = particleFill(particle)
    ctx.beginPath()
    ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2)
    ctx.fill()
  }

  rafId = window.requestAnimationFrame(drawParticles)
}

onMounted(() => {
  gravityTimer = window.setTimeout(() => {
    antigravity.value = true
  }, 1100)
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('resize', resizeCanvas)
  resizeCanvas()
  drawParticles()
})

onBeforeUnmount(() => {
  if (gravityTimer) window.clearTimeout(gravityTimer)
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('resize', resizeCanvas)
  if (rafId) window.cancelAnimationFrame(rafId)
})
</script>

<template>
  <section class="portal-shell" :class="{ antigravity }" :style="parallaxStyle">
    <canvas ref="particleCanvas" class="particle-layer"></canvas>
    <div class="portal-vignette"></div>
    <div class="portal-noise"></div>

    <header class="masthead floatable masthead-left">
      <button type="button" @click="triggerLogin">About 游侠</button>
      <button type="button" @click="triggerLogin">Knowledge Base 知识库</button>
    </header>

    <header class="masthead floatable masthead-right">
      <button type="button" @click="triggerLogin">Travel Q&A 旅游问答</button>
      <button type="button" @click="triggerLogin">Sign In</button>
    </header>

    <main class="portal-stage">
      <div class="portal-center">
        <div class="brand-stack floatable">
          <img class="brand-icon" src="/favicon.svg" alt="Ranger Knowledge icon" />
          <div class="brand-title">TOURISM KNOWLEDGE BASE</div>
        </div>

        <div class="travel-logo floatable">
          RANGER KNOWLEDGE
        </div>

        <div class="search-wrap floatable">
          <button class="search-shell" type="button" @click="triggerLogin">
            <span class="search-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M10.5 4a6.5 6.5 0 1 1 0 13a6.5 6.5 0 0 1 0-13Zm0 2a4.5 4.5 0 1 0 0 9a4.5 4.5 0 0 0 0-9Zm5.9 9.49 3.1 3.1-1.41 1.41-3.1-3.1z" />
              </svg>
            </span>
            <span class="search-copy">Search city guides, hotels, food, routes, and image-based travel knowledge</span>
            <span class="search-login">Enter</span>
          </button>

          <div class="search-actions">
            <button type="button" @click="triggerLogin">Open Ranger Knowledge 游侠智库</button>
            <button type="button" @click="triggerLogin">Knowledge Admin 后台管理</button>
          </div>
        </div>

        <div class="status-row floatable">
          <span>Now serving 交通 / 景点 / 酒店 / 美食 / 线路</span>
          <span>OpenAI-compatible models and image-based retrieval are ready 已接入</span>
        </div>
      </div>

      <div
        v-for="note in orbitNotes"
        :key="note.label"
        class="orbit-note floatable"
        :style="{ '--float-x': note.x, '--float-y': note.y, '--float-r': note.r, '--float-delay': note.d }"
      >
        {{ note.label }}
      </div>

      <div class="portal-hint hint-top floatable">Search first, then drift | 先像搜索，再开始失重</div>
      <div class="portal-hint hint-bottom floatable">Choose any entry to sign in | 点击任意入口直接进入</div>
    </main>
  </section>
</template>

<style scoped>
.portal-shell {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 100%;
  overflow: hidden;
  color: #151515;
  background:
    radial-gradient(circle at 50% 42%, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98) 36%, rgba(241, 245, 248, 0.98) 100%);
}

.particle-layer,
.portal-vignette,
.portal-noise {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.particle-layer {
  z-index: 0;
}

.portal-vignette {
  background:
    radial-gradient(circle at 50% 45%, rgba(255, 255, 255, 0) 0 22%, rgba(255, 255, 255, 0.08) 44%, rgba(208, 218, 226, 0.2) 100%),
    radial-gradient(circle at 18% 16%, rgba(108, 182, 196, 0.07), transparent 18%),
    radial-gradient(circle at 84% 18%, rgba(232, 191, 112, 0.08), transparent 20%);
}

.portal-noise {
  opacity: 0.08;
  mix-blend-mode: multiply;
  background-image:
    linear-gradient(transparent 0, rgba(0, 0, 0, 0.03) 100%),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.96' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)' opacity='0.4'/%3E%3C/svg%3E");
}

.portal-stage,
.portal-center,
.masthead,
.orbit-note,
.portal-hint {
  position: relative;
  z-index: 2;
}

.masthead {
  position: absolute;
  top: 22px;
  display: flex;
  gap: 14px;
}

.masthead-left {
  left: 28px;
}

.masthead-right {
  right: 28px;
}

.masthead button,
.search-actions button {
  border: none;
  background: transparent;
  color: rgba(21, 21, 21, 0.82);
  cursor: pointer;
  font-size: 13px;
}

.portal-stage {
  width: 100%;
  height: 100%;
  min-height: 100%;
  display: grid;
  place-items: center;
  padding: 112px 28px 56px;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.portal-stage::-webkit-scrollbar {
  display: none;
}

.portal-center {
  position: relative;
  width: min(780px, 100%);
  max-width: 100%;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0;
  text-align: center;
}

.brand-stack {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.brand-icon {
  width: 42px;
  height: 62px;
  object-fit: contain;
  opacity: 0.92;
  filter: drop-shadow(0 10px 18px rgba(209, 217, 224, 0.6));
}

.brand-title {
  color: rgba(21, 21, 21, 0.58);
  font-size: clamp(10px, 1.3vw, 11px);
  font-weight: 700;
  letter-spacing: 0.28em;
  text-transform: uppercase;
}

.travel-logo {
  margin-top: 12px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-family: 'DM Sans', sans-serif;
  font-size: clamp(42px, 7vw, 96px);
  font-weight: 800;
  line-height: 0.96;
  letter-spacing: -0.05em;
  color: #111111;
  text-transform: uppercase;
  text-shadow: 0 14px 28px rgba(225, 231, 235, 0.75);
  white-space: nowrap;
}

.search-wrap {
  margin-top: 18px;
  width: min(700px, 100%);
}

.search-shell {
  width: 100%;
  min-height: 60px;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 0 18px;
  border: 1px solid rgba(191, 202, 209, 0.78);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: #151515;
  cursor: pointer;
  box-shadow:
    0 18px 42px rgba(212, 220, 227, 0.6),
    inset 0 1px 0 rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(10px);
}

.search-icon svg {
  width: 18px;
  height: 18px;
  fill: rgba(21, 21, 21, 0.56);
}

.search-copy {
  text-align: left;
  color: rgba(21, 21, 21, 0.72);
  font-size: clamp(13px, 1.8vw, 15px);
  line-height: 1.5;
}

.search-login {
  padding: 9px 16px;
  border-radius: 999px;
  background: rgba(241, 246, 248, 0.95);
  color: rgba(21, 21, 21, 0.82);
  font-weight: 600;
}

.search-actions {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 18px;
}

.status-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 18px;
  margin-top: 28px;
  color: rgba(21, 21, 21, 0.46);
  font-size: 12px;
  text-align: center;
}

.orbit-note {
  position: absolute;
  top: 50%;
  left: 50%;
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(196, 207, 214, 0.7);
  color: rgba(21, 21, 21, 0.62);
  font-size: 12px;
  letter-spacing: 0.06em;
  transform: translate(-50%, -50%);
  opacity: 0;
  backdrop-filter: blur(10px);
  box-shadow: 0 12px 30px rgba(214, 223, 229, 0.46);
}

.portal-hint {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  color: rgba(21, 21, 21, 0.34);
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hint-top {
  top: 112px;
}

.hint-bottom {
  bottom: 30px;
}

.floatable {
  transition:
    transform 1.7s cubic-bezier(0.2, 0.8, 0.2, 1),
    opacity 0.8s ease;
}

.portal-shell.antigravity .masthead-left {
  transform: translate3d(calc(var(--pointer-x) * -24px), calc(var(--pointer-y) * 12px), 0) rotate(-7deg);
}

.portal-shell.antigravity .masthead-right {
  transform: translate3d(calc(var(--pointer-x) * 28px), calc(var(--pointer-y) * -10px), 0) rotate(7deg);
}

.portal-shell.antigravity .brand-stack {
  transform: translate3d(calc(var(--pointer-x) * -4px), calc(var(--pointer-y) * -8px), 0) rotate(-1deg);
}

.portal-shell.antigravity .travel-logo {
  transform: translate3d(calc(var(--pointer-x) * -10px), calc(var(--pointer-y) * -14px), 0) rotate(-3deg);
}

.portal-shell.antigravity .search-wrap {
  transform: translate3d(calc(var(--pointer-x) * 12px), calc(var(--pointer-y) * 10px), 0) rotate(4deg);
}

.portal-shell.antigravity .status-row {
  transform: translate3d(calc(var(--pointer-x) * -18px), calc(var(--pointer-y) * 10px), 0) rotate(-3deg);
}

.portal-shell.antigravity .orbit-note {
  opacity: 1;
  animation: orbit-drift 9s ease-in-out infinite;
  animation-delay: var(--float-delay);
  transform:
    translate(-50%, -50%)
    translate3d(var(--float-x), var(--float-y), 0)
    rotate(var(--float-r));
}

.portal-shell.antigravity .hint-top {
  transform: translateX(-50%) translate3d(-28px, -12px, 0) rotate(-5deg);
}

.portal-shell.antigravity .hint-bottom {
  transform: translateX(-50%) translate3d(34px, -10px, 0) rotate(4deg);
}

@keyframes orbit-drift {
  0%,
  100% {
    transform:
      translate(-50%, -50%)
      translate3d(var(--float-x), var(--float-y), 0)
      rotate(var(--float-r));
  }
  50% {
    transform:
      translate(-50%, -50%)
      translate3d(calc(var(--float-x) + 14px), calc(var(--float-y) - 18px), 0)
      rotate(calc(var(--float-r) + 6deg));
  }
}

@media (max-width: 920px) {
  .masthead-right {
    display: none;
  }

  .masthead-left {
    left: 18px;
    right: 18px;
    justify-content: center;
  }

  .portal-center {
    width: min(100%, 720px);
  }

  .travel-logo {
    font-size: clamp(34px, 8vw, 64px);
  }

  .search-shell {
    grid-template-columns: 24px minmax(0, 1fr);
    padding: 14px 18px;
  }

  .search-login {
    grid-column: 1 / -1;
    justify-self: flex-end;
  }

  .search-actions,
  .status-row {
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }

  .orbit-note,
  .portal-hint {
    display: none;
  }
}

@media (max-width: 720px) {
  .portal-stage {
    padding: 92px 16px 32px;
  }

  .masthead {
    top: 14px;
  }

  .masthead-left {
    left: 12px;
    right: 12px;
    gap: 10px;
    flex-wrap: wrap;
  }

  .brand-icon {
    width: 36px;
    height: 54px;
  }

  .brand-title {
    letter-spacing: 0.2em;
  }

  .travel-logo {
    white-space: normal;
    text-wrap: balance;
  }

  .search-wrap {
    margin-top: 14px;
  }

  .search-shell {
    gap: 10px;
    border-radius: 28px;
  }

  .search-actions {
    gap: 10px;
    margin-top: 14px;
  }

  .status-row {
    margin-top: 18px;
    gap: 8px;
    font-size: 11px;
  }
}

@media (max-height: 860px) {
  .portal-stage {
    padding-top: 84px;
    padding-bottom: 28px;
  }

  .brand-icon {
    width: 38px;
    height: 56px;
  }

  .travel-logo {
    margin-top: 10px;
    font-size: clamp(38px, 6.2vw, 76px);
  }

  .search-wrap {
    margin-top: 14px;
  }

  .search-actions {
    margin-top: 14px;
  }

  .status-row {
    margin-top: 20px;
  }

  .hint-top {
    top: 88px;
  }

  .hint-bottom {
    bottom: 18px;
  }
}

@media (max-height: 740px) {
  .portal-stage {
    padding-top: 72px;
  }

  .masthead {
    top: 14px;
  }

  .brand-stack {
    gap: 8px;
  }

  .brand-icon {
    width: 34px;
    height: 50px;
  }

  .brand-title {
    font-size: 10px;
    letter-spacing: 0.16em;
  }

  .travel-logo {
    font-size: clamp(32px, 5.6vw, 60px);
  }

  .search-shell {
    min-height: 54px;
  }

  .search-login {
    padding: 7px 14px;
  }

  .status-row,
  .orbit-note,
  .portal-hint {
    display: none;
  }
}
</style>
