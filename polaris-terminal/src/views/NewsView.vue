<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NInput, NModal, NSwitch, NPopconfirm, useMessage } from 'naive-ui'
import { store } from '../store'
import { newsApi } from '../api'
import { API_BASE } from '../api/http'
import { openExternal } from '../utils/openExternal'

const message = useMessage()

/** 外链配图走后端代理，绕过源站 Referer 防盗链 */
function imgSrc(url) {
  if (!url) return ''
  return `${API_BASE}/news/image?url=${encodeURIComponent(url)}`
}

/* ── 筛选 ── */
const CATS = [
  { key: '全部', icon: '✦' },
  { key: '财经', icon: '📈' },
  { key: '科技', icon: '🚀' },
  { key: '考研就业', icon: '🎓' },
]
const activeCat = ref('全部')
const keyword = ref('')
const unreadOnly = ref(false)
const starredOnly = ref(false)
const page = ref(0)
const PAGE_SIZE = 24

const catStats = computed(() => {
  const map = {}
  store.news.categories.forEach((c) => { map[c.category] = c })
  return map
})

const visible = computed(() => store.news.items)
const hasMore = computed(() => store.news.items.length < store.news.total)

function queryParams(extra = {}) {
  return {
    category: activeCat.value === '全部' ? undefined : activeCat.value,
    keyword: keyword.value.trim() || undefined,
    unread_only: unreadOnly.value || undefined,
    starred_only: starredOnly.value || undefined,
    limit: PAGE_SIZE,
    offset: 0,
    ...extra,
  }
}

async function reload(append = false) {
  if (!append) page.value = 0
  const params = queryParams({ offset: append ? store.news.items.length : 0 })
  store.news.loading = true
  try {
    const [list, cats] = await Promise.all([newsApi.items(params), newsApi.categories()])
    store.news.items = append ? [...store.news.items, ...(list?.items || [])] : (list?.items || [])
    store.news.total = list?.total || 0
    store.news.categories = cats?.items || []
  } catch (err) {
    message.error('加载失败：' + err.message)
  } finally {
    store.news.loading = false
  }
}

function switchCat(c) {
  activeCat.value = c
  reload()
}

/* ── 抓取（轮询状态）── */
let pollTimer = null
async function startCrawl(force = false) {
  try {
    const r = await store.newsCrawl(force)
    if (!r?.started) { message.info(r?.reason || '抓取未启动'); return }
    message.info('抓取已在后台启动：通用发现 → 增量去重 → 聚焦补全正文')
    pollTimer = setInterval(async () => {
      try {
        const s = await newsApi.crawlStatus()
        store.news.crawling = !!s?.running
        if (!s?.running) {
          clearInterval(pollTimer); pollTimer = null
          await reload()
          store.news.logs = (await newsApi.logs(8))?.items || []
          const res = s?.last_result || {}
          if (res.error) message.error('抓取异常：' + res.error)
          else message.success(`抓取完成：发现 ${res.found ?? 0} 条，新增 ${res.new ?? 0} 条，聚焦补全 ${res.enriched ?? 0} 条`)
        }
      } catch { /* 忽略轮询失败 */ }
    }, 2500)
  } catch (err) {
    message.error(err.message)
  }
}
onUnmounted(() => pollTimer && clearInterval(pollTimer))

/* ── 详情 ── */
const detail = ref(null)
const detailShow = ref(false)          // 弹窗显隐必须是独立布尔量，不能复用详情对象
const detailLoading = ref(false)
async function openDetail(item) {
  if (!item?.id) { message.warning('该条目缺少 ID，无法打开'); return }
  detailShow.value = true
  detailLoading.value = true
  detail.value = { ...item, content: '' }
  try {
    const full = await newsApi.detail(item.id)
    // 用户可能在请求返回前已关闭弹窗或点了别的条目
    if (!detailShow.value) return
    detail.value = full
    if (!item.is_read) { item.is_read = true; store.newsSetRead(item.id, true) }
  } catch (err) {
    if (detailShow.value) {
      // 详情接口失败时保留列表已有摘要，避免弹窗完全空白
      detail.value = { ...item, content: item.summary || '' }
      message.error('正文加载失败：' + err.message)
    }
  } finally {
    detailLoading.value = false
  }
}
function closeDetail() {
  detailShow.value = false
  detail.value = null
}
function openOriginal() {
  const url = detail.value?.url
  if (!url) { message.warning('该条目缺少原文链接'); return }
  openExternal(url)
}

async function toggleStar(item) {
  await store.newsSetStar(item.id, !item.is_starred)
  if (starredOnly.value) reload()
}

/* ── 源管理 ── */
const showSources = ref(false)
const srcForm = ref({ name: '', url: '', category: '综合', mode: 'rss', interval_min: 30 })
async function loadSources() { await store.loadNewsSources() }
async function addSource() {
  if (!srcForm.value.name.trim() || !srcForm.value.url.trim()) { message.warning('请填写名称与地址'); return }
  try {
    await newsApi.createSource(srcForm.value)
    await loadSources()
    srcForm.value = { name: '', url: '', category: '综合', mode: 'rss', interval_min: 30 }
    message.success('已添加抓取源')
  } catch (err) { message.error(err.message) }
}
async function toggleSource(s) {
  try {
    await newsApi.updateSource(s.id, { ...s, enabled: !s.enabled })
    await loadSources()
  } catch (err) { message.error(err.message) }
}
async function removeSource(s) {
  await newsApi.removeSource(s.id)
  await loadSources()
}

/* ── 时间显示 ── */
function ago(iso) {
  if (!iso) return '—'
  const t = new Date(iso.replace(' ', 'T')).getTime()
  const diff = (Date.now() - t) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return iso.slice(0, 10)
}
const CAT_COLOR = { '财经': '#facc15', '科技': '#60a5fa', '考研就业': '#c084fc', '综合': '#4ade80' }

/* 首条作为焦点大图卡 */
const featured = computed(() => (!keyword.value && activeCat.value === '全部' && visible.value.length > 4) ? visible.value[0] : null)
const rest = computed(() => (featured.value ? visible.value.slice(1) : visible.value))

onMounted(async () => {
  await reload()
  try { store.news.logs = (await newsApi.logs(6))?.items || [] } catch { /* 忽略 */ }
})
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h2 class="title">📰 新闻资讯 <span class="en">NEWS FEED</span></h2>
      </div>
      <div class="hbtns">
        <NButton size="small" tertiary @click="showSources = true; loadSources()">⛓ 抓取源（{{ store.news.sources.length || '…' }}）</NButton>
        <NButton size="small" :loading="store.news.crawling" type="primary" @click="startCrawl(false)">
          {{ store.news.crawling ? '抓取中…' : '⟳ 更新资讯' }}
        </NButton>
      </div>
    </header>

    <div class="toolbar">
      <div class="cats">
        <button v-for="c in CATS" :key="c.key" class="cat" :class="{ on: activeCat === c.key }" @click="switchCat(c.key)">
          <span>{{ c.icon }} {{ c.key }}</span>
          <span v-if="catStats[c.key]?.unread" class="badge mono">{{ catStats[c.key].unread }}</span>
        </button>
      </div>
      <div class="filters">
        <label class="sw"><span>仅未读</span><NSwitch v-model:value="unreadOnly" size="small" @update:value="reload()" /></label>
        <label class="sw"><span>★ 收藏</span><NSwitch v-model:value="starredOnly" size="small" @update:value="reload()" /></label>
        <NInput v-model:value="keyword" size="small" placeholder="搜索标题…" clearable style="width:180px" @keyup.enter="reload()" @clear="reload()" />
        <button class="mini" @click="reload()">搜索</button>
      </div>
    </div>

    <!-- 焦点卡 -->
    <div v-if="featured" class="hero" :style="{ '--hc': CAT_COLOR[featured.category] || '#4ade80' }" @click="openDetail(featured)">
      <div class="hero-media">
        <div class="hero-ph">✦</div>
        <img v-if="featured.image_url" :src="imgSrc(featured.image_url)" class="hero-img" loading="lazy" @error="(e) => (e.target.style.display = 'none')" />
      </div>
      <div class="hero-body">
        <span class="tag" :style="{ color: 'var(--hc)', borderColor: 'color-mix(in srgb, var(--hc) 45%, transparent)' }">{{ featured.category }} · 头条</span>
        <div class="hero-title">{{ featured.title }}</div>
        <div class="hero-sum">{{ featured.summary || '（点击查看详情）' }}</div>
        <div class="hero-meta mono">{{ featured.source_name }} · {{ ago(featured.published_at) }} ↗</div>
      </div>
    </div>

    <!-- 列表 -->
    <div v-if="store.news.loading && !visible.length" class="empty">加载中…</div>
    <div v-else-if="!visible.length" class="empty">
      <div class="e-ico">🗞</div>
      <div>暂无资讯，点击右上角「⟳ 更新资讯」抓取一批</div>
    </div>
    <div class="grid">
      <article v-for="n in rest" :key="n.id" class="card" :class="{ unread: !n.is_read }" :style="{ '--hc': CAT_COLOR[n.category] || '#4ade80' }" @click="openDetail(n)">
        <div class="c-img-wrap">
          <div class="c-img-ph" :style="{ background: `linear-gradient(140deg, color-mix(in srgb, var(--hc) 22%, transparent), rgba(255,255,255,.02))` }">
            <span>{{ n.category === '财经' ? '📈' : n.category === '科技' ? '🚀' : n.category === '考研就业' ? '🎓' : '✦' }}</span>
          </div>
          <img v-if="n.image_url" :src="imgSrc(n.image_url)" class="c-img" loading="lazy" @error="(e) => e.target.style.display = 'none'" />
          <button class="star" :class="{ on: n.is_starred }" @click.stop="toggleStar(n)" title="收藏">★</button>
        </div>
        <div class="c-body">
          <div class="c-tags">
            <span class="tag" :style="{ color: 'var(--hc)', borderColor: 'color-mix(in srgb, var(--hc) 40%, transparent)' }">{{ n.category }}</span>
            <span v-for="t in (n.tags || []).slice(0, 2)" :key="t" class="tag gray">{{ t }}</span>
          </div>
          <h3 class="c-title">{{ n.title }}</h3>
          <p class="c-sum">{{ n.summary }}</p>
          <div class="c-meta mono">
            <span>{{ n.source_name }}</span>
            <span>{{ ago(n.published_at) }}</span>
          </div>
        </div>
      </article>
    </div>

    <div v-if="hasMore && !store.news.loading" class="more-row">
      <NButton size="small" tertiary :loading="store.news.loading" @click="reload(true)">加载更多（剩余 {{ store.news.total - store.news.items.length }} 条）</NButton>
    </div>

    <!-- 抓取日志 -->
    <div v-if="store.news.logs.length" class="logs card-glass">
      <div class="lg-title mono">⚙ 最近抓取</div>
      <div v-for="l in store.news.logs" :key="l.id" class="lg-row mono">
        <span class="lg-stage" :class="l.stage">{{ { general: '通用', focused: '聚焦', incremental: '增量' }[l.stage] || l.stage }}</span>
        <span class="lg-src">{{ l.source_name || '—' }}</span>
        <span>发现 {{ l.found }} · 新增 {{ l.new_items }}<template v-if="l.enriched"> · 补全 {{ l.enriched }}</template></span>
        <span :class="l.ok ? 'ok' : 'bad'">{{ l.ok ? '✓' : '✗ ' + (l.message || '').slice(0, 40) }}</span>
        <span class="lg-time">{{ (l.created_at || '').slice(5, 16) }}</span>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <NModal :show="detailShow" preset="card" style="width:680px; max-width:94vw" :bordered="false"
            :title="detail ? (detail.category + ' · ' + (detail.source_name || '')) : '新闻详情'"
            @update:show="(v) => { if (!v) closeDetail() }">
      <div v-if="detail" class="d-wrap">
        <h2 class="d-title">{{ detail.title }}</h2>
        <div class="d-meta mono">
          <span>{{ detail.published_at || '' }}</span>
          <span v-if="detail.author">· {{ detail.author }}</span>
          <button class="d-star" :class="{ on: detail.is_starred }" @click="toggleStar(detail)">★ 收藏</button>
        </div>
        <img v-if="detail.image_url" :src="imgSrc(detail.image_url)" class="d-img" loading="lazy" @error="(e) => (e.target.style.display = 'none')" />
        <div v-if="detailLoading" class="d-load">加载正文…</div>
        <pre v-else class="d-content">{{ detail.content || detail.summary || '（该条目暂无正文，点击下方按钮阅读原文）' }}</pre>
        <div class="d-note mono">正文仅作本地缓存供个人阅读，完整内容请以原文为准。</div>
      </div>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="closeDetail">关闭</NButton>
          <NButton type="primary" :disabled="!detail?.url" @click="openOriginal">在 Edge 中打开原文 ↗</NButton>
        </div>
      </template>
    </NModal>

    <!-- 源管理弹窗 -->
    <NModal v-model:show="showSources" preset="card" title="抓取源管理" style="width:640px; max-width:94vw" :bordered="false">
      <div class="src-add">
        <NInput v-model:value="srcForm.name" size="small" placeholder="名称" style="width:130px" />
        <NInput v-model:value="srcForm.url" size="small" placeholder="RSS / JSON 地址" style="flex:1" />
        <NInput v-model:value="srcForm.category" size="small" placeholder="分类" style="width:96px" />
        <NButton size="small" type="primary" @click="addSource">添加</NButton>
      </div>
      <div class="src-list">
        <div v-for="s in store.news.sources" :key="s.id" class="src" :class="{ off: !s.enabled }">
          <div class="s-main">
            <div class="s-name">{{ s.name }}<span class="tag gray" style="margin-left:8px">{{ s.category }}</span></div>
            <div class="s-url mono">{{ s.url }}</div>
          </div>
          <div class="s-ops">
            <span class="s-int mono">≥{{ s.interval_min }}分钟</span>
            <NSwitch :value="s.enabled" size="small" @update:value="() => toggleSource(s)" />
            <NPopconfirm @positive-click="removeSource(s)">
              <template #trigger><button class="s-del">×</button></template>
              删除该源？
            </NPopconfirm>
          </div>
        </div>
      </div>
      <div class="src-tip mono">合规抓取：仅公开 RSS/页面 · 串行限速 · 不绕过防护 · 内容版权归原始来源</div>
    </NModal>
  </div>
</template>

<style scoped>
.page { padding: 20px 24px 40px; }
.head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.title { margin: 0; font-size: 20px; letter-spacing: .5px; }
.en { font-size: 11px; color: var(--text-3); letter-spacing: 2px; margin-left: 6px; }
.desc { margin: 6px 0 0; font-size: 12px; color: var(--text-3); }
.hbtns { display: flex; gap: 8px; }

.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 16px 0 14px; flex-wrap: wrap; }
.cats { display: flex; gap: 8px; flex-wrap: wrap; }
.cat { display: flex; align-items: center; gap: 6px; font-size: 12.5px; padding: 5px 14px; border-radius: 999px; cursor: pointer; background: rgba(255,255,255,.02); border: 1px solid var(--border); color: var(--text-2); transition: all .15s; }
.cat:hover { color: var(--accent); border-color: rgba(74,222,128,.4); }
.cat.on { color: var(--accent); border-color: rgba(74,222,128,.5); background: rgba(74,222,128,.12); box-shadow: 0 0 14px rgba(74,222,128,.15); }
.badge { font-size: 9.5px; background: var(--accent); color: #06170d; border-radius: 999px; padding: 0 6px; font-weight: 700; }
.filters { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.sw { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-2); }
.mini { font-size: 11.5px; padding: 3px 12px; border-radius: 8px; border: 1px solid var(--border); background: transparent; color: var(--text-2); cursor: pointer; }
.mini:hover { color: var(--accent); border-color: rgba(74,222,128,.4); }

/* 焦点卡 */
.hero { position: relative; display: grid; grid-template-columns: 300px 1fr; gap: 0; border-radius: 18px; overflow: hidden; border: 1px solid var(--border); cursor: pointer; margin-bottom: 18px; background: rgba(255,255,255,.02); transition: border-color .2s, box-shadow .2s; }
.hero:hover { border-color: color-mix(in srgb, var(--hc) 50%, transparent); box-shadow: 0 10px 34px rgba(0,0,0,.45), 0 0 22px color-mix(in srgb, var(--hc) 14%, transparent); }
.hero-media { position: relative; min-height: 170px; overflow: hidden; }
.hero-img, .hero-ph { width: 100%; height: 100%; min-height: 170px; object-fit: cover; }
.hero-ph { position: absolute; inset: 0; display: grid; place-items: center; font-size: 44px; color: var(--hc); background: linear-gradient(150deg, color-mix(in srgb, var(--hc) 16%, transparent), transparent); }
.hero-img { position: relative; z-index: 1; }
.hero-body { padding: 18px 20px; display: flex; flex-direction: column; gap: 9px; justify-content: center; }
.hero-title { font-size: 18px; font-weight: 700; line-height: 1.45; color: var(--text-1); }
.hero-sum { font-size: 12.5px; color: var(--text-2); line-height: 1.7; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.hero-meta { font-size: 10.5px; color: var(--text-3); }

.tag { font-size: 10.5px; padding: 1px 9px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-2); width: fit-content; }
.tag.gray { color: var(--text-3); }

.empty { text-align: center; color: var(--text-3); font-size: 13px; padding: 60px 0; }
.e-ico { font-size: 34px; margin-bottom: 10px; }

/* 卡片网格 */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(272px, 1fr)); gap: 14px; }
.card { position: relative; border-radius: 15px; overflow: hidden; cursor: pointer; background: linear-gradient(165deg, rgba(255,255,255,.035), rgba(255,255,255,.012)); border: 1px solid var(--border); transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
.card:hover { transform: translateY(-3px); border-color: color-mix(in srgb, var(--hc) 55%, transparent); box-shadow: 0 12px 30px rgba(0,0,0,.45), 0 0 20px color-mix(in srgb, var(--hc) 15%, transparent); }
.card.unread::after { content: ''; position: absolute; top: 10px; left: 10px; width: 7px; height: 7px; border-radius: 50%; background: var(--hc); box-shadow: 0 0 10px var(--hc); z-index: 2; }
.c-img-wrap { position: relative; height: 128px; overflow: hidden; }
.c-img { position: absolute; inset: 0; z-index: 1; width: 100%; height: 100%; object-fit: cover; }
.c-img-ph { position: absolute; inset: 0; width: 100%; height: 100%; display: grid; place-items: center; font-size: 30px; }
.star { position: absolute; right: 8px; top: 8px; z-index: 3; width: 26px; height: 26px; border-radius: 8px; border: 1px solid var(--border); background: rgba(10,14,12,.6); color: var(--text-3); cursor: pointer; font-size: 13px; backdrop-filter: blur(4px); transition: all .15s; }
.star:hover, .star.on { color: #facc15; border-color: rgba(250,204,21,.5); text-shadow: 0 0 10px rgba(250,204,21,.6); }
.c-body { padding: 11px 13px 12px; display: flex; flex-direction: column; gap: 7px; }
.c-tags { display: flex; gap: 5px; flex-wrap: wrap; }
.c-title { margin: 0; font-size: 13.5px; font-weight: 650; line-height: 1.5; color: var(--text-1); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.c-sum { margin: 0; font-size: 11.5px; color: var(--text-2); line-height: 1.65; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.c-meta { display: flex; justify-content: space-between; font-size: 10px; color: var(--text-3); margin-top: 2px; }

.more-row { text-align: center; margin-top: 18px; }

/* 抓取日志 */
.logs { margin-top: 22px; border-radius: 14px; border: 1px solid var(--border); background: rgba(255,255,255,.02); padding: 12px 16px; }
.lg-title { font-size: 11px; color: var(--text-3); margin-bottom: 8px; letter-spacing: 1px; }
.lg-row { display: flex; align-items: center; gap: 14px; font-size: 10.5px; color: var(--text-2); padding: 4px 0; border-top: 1px dashed rgba(255,255,255,.05); flex-wrap: wrap; }
.lg-stage { padding: 1px 8px; border-radius: 999px; font-size: 9.5px; }
.lg-stage.general { color: #60a5fa; background: rgba(96,165,250,.1); }
.lg-stage.incremental { color: #4ade80; background: rgba(74,222,128,.1); }
.lg-stage.focused { color: #c084fc; background: rgba(192,132,252,.1); }
.lg-src { color: var(--text-1); max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ok { color: #4ade80; }
.bad { color: #f87171; }
.lg-time { margin-left: auto; color: var(--text-3); }

/* 详情 */
.d-wrap { display: flex; flex-direction: column; gap: 10px; max-height: 62vh; overflow-y: auto; }
.d-title { margin: 0; font-size: 17px; line-height: 1.5; }
.d-meta { display: flex; align-items: center; gap: 10px; font-size: 11px; color: var(--text-3); }
.d-star { margin-left: auto; background: none; border: 1px solid var(--border); color: var(--text-3); border-radius: 999px; padding: 2px 10px; font-size: 11px; cursor: pointer; }
.d-star.on { color: #facc15; border-color: rgba(250,204,21,.5); }
.d-img { border-radius: 12px; max-height: 260px; object-fit: cover; width: 100%; }
.d-load { color: var(--text-3); font-size: 12px; padding: 20px 0; text-align: center; }
.d-content { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; line-height: 1.85; color: var(--text-1); }
.d-note { font-size: 10.5px; color: var(--text-3); border-top: 1px dashed var(--border); padding-top: 8px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }

/* 源管理 */
.src-add { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.src-list { max-height: 40vh; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.src { display: flex; align-items: center; justify-content: space-between; gap: 10px; border: 1px solid var(--border); border-radius: 10px; padding: 8px 12px; }
.src.off { opacity: .5; }
.s-main { min-width: 0; }
.s-name { font-size: 12.5px; font-weight: 600; }
.s-url { font-size: 10px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 380px; }
.s-ops { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.s-int { font-size: 10px; color: var(--text-3); }
.s-del { background: none; border: none; color: var(--text-3); cursor: pointer; font-size: 15px; }
.s-del:hover { color: #f87171; }
.src-tip { margin-top: 12px; font-size: 10.5px; color: var(--text-3); }

@media (max-width: 760px) {
  .hero { grid-template-columns: 1fr; }
  .hero-img, .hero-ph { min-height: 140px; }
}
</style>
