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
const portalScroll = ref<HTMLElement>()
const quotePanel = ref<HTMLElement>()
const journeyPanel = ref<HTMLElement>()
const pointerX = ref(0)
const pointerY = ref(0)
const heroScrollProgress = ref(0)
const quoteProgress = ref(0)
const journeyProgress = ref(0)
let gravityTimer: number | null = null
let rafId = 0
let particles: Particle[] = []

const orbitNotes = [
  { label: 'SANYA / beach plans', x: '-34vw', y: '-18vh', r: '-10deg', d: '0s' },
  { label: 'HANGZHOU / tea and lakes', x: '32vw', y: '-15vh', r: '8deg', d: '0.16s' },
  { label: 'YUNNAN / long routes', x: '-30vw', y: '16vh', r: '8deg', d: '0.28s' },
  { label: 'CHENGDU / food nights', x: '25vw', y: '21vh', r: '-9deg', d: '0.42s' },
  { label: 'XIAMEN / seaside walk', x: '-6vw', y: '-28vh', r: '5deg', d: '0.56s' },
]

const featuredPrompts = [
  '三亚亲子四日游怎么安排更轻松？',
  '杭州两天一夜，西湖和茶园怎么串起来？',
  '云南第一次去，昆明大理丽江怎么取舍？',
  '成都夜游、美食和博物馆路线推荐',
]

const vibeLines = [
  {
    title: '资料先归位',
    copy: '把景点、酒店、交通、美食和路线资料放进同一个旅行知识入口，减少反复翻文件的时间。',
  },
  {
    title: '回答要有来源',
    copy: '每次问答都围绕已有资料组织，不只给结论，也保留可回看的依据和线索。',
  },
  {
    title: '建议要能执行',
    copy: '路线、预算、时间和偏好被一起考虑，回答更像可以直接拿去调整的行程草稿。',
  },
]

const journeyCards = [
  {
    eyebrow: 'Guest Mode',
    title: '游客只管提问',
    copy: '输入城市、天数、预算或旅行偏好，就能快速得到路线、住宿、美食和交通建议。',
  },
  {
    eyebrow: 'Admin Mode',
    title: '管理员维护资料',
    copy: '把资料上传、状态确认和内容更新集中管理，让知识长期可查、可改、可继续扩展。',
  },
]

const parallaxStyle = computed(() => ({
  '--pointer-x': `${pointerX.value}px`,
  '--pointer-y': `${pointerY.value}px`,
}))

const heroMotionStyle = computed(() => ({
  '--hero-fade': `${1 - heroScrollProgress.value * 0.32}`,
  '--hero-shift': `${heroScrollProgress.value * 42}px`,
  '--hero-scale': `${1 - heroScrollProgress.value * 0.035}`,
}))

function triggerLogin() {
  emit('open-login')
}

function openAbout() {
  window.location.assign('/about-ranger.html')
}

function openPricing() {
  window.location.assign('/pricing.html')
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value))
}

function updateMotion() {
  const scrollEl = portalScroll.value
  if (!scrollEl) return

  const viewportHeight = scrollEl.clientHeight || window.innerHeight
  heroScrollProgress.value = clamp01(scrollEl.scrollTop / Math.max(viewportHeight * 0.7, 1))

  const getProgress = (element: HTMLElement | undefined | null) => {
    if (!element) return 0
    const rect = element.getBoundingClientRect()
    const focusY = window.innerHeight * 0.58
    const distance = Math.abs(rect.top + rect.height * 0.32 - focusY)
    return clamp01(1 - distance / Math.max(window.innerHeight * 0.78, 1))
  }

  quoteProgress.value = getProgress(quotePanel.value)
  journeyProgress.value = getProgress(journeyPanel.value)
}

function cardMotionStyle(index: number, progress: number, spread = 26) {
  const startOffset = spread + index * 18
  const shift = (1 - progress) * startOffset
  const opacity = 0.72 + progress * 0.28
  const scale = 0.98 + progress * 0.02
  return {
    opacity: opacity.toFixed(3),
    transform: `translate3d(0, ${shift.toFixed(1)}px, 0) scale(${scale.toFixed(3)})`,
    filter: `blur(${((1 - progress) * 1.2).toFixed(2)}px)`,
  }
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
  updateMotion()
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

    <header class="masthead floatable">
      <div class="masthead-actions">
        <button type="button" @click="openAbout">About 游侠</button>
        <button type="button" @click="openPricing">充值</button>
      </div>
      <div class="masthead-actions">
        <button type="button" @click="triggerLogin">Travel Q&A 旅游问答</button>
        <button type="button" class="masthead-strong" @click="triggerLogin">Sign In</button>
      </div>
    </header>

    <main ref="portalScroll" class="portal-scroll" @scroll.passive="updateMotion">
      <section class="snap-panel hero-panel">
        <div class="portal-center hero-motion" :style="heroMotionStyle">
          <div class="brand-stack floatable">
            <img class="brand-icon" src="/tourism-logo.png" alt="Ranger logo" />
            <div class="brand-title">RANGER THINK TANK</div>
          </div>

          <div class="travel-logo floatable">
            <span>RANGER</span>
            <span>THINK TANK</span>
          </div>

          <p class="hero-copy floatable">
            游侠智库把景点、酒店、美食、交通和线路资料变成可以直接提问的旅行助手。
          </p>

          <div class="search-wrap floatable">
            <button class="search-shell" type="button" @click="triggerLogin">
              <span class="search-icon">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M10.5 4a6.5 6.5 0 1 1 0 13a6.5 6.5 0 0 1 0-13Zm0 2a4.5 4.5 0 1 0 0 9a4.5 4.5 0 0 0 0-9Zm5.9 9.49 3.1 3.1-1.41 1.41-3.1-3.1z" />
                </svg>
              </span>
              <span class="search-copy">Ask about routes, hotels, food, transport, and trip planning</span>
              <span class="search-login">Enter</span>
            </button>

            <div class="quick-prompts">
              <button v-for="prompt in featuredPrompts" :key="prompt" class="prompt-pill" type="button" @click="triggerLogin">
                {{ prompt }}
              </button>
            </div>
          </div>

          <div class="scroll-hint floatable">
            <span>Scroll for more</span>
            <span>继续向下看游侠智库能做什么</span>
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
      </section>

      <section ref="quotePanel" class="snap-panel quote-panel" :style="{ '--section-progress': quoteProgress.toFixed(3) }">
        <div class="section-inner">
          <div class="section-heading">
            <span class="section-kicker">Quick Moodboard</span>
            <h2>少一点信息噪音，多一点能落地的旅行判断。</h2>
          </div>

          <div class="vibe-grid">
            <article
              v-for="(item, index) in vibeLines"
              :key="item.title"
              class="vibe-card motion-card"
              :style="cardMotionStyle(index, quoteProgress, 30)"
            >
              <h3>{{ item.title }}</h3>
              <p>{{ item.copy }}</p>
            </article>
          </div>
        </div>
      </section>

      <section ref="journeyPanel" class="snap-panel journey-panel" :style="{ '--section-progress': journeyProgress.toFixed(3) }">
        <div class="section-inner section-inner--wide">
          <div class="section-heading">
            <span class="section-kicker">Signal, not noise</span>
            <h2>不是把信息堆给你，而是把判断先替你理顺。</h2>
          </div>

          <div class="journey-grid">
            <article
              v-for="(card, index) in journeyCards"
              :key="card.title"
              class="journey-card motion-card"
              :style="cardMotionStyle(index, journeyProgress, 34)"
            >
              <span class="journey-eyebrow">{{ card.eyebrow }}</span>
              <h3>{{ card.title }}</h3>
              <p>{{ card.copy }}</p>
            </article>
          </div>

          <button type="button" class="section-cta" @click="triggerLogin">进入游侠问答</button>
        </div>
      </section>
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

.masthead {
  position: absolute;
  top: 22px;
  left: 28px;
  right: 28px;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.masthead-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.masthead button {
  height: 40px;
  padding: 0 16px;
  border: 1px solid rgba(194, 203, 209, 0.62);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: rgba(17, 17, 17, 0.82);
  box-shadow: 0 10px 24px rgba(214, 223, 229, 0.36);
  backdrop-filter: blur(10px);
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
}

.masthead .masthead-strong {
  background: #111111;
  color: #f7fafc;
}

.portal-scroll {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
  overscroll-behavior-y: contain;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.portal-scroll::-webkit-scrollbar {
  display: none;
}

.snap-panel {
  position: relative;
  min-height: 100vh;
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 112px 12px 52px;
}

.hero-panel {
  overflow: hidden;
}

.quote-panel,
.journey-panel {
  min-height: auto;
  padding-top: 56px;
  padding-bottom: 56px;
}

.journey-panel {
  padding-top: 24px;
  padding-bottom: 72px;
}

.portal-center {
  position: relative;
  width: min(1280px, 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.hero-motion {
  opacity: var(--hero-fade, 1);
  transform: translate3d(0, var(--hero-shift, 0), 0) scale(var(--hero-scale, 1));
  transform-origin: center top;
  transition: opacity 220ms ease-out, transform 260ms ease-out;
}

.brand-stack {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.brand-icon {
  width: clamp(190px, 18vw, 260px);
  height: auto;
  object-fit: contain;
  opacity: 0.96;
  filter: drop-shadow(0 16px 24px rgba(188, 198, 206, 0.62));
}

.brand-title {
  color: rgba(21, 21, 21, 0.58);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.28em;
  text-transform: uppercase;
}

.travel-logo {
  margin-top: 16px;
  display: grid;
  gap: 0.14em;
  width: min(1200px, 100%);
  font-family: 'DM Sans', sans-serif;
  font-size: clamp(54px, 8.8vw, 118px);
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -0.055em;
  color: #111111;
  text-shadow: 0 14px 28px rgba(225, 231, 235, 0.75);
}

.hero-copy {
  width: min(920px, 100%);
  margin: 26px 0 0;
  color: rgba(17, 17, 17, 0.66);
  font-size: clamp(16px, 2.1vw, 20px);
  line-height: 1.86;
}

.search-wrap {
  margin-top: 26px;
  width: min(780px, 100%);
}

.search-shell {
  width: 100%;
  min-height: 68px;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 0 18px;
  border: 1px solid rgba(191, 202, 209, 0.78);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
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
  background: rgba(16, 17, 19, 0.94);
  color: #f6f8fb;
  font-weight: 700;
}

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
  margin-top: 18px;
}

.prompt-pill {
  border: 1px solid rgba(194, 203, 209, 0.78);
  background: rgba(255, 255, 255, 0.68);
  color: rgba(17, 17, 17, 0.8);
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 13px;
  cursor: pointer;
}

.scroll-hint {
  display: grid;
  gap: 6px;
  margin-top: 34px;
  color: rgba(21, 21, 21, 0.42);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.section-inner {
  width: min(1280px, 100%);
  display: grid;
  gap: 28px;
  opacity: calc(0.82 + (var(--section-progress, 0) * 0.18));
  transform: translate3d(0, calc((1 - var(--section-progress, 0)) * 18px), 0);
  transition: opacity 220ms ease-out, transform 280ms ease-out;
}

.section-inner--wide {
  width: min(1320px, 100%);
}

.section-heading {
  display: grid;
  gap: 12px;
}

.section-kicker {
  color: rgba(17, 17, 17, 0.44);
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.section-heading h2 {
  margin: 0;
  width: min(980px, 100%);
  font-size: clamp(34px, 5.2vw, 68px);
  line-height: 1.08;
  letter-spacing: -0.04em;
  color: #111111;
}

.quote-panel .section-inner,
.journey-panel .section-inner {
  position: relative;
}

.quote-panel .section-inner::before,
.journey-panel .section-inner::before {
  content: '';
  position: absolute;
  top: -26px;
  left: 0;
  width: min(120px, 24vw);
  height: 1px;
  background: linear-gradient(90deg, rgba(17, 17, 17, 0.18), rgba(17, 17, 17, 0));
}

.vibe-grid,
.journey-grid {
  display: grid;
  gap: 24px;
}

.vibe-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.journey-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.vibe-card,
.journey-card {
  min-height: 240px;
  padding: 34px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(190, 201, 208, 0.72);
  box-shadow: 0 22px 50px rgba(212, 220, 227, 0.48);
  backdrop-filter: blur(12px);
}

.motion-card {
  will-change: transform, opacity, filter;
  transition:
    transform 260ms cubic-bezier(0.2, 0.8, 0.2, 1),
    opacity 220ms ease-out,
    filter 280ms ease-out;
}

.vibe-card h3,
.journey-card h3 {
  margin: 0;
  font-size: 28px;
  line-height: 1.24;
  color: #111111;
}

.vibe-card p,
.journey-card p {
  margin: 14px 0 0;
  color: rgba(17, 17, 17, 0.64);
  line-height: 1.9;
  font-size: 16px;
}

.journey-eyebrow {
  display: inline-flex;
  margin-bottom: 12px;
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(17, 17, 17, 0.06);
  color: rgba(17, 17, 17, 0.62);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.section-cta {
  justify-self: start;
  border: none;
  min-width: 180px;
  height: 52px;
  padding: 0 22px;
  border-radius: 999px;
  background: #111111;
  color: #f7fafc;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
}

.orbit-note {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
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

.floatable {
  transition:
    transform 1.7s cubic-bezier(0.2, 0.8, 0.2, 1),
    opacity 0.8s ease;
}

.portal-shell.antigravity .brand-stack {
  transform: translate3d(calc(var(--pointer-x) * -4px), calc(var(--pointer-y) * -8px), 0) rotate(-1deg);
}

.portal-shell.antigravity .travel-logo {
  transform: translate3d(calc(var(--pointer-x) * -10px), calc(var(--pointer-y) * -14px), 0) rotate(-2deg);
}

.portal-shell.antigravity .search-wrap {
  transform: translate3d(calc(var(--pointer-x) * 12px), calc(var(--pointer-y) * 10px), 0) rotate(2deg);
}

.portal-shell.antigravity .scroll-hint {
  transform: translate3d(calc(var(--pointer-x) * -8px), calc(var(--pointer-y) * 10px), 0) rotate(-2deg);
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

@media (max-width: 980px) {
  .vibe-grid,
  .journey-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .masthead {
    top: 14px;
    left: 12px;
    right: 12px;
    align-items: stretch;
  }

  .masthead-actions {
    gap: 8px;
  }

  .masthead button {
    height: 38px;
    padding: 0 11px;
    font-size: 12px;
  }

  .snap-panel {
    padding: 126px 12px 40px;
  }

  .quote-panel,
  .journey-panel {
    padding-top: 44px;
    padding-bottom: 44px;
  }

  .travel-logo {
    width: min(100%, 860px);
    font-size: clamp(42px, 11vw, 68px);
    line-height: 1.12;
    gap: 0.15em;
  }

  .hero-copy {
    width: min(100%, 760px);
  }

  .search-shell {
    grid-template-columns: 24px minmax(0, 1fr);
    padding: 14px 18px;
    border-radius: 28px;
  }

  .search-login {
    grid-column: 1 / -1;
    justify-self: flex-end;
  }

  .prompt-pill {
    font-size: 12px;
  }

  .orbit-note {
    display: none;
  }
}

@media (max-height: 820px) {
  .snap-panel {
    min-height: auto;
    padding-top: 104px;
    padding-bottom: 48px;
  }

  .hero-panel {
    min-height: 100vh;
    min-height: 100dvh;
  }

  .brand-icon {
    width: clamp(160px, 15vw, 210px);
  }

  .quote-panel,
  .journey-panel {
    padding-top: 36px;
    padding-bottom: 36px;
  }
}
</style>
