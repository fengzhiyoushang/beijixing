<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { store } from '../store'
import GlowChart from '../components/GlowChart.vue'
import StatusDot from '../components/StatusDot.vue'
import { axisBase, glowBar } from '../utils/chart'
import { countdown, daysUntil, PRIORITY_LABEL, PRIORITY_TONE } from '../utils/format'

const router = useRouter()

/* ── 秒级时钟：驱动所有倒计时 ── */
const now = ref(Date.now())
let timer = null
onMounted(() => { timer = setInterval(() => (now.value = Date.now()), 1000) })
onUnmounted(() => clearInterval(timer))

const accent = computed(() => store.settings.accent)

/* ① 今日课程 */
const courses = computed(() => store.todayCourses)
const courseStat = computed(() => {
  const done = courses.value.filter((c) => c.status === 'done').length
  return { done, total: courses.value.length }
})

/* ② 今日待推进 DDL（按优先级 + 时间排序） */
const priorityWeight = { high: 0, medium: 1, low: 2 }
const ddls = computed(() =>
  store.todayDdls
    .filter((d) => d.status === 'pending')
    .slice()
    .sort((a, b) => priorityWeight[a.priority] - priorityWeight[b.priority] || new Date(a.due) - new Date(b.due)),
)

/* ③ 重要节点（按时间远近） */
const nodes = computed(() =>
  store.milestones
    .map((m) => ({ ...m, days: daysUntil(m.date), cd: countdown(m.date, now.value) }))
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .slice(0, 5),
)

/* ④ 学习数据概览 · 周时长柱状图 */
const studyBarOption = computed(() => ({
  grid: { left: 34, right: 12, top: 18, bottom: 24 },
  xAxis: { type: 'category', data: store.studyOverview.weekDays, ...axisBase(), splitLine: { show: false } },
  yAxis: { type: 'value', name: '小时', nameTextStyle: { color: '#6b7280', fontSize: 10 }, ...axisBase() },
  tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
  series: [
    {
      ...glowBar(accent.value),
      data: store.studyOverview.hours,
      barWidth: '46%',
    },
  ],
}))

/* ④ 双环形：DDL 完成率 + 考研总进度 */
function ringOption(value, color, label) {
  return {
    series: [
      {
        type: 'pie',
        radius: ['66%', '86%'],
        center: ['50%', '50%'],
        silent: true,
        label: { show: false },
        data: [
          { value, itemStyle: { color, shadowColor: color + 'aa', shadowBlur: 14 } },
          { value: 100 - value, itemStyle: { color: '#2a2a2a' } },
        ],
      },
    ],
    graphic: [
      { type: 'text', left: 'center', top: '40%', style: { text: `${value}%`, fill: color, fontSize: 18, fontWeight: 700, textAlign: 'center' } },
      { type: 'text', left: 'center', top: '62%', style: { text: label, fill: '#6b7280', fontSize: 10, textAlign: 'center' } },
    ],
  }
}
const ddlRing = computed(() => ringOption(Math.round(store.studyOverview.ddlRate), accent.value, 'DDL 完成率'))
const kaoyanRing = computed(() => ringOption(Math.round(store.studyOverview.kaoyanProgress), '#60a5fa', '考研总进度'))

/* ⑤ 知识库量化 */
const kbTrendOption = computed(() => ({
  grid: { left: 8, right: 8, top: 10, bottom: 8 },
  xAxis: { type: 'category', show: false, data: store.knowledgeStats.weekNewTrend.map((_, i) => `D${i + 1}`) },
  yAxis: { type: 'value', show: false },
  tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
  series: [
    {
      ...glowBar('#60a5fa'),
      data: store.knowledgeStats.weekNewTrend,
      barWidth: '52%',
    },
  ],
}))

function toneOf(ddl) {
  const cd = countdown(ddl.due, now.value)
  if (cd.overdue) return 'red'
  const mins = (new Date(ddl.due).getTime() - now.value) / 60000
  if (mins < 180) return 'yellow'
  return 'green'
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>战略总览</h2>
      <span class="sub mono">OVERVIEW · {{ store.profile.school }} · {{ store.profile.role }}</span>
      <span class="spacer" />
      <span class="chip chip-accent">✦ 北极星导航已就绪</span>
    </div>

    <div class="grid">
      <!-- ① 今日课程 -->
      <section class="col-4 card">
        <header class="card-head">
          <div>
            <div class="card-title">▤ 今日课程 <span class="en">TODAY CLASSES</span></div>
            <div class="panel-sub">按时间顺序排列，进行中的课程会高亮</div>
          </div>
          <span class="chip">{{ courseStat.done }}/{{ courseStat.total }} 已完成</span>
        </header>
        <div class="list">
          <div v-for="c in courses" :key="c.name" class="course-row" :class="c.status">
            <div class="c-left">
              <span class="dot" :class="c.status === 'done' ? 'dot-gray' : c.status === 'current' ? 'dot-green' : 'dot-blue'" />
              <div class="c-time mono">{{ c.time }}</div>
            </div>
            <div class="c-mid">
              <div class="c-name">{{ c.name }}</div>
              <div class="c-room mono">📍 {{ c.room }} · {{ c.teacher }}</div>
            </div>
            <span class="c-tag" :style="{ color: c.color, borderColor: c.color + '66' }">
              {{ c.status === 'done' ? '已结束' : c.status === 'current' ? '进行中' : '待开始' }}
            </span>
          </div>
        </div>
      </section>

      <!-- ② 今日待推进 DDL -->
      <section class="col-4 card">
        <header class="card-head">
          <div>
            <div class="card-title">☑ 今天要推进 <span class="en">DUE TODAY</span></div>
            <div class="panel-sub">把注意力放在真正重要的事情上</div>
          </div>
          <button class="more" @click="router.push('/notes')">查看全部 →</button>
        </header>
        <div class="list">
          <div v-for="d in ddls" :key="d.id" class="ddl-row" @click="store.toggleNote(d.id)">
            <span class="dot" :class="`dot-${toneOf(d)}`" />
            <div class="d-mid">
              <div class="d-title">{{ d.title }}</div>
              <div class="d-meta mono">
                <span class="chip" :class="`chip-${PRIORITY_TONE[d.priority]}`">{{ PRIORITY_LABEL[d.priority] }}优先</span>
                <span class="d-tag">{{ d.tag }} · 截止 {{ (d.due || '').slice(5, 16).replace('T', ' ') }}</span>
              </div>
            </div>
            <div class="d-right">
              <span class="pill" :class="countdown(d.due, now).overdue ? 'pill-red' : 'pill-accent'">
                {{ countdown(d.due, now).overdue ? '已逾期' : '待处理' }}
              </span>
              <div class="d-cd mono" :class="{ overdue: countdown(d.due, now).overdue }">
                {{ countdown(d.due, now).text }}
              </div>
            </div>
          </div>
          <div v-if="!ddls.length" class="empty">今日无待推进事项 ✦ 保持节奏</div>
        </div>
        <footer class="card-foot mono">点击条目可直接标记完成（联动「事项备忘」与快讯）</footer>
      </section>

      <!-- ⑥ 快讯头条 -->
      <section class="col-4 row-2 card news-card">
        <header class="card-head">
          <div>
            <div class="card-title">◈ 快讯头条 <span class="en">LIVE FEED</span></div>
            <div class="panel-sub">来自后端告警 / 教室采集 / 提醒推送的实时动态</div>
          </div>
          <StatusDot tone="green" label="实时" />
        </header>
        <div class="news-list">
          <div v-for="(n, i) in store.newsFeed" :key="i" class="news-row">
            <span class="n-bar" :class="`bar-${n.tone}`" />
            <div class="n-body">
              <div class="n-text">{{ n.text }}</div>
              <div class="n-meta mono">
                <span class="chip" :class="`chip-${n.tone}`">{{ n.tag }}</span>
                <span class="n-time">{{ n.time }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ③ 重要节点（参考稿：卡片网格 + 大号倒计时） -->
      <section class="col-8 card">
        <header class="card-head">
          <div>
            <div class="card-title">⏳ 重要节点 <span class="en">KEY MILESTONES</span></div>
            <div class="panel-sub">按剩余时间排序，倒计时逐秒更新</div>
          </div>
          <button class="more" @click="router.push('/kaoyan')">查看全部 →</button>
        </header>
        <div class="node-grid">
          <div v-for="m in nodes" :key="m.name" class="node-card">
            <span class="node-dot" :class="`dot-${m.tone}`" />
            <div class="node-src mono">
              {{ m.note ? m.note.slice(0, 14) : m.type }} · {{ m.type }}
            </div>
            <div class="node-title">{{ m.name }}</div>
            <div class="node-date mono">{{ (m.date || '').slice(0, 10) }}</div>
            <div
              class="node-count mono"
              :style="{ color: m.tone === 'red' ? '#f87171' : m.tone === 'yellow' ? '#fbbf24' : '#60a5fa' }"
            >
              {{ m.cd.overdue ? '已逾期' : m.cd.text }}
            </div>
          </div>
          <div v-if="!nodes.length" class="empty">暂无节点 ✦ 去「考研规划」设定目标与截止日</div>
        </div>
      </section>

      <!-- ④ 学习数据概览 -->
      <section class="col-12 card">
        <header class="card-head">
          <div>
            <div class="card-title">◱ 学习数据概览 <span class="en">STUDY METRICS</span></div>
            <div class="panel-sub">近 7 天每日学习时长 · DDL 完成率 · 考研总进度</div>
          </div>
          <span class="chip chip-accent">本周 {{ store.studyOverview.weekTotal }}h · {{ store.studyOverview.weekDelta }}</span>
        </header>
        <div class="study-body">
          <div class="study-left">
            <div class="mini-title label-3">本周每日学习时长（小时）</div>
            <GlowChart :option="studyBarOption" height="208px" />
          </div>
          <div class="study-right">
            <div class="ring-box">
              <GlowChart :option="ddlRing" height="140px" />
              <div class="ring-sub mono">{{ store.studyOverview.ddlDone }}/{{ store.studyOverview.ddlTotal }} 项已完成</div>
            </div>
            <div class="ring-box">
              <GlowChart :option="kaoyanRing" height="140px" />
              <div class="ring-sub mono">目标 {{ store.studyOverview.kaoyanTargetScore }} 分 · 当前 {{ store.studyOverview.kaoyanCurrentScore }}</div>
            </div>
          </div>
        </div>
      </section>

      <!-- ⑤ 知识库量化 -->
      <section class="col-12 card">
        <header class="card-head">
          <div>
            <div class="card-title">≡ 知识库量化 <span class="en">KNOWLEDGE BASE</span></div>
            <div class="panel-sub">文档规模 · 索引覆盖率 · 近一周入库节奏与高频标签</div>
          </div>
          <span class="chip chip-blue">RAG 命中 {{ store.knowledgeStats.ragCount }} 次</span>
        </header>
        <div class="kb-body">
          <div class="kb-stat">
            <div class="num-big">{{ store.knowledgeStats.docCount }}</div>
            <div class="label-3">文档数量</div>
          </div>
          <div class="kb-stat">
            <div class="num-big" style="color:#60a5fa; text-shadow:0 0 14px #60a5fa66">{{ store.knowledgeStats.mastery }}</div>
            <div class="label-3">索引覆盖率</div>
          </div>
          <div class="kb-stat">
            <div class="num-big" style="color:#facc15; text-shadow:0 0 14px #facc1566">+{{ store.knowledgeStats.newThisWeek }}</div>
            <div class="label-3">本周新增</div>
          </div>
          <div class="kb-chart">
            <div class="mini-title label-3">本周每日入库量</div>
            <GlowChart :option="kbTrendOption" height="64px" />
          </div>
          <div class="kb-tags">
            <div class="mini-title label-3">高频标签</div>
            <div class="tags">
              <span v-for="t in store.knowledgeStats.hotTags" :key="t" class="tag-pill">{{ t }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.008)), var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 18px 14px;
  display: flex; flex-direction: column;
  min-width: 0;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.card:hover { border-color: rgba(74, 222, 128, 0.22); box-shadow: 0 12px 34px rgba(0, 0, 0, 0.32); }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.list { display: flex; flex-direction: column; }
.card-foot { font-size: 10px; color: var(--text-3); padding-top: 8px; margin-top: auto; border-top: 1px dashed var(--border); }
.empty { color: var(--text-3); font-size: 12px; padding: 18px 0; text-align: center; }

/* 课程行 */
.course-row { display: flex; align-items: center; gap: 10px; padding: 9px 2px; border-bottom: 1px dashed var(--border); }
.course-row:last-child { border-bottom: none; }
.course-row.done { opacity: 0.5; }
.course-row.current { background: rgba(74, 222, 128, 0.05); border-radius: 8px; padding-left: 8px; }
.c-left { display: flex; align-items: center; gap: 8px; width: 108px; flex-shrink: 0; }
.c-time { font-size: 11px; color: var(--text-2); }
.c-mid { flex: 1; min-width: 0; }
.c-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-room { font-size: 10px; color: var(--text-3); margin-top: 2px; }
.c-tag { font-size: 10px; padding: 1px 8px; border: 1px solid; border-radius: 999px; flex-shrink: 0; }

/* DDL 行 */
.ddl-row { display: flex; align-items: center; gap: 10px; padding: 9px 2px; border-bottom: 1px dashed var(--border); cursor: pointer; border-radius: 8px; }
.ddl-row:hover { background: rgba(255, 255, 255, 0.025); }
.ddl-row:last-child { border-bottom: none; }
.d-mid { flex: 1; min-width: 0; }
.d-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.d-meta { display: flex; align-items: center; gap: 8px; margin-top: 3px; }
.d-tag { font-size: 10px; color: var(--text-3); }
.d-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
.d-cd { font-size: 12px; color: var(--accent); }
.d-cd.overdue { color: var(--red); }

/* 快讯 */
.news-card { min-height: 0; }
.news-list { flex: 1; overflow-y: auto; max-height: 560px; padding-right: 4px; }
.news-row { display: flex; gap: 10px; padding: 10px 2px; border-bottom: 1px solid var(--border); }
.news-row:last-child { border-bottom: none; }
.n-bar { width: 3px; border-radius: 2px; flex-shrink: 0; margin: 2px 0; background: var(--text-3); }
.bar-green { background: var(--accent); box-shadow: 0 0 10px rgba(74, 222, 128, 0.5); }
.bar-yellow { background: var(--yellow); box-shadow: 0 0 10px rgba(251, 191, 36, 0.4); }
.bar-red { background: var(--red); box-shadow: 0 0 10px rgba(248, 113, 113, 0.4); }
.bar-blue { background: var(--blue); box-shadow: 0 0 10px rgba(96, 165, 250, 0.4); }
.n-body { flex: 1; min-width: 0; }
.n-text { font-size: 12.5px; color: var(--text-1); line-height: 1.6; }
.n-meta { display: flex; align-items: center; gap: 8px; margin-top: 5px; }
.n-time { font-size: 10px; color: var(--text-3); margin-left: auto; }

/* 节点 */
/* 重要节点：卡片网格（参考稿样式） */
.node-grid {
  display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}
.node-card {
  position: relative;
  border: 1px solid var(--border); border-radius: 14px;
  padding: 12px 14px 13px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.008));
  transition: border-color 0.16s ease, transform 0.16s ease;
}
.node-card:hover { border-color: rgba(74, 222, 128, 0.3); transform: translateY(-1px); }
.node-dot { position: absolute; right: 12px; top: 13px; }
.node-src { font-size: 10px; color: var(--text-3); margin-bottom: 6px; }
.node-title { font-size: 13px; color: var(--text-1); line-height: 1.4; min-height: 36px; }
.node-date { font-size: 10.5px; color: var(--text-3); margin: 4px 0 8px; }
.node-count { font-size: 19px; font-weight: 700; letter-spacing: 0.5px; }

/* 学习数据 */
.study-body { display: flex; gap: 16px; }
.study-left { flex: 1; min-width: 0; }
.study-right { width: 210px; display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; }
.ring-box { border: 1px solid var(--border); border-radius: 10px; padding: 6px; background: rgba(255, 255, 255, 0.015); }
.ring-sub { font-size: 10px; color: var(--text-3); text-align: center; padding-bottom: 4px; }
.mini-title { font-size: 11px; margin-bottom: 6px; }

/* 知识库量化：自适应栅格，窄窗口自动换行不错位/不变形 */
.kb-body {
  display: grid;
  /* 三个指标卡固定最小宽，图表/标签弹性伸缩 */
  grid-template-columns: repeat(3, minmax(88px, 1fr)) minmax(150px, 1.15fr) minmax(170px, 1.4fr);
  gap: 16px 18px;
  align-items: center;
}
.kb-stat {
  text-align: center;
  min-width: 0;
  display: flex; flex-direction: column; align-items: center; gap: 3px;
}
.kb-stat .num-big {
  /* 长数字（如 128.6）不撑破单元格 */
  font-size: clamp(19px, 1.55vw, 26px);
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; max-width: 100%;
}
.kb-stat .label-3 { white-space: nowrap; }
.kb-chart, .kb-tags { min-width: 0; align-self: center; }
.kb-chart { display: flex; flex-direction: column; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; max-height: 68px; overflow: hidden; }
.tag-pill {
  font-size: 11px; padding: 3px 10px; border-radius: 999px;
  border: 1px solid var(--border); color: var(--text-2); background: rgba(255, 255, 255, 0.02);
  white-space: nowrap;
}
.tag-pill:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }

/* 分档降级：先让图表/标签换到第二行，再把三个指标并排 */
@media (max-width: 1360px) {
  .kb-body { grid-template-columns: repeat(3, minmax(88px, 1fr)) 1fr; }
  .kb-tags { grid-column: 1 / -1; }
  .tags { max-height: none; }
}
@media (max-width: 1080px) {
  .kb-body { grid-template-columns: repeat(3, 1fr); }
  .kb-chart, .kb-tags { grid-column: 1 / -1; }
  .tags { max-height: none; }
}
@media (max-width: 640px) {
  .kb-body { grid-template-columns: repeat(2, 1fr); }
  .kb-stat:nth-child(3) { grid-column: 1 / -1; }
}
@media (max-width: 1100px) {
  .study-body { flex-direction: column; }
  .study-right { width: 100%; flex-direction: row; }
  .ring-box { flex: 1; }
}
</style>
