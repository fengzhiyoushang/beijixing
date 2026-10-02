<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { NButton, NInput, useMessage } from 'naive-ui'
import { streamChat } from '../api'
import { store } from '../store'

const message = useMessage()

/* ── 开关状态 ── */
const opened = ref(false)       // 面板是否展开
const minimized = ref(false)    // 最小化为标题条
const dragging = ref(false)

/* ── 面板位置（拖拽后使用 left/top 绝对定位） ── */
const panel = ref(null)
const pos = reactive({ x: null, y: null })

function startDrag(e) {
  if (e.button !== 0) return
  const rect = panel.value.getBoundingClientRect()
  const offsetX = e.clientX - rect.left
  const offsetY = e.clientY - rect.top
  dragging.value = true
  const move = (ev) => {
    const maxX = window.innerWidth - 40
    const maxY = window.innerHeight - 40
    pos.x = Math.min(Math.max(ev.clientX - offsetX, 8), maxX)
    pos.y = Math.min(Math.max(ev.clientY - offsetY, 8), maxY)
  }
  const up = () => {
    dragging.value = false
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

const panelStyle = computed(() => {
  if (pos.x === null) return { right: '24px', bottom: '96px' }
  return { left: pos.x + 'px', top: pos.y + 'px', right: 'auto', bottom: 'auto' }
})

/* ── 会话 ── */
const messages = ref([
  {
    role: 'ai',
    text: '你好，我是北极星战略助手 ✦\n可以问我：今日课程、待办 DDL、空教室推荐、考研进度、本周学习时长、预算情况。',
  },
])
const input = ref('')
const typing = ref(false)
const listEl = ref(null)

const suggestions = ['今日安排', '空教室推荐', '考研差距', '本周学习时长', '预算还剩多少']

function scrollBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

/** 真实 AI：SSE 流式对话（后端 /ai/chat/stream，内部自动执行 Function Call 工具） */
const sessionId = ref(null)
let controller = null

const TOOL_LABEL = {
  get_dashboard_summary: '读取总览',
  query_schedule: '查询课表',
  add_ddl_task: '新建 DDL',
  list_ddl_tasks: '查询任务',
  complete_ddl_task: '完成任务',
  get_task_stats: '任务统计',
  log_study_record: '记录学习',
  get_study_progress: '学习进度',
  classroom_predict: '空闲教室预测',
  report_classroom_status: '上报教室状态',
  classroom_free_rate: '教室空闲率',
  get_kaoyan_gap: '考研差距',
  generate_kaoyan_plan: '生成备考计划',
  record_kaoyan_score: '录入成绩',
  search_knowledge: '检索知识库',
  rag_answer: '知识库问答',
  add_finance_record: '记一笔账',
  get_finance_summary: '财务汇总',
  log_health_record: '记录健康',
  get_health_report: '健康报告',
  take_sedentary_break: '起身提醒',
}

function send(text) {
  const q = (text ?? input.value).trim()
  if (!q || typing.value) return
  messages.value.push({ role: 'user', text: q })
  input.value = ''
  scrollBottom()

  typing.value = true
  const item = reactive({ role: 'ai', text: '', tools: [] })
  messages.value.push(item)

  controller = streamChat(
    { message: q, session_id: sessionId.value, use_tools: true, use_rag: true },
    {
      onMeta: (data) => {
        if (data.session_id) sessionId.value = data.session_id
      },
      onTool: (trace) => {
        item.tools.push({
          name: trace.name,
          label: TOOL_LABEL[trace.name] || trace.name,
          ok: trace.ok !== false,
          error: trace.result?.error,
        })
        scrollBottom()
      },
      onToken: (chunk) => {
        item.text += chunk
        scrollBottom()
      },
      onDone: (data) => {
        typing.value = false
        if (data?.session_id) sessionId.value = data.session_id
        if (!item.text) item.text = '（模型未返回内容）'
        scrollBottom()
        // 工具可能已经改动了数据（新建任务/记账等），刷新看板
        if (item.tools.length) store.refresh()
      },
      onError: (err) => {
        typing.value = false
        item.text = item.text || `⚠ ${err.message}`
        message.error(err.message)
      },
    },
  )
}

function stop() {
  controller?.abort()
  controller = null
  typing.value = false
}

function toggleMinimize() { minimized.value = !minimized.value }
function closePanel() { opened.value = false; minimized.value = false }
function resetChat() {
  sessionId.value = null
  messages.value = [{ role: 'ai', text: '已开启新会话 ✦ 有什么可以帮你？' }]
  message.success('已开启新会话')
}

/* 快捷键：Ctrl/⌘ + K 唤起 */
function onKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    opened.value = true
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <!-- 悬浮按钮 -->
  <button v-if="!opened" class="fab" title="北极星 AI 助手（Ctrl+K）" @click="opened = true">
    <span class="fab-star">✦</span>
    <span class="fab-ring" />
    <span class="fab-badge mono">AI</span>
  </button>

  <!-- 聊天面板 -->
  <div
    v-if="opened"
    ref="panel"
    class="panel"
    :class="{ minimized, dragging }"
    :style="panelStyle"
  >
    <header class="p-head" @mousedown="startDrag">
      <div class="p-title">
        <span class="p-star">✦</span>
        北极星 AI 助手
        <span class="p-sub mono">POLARIS COPILOT</span>
      </div>
      <div class="p-actions" @mousedown.stop>
        <button class="act" :title="minimized ? '展开' : '最小化'" @click="toggleMinimize">{{ minimized ? '▢' : '—' }}</button>
        <button class="act" title="新会话" @click="resetChat">⟳</button>
        <button class="act close" title="关闭" @click="closePanel">✕</button>
      </div>
    </header>

    <template v-if="!minimized">
      <div ref="listEl" class="p-body">
        <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
          <div class="bubble">
            <span class="who mono">{{ m.role === 'ai' ? 'AI' : 'ME' }}</span>
            <div v-if="m.tools && m.tools.length" class="tool-chips">
              <span
                v-for="(t, ti) in m.tools" :key="ti"
                class="tool-chip mono" :class="{ bad: !t.ok }"
                :title="t.error || '已执行'"
              >⚙ {{ t.label }}</span>
            </div>
            <pre class="text">{{ m.text }}</pre>
          </div>
        </div>
        <div v-if="typing" class="msg ai">
          <div class="bubble"><span class="who mono">AI</span><span class="cursor">▊</span></div>
        </div>
      </div>

      <div class="p-sug">
        <button v-for="s in suggestions" :key="s" class="sug" @click="send(s)">{{ s }}</button>
      </div>

      <footer class="p-foot">
        <NInput
          v-model:value="input"
          size="small"
          placeholder="询问课程 / DDL / 教室 / 考研进度…（Enter 发送）"
          @keyup.enter="send()"
        />
        <NButton v-if="typing" size="small" quaternary type="error" @click="stop">停止</NButton>
        <NButton v-else size="small" type="primary" @click="send()">发送</NButton>
      </footer>
      <div class="p-tip mono">拖动标题栏可移动 · Ctrl+K 唤起 · 已接入后端 DeepSeek（Function Call 可读写数据）</div>
    </template>
  </div>
</template>

<style scoped>
/* 悬浮按钮 */
.fab {
  position: fixed; right: 26px; bottom: 26px; z-index: 90;
  width: 58px; height: 58px; border-radius: 50%; cursor: pointer;
  background: radial-gradient(circle at 30% 30%, #1f2a22, #14161a);
  border: 1px solid rgba(74, 222, 128, 0.5);
  display: grid; place-items: center;
  box-shadow: 0 0 22px rgba(74, 222, 128, 0.25), 0 8px 24px rgba(0, 0, 0, 0.5);
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.fab:hover { transform: translateY(-2px) scale(1.04); box-shadow: 0 0 30px rgba(74, 222, 128, 0.45); }
.fab-star { color: var(--accent); font-size: 24px; text-shadow: 0 0 14px var(--accent); }
.fab-ring {
  position: absolute; inset: -6px; border-radius: 50%;
  border: 1px solid rgba(74, 222, 128, 0.35);
  animation: ringPulse 2.6s ease-out infinite;
}
@keyframes ringPulse {
  0% { transform: scale(0.85); opacity: 0.9; }
  70% { transform: scale(1.18); opacity: 0; }
  100% { opacity: 0; }
}
.fab-badge {
  position: absolute; right: -2px; bottom: -2px;
  font-size: 9px; padding: 1px 5px; border-radius: 999px;
  background: var(--accent); color: #05130a; font-weight: 700;
}

/* 面板（参考稿：深色半透明 · 圆角 16 · 无气泡式的 AI 文本） */
.panel {
  position: fixed; z-index: 95;
  width: 392px; max-width: calc(100vw - 40px);
  background: rgba(19, 25, 23, 0.94);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  box-shadow: 0 22px 60px rgba(0, 0, 0, 0.62), 0 0 34px rgba(74, 222, 128, 0.08);
  display: flex; flex-direction: column;
  overflow: hidden;
  backdrop-filter: blur(14px);
}
.dragging { user-select: none; cursor: grabbing; }

.p-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; cursor: grab;
  background: linear-gradient(90deg, rgba(74, 222, 128, 0.1), transparent);
  border-bottom: 1px solid var(--border);
}
.p-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; }
.p-star { color: var(--accent); text-shadow: 0 0 12px var(--accent); }
.p-sub { font-size: 9px; color: var(--text-3); letter-spacing: 1px; font-weight: 400; }
.p-actions { display: flex; gap: 4px; }
.act {
  width: 24px; height: 24px; border-radius: 6px; cursor: pointer;
  background: transparent; border: 1px solid transparent; color: var(--text-2); font-size: 12px;
}
.act:hover { background: rgba(255, 255, 255, 0.05); color: var(--text-1); }
.act.close:hover { color: var(--red); border-color: rgba(248, 113, 113, 0.4); }

.p-body { height: 320px; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.minimized .p-body { display: none; }

.msg { display: flex; }
.msg.user { justify-content: flex-end; }
/* AI 消息：无气泡，纯文本（参考稿样式） */
.bubble { max-width: 92%; }
.msg.ai .bubble { background: transparent; border: none; padding: 0 2px; }
.msg.user .bubble {
  padding: 7px 11px; border-radius: 12px;
  background: rgba(255, 255, 255, 0.07); border: 1px solid var(--border);
}
.who { display: block; font-size: 9px; color: var(--text-3); margin-bottom: 4px; letter-spacing: 1px; }
.tool-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.tool-chip {
  font-size: 9.5px; padding: 1px 7px; border-radius: 999px;
  border: 1px solid rgba(74, 222, 128, 0.35); color: var(--accent);
  background: rgba(74, 222, 128, 0.08);
}
.tool-chip.bad { border-color: rgba(248, 113, 113, 0.4); color: #f87171; background: rgba(248, 113, 113, 0.08); }
.text { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; color: var(--text-1); line-height: 1.7; }
.msg.ai .text { color: #c9d4cd; }
.cursor { color: var(--accent); animation: blink 1s steps(2) infinite; }
@keyframes blink { 50% { opacity: 0; } }

.p-sug { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 12px 10px; }
.sug {
  font-size: 11px; padding: 3px 10px; border-radius: 999px; cursor: pointer;
  background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); color: var(--text-2);
}
.sug:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.45); }

.p-foot { display: flex; gap: 8px; padding: 10px 12px; border-top: 1px solid var(--border); align-items: center; }
.p-tip { padding: 0 12px 10px; font-size: 10px; color: var(--text-3); text-align: center; }

@media (max-width: 520px) {
  .panel { width: calc(100vw - 24px); }
}
</style>
