<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { NButton, NSwitch, NPopconfirm, useMessage } from 'naive-ui'
import { aiApi } from '../api'
import { streamChat } from '../api/http'
import { store } from '../store'

const message = useMessage()

/* ── 会话列表 ── */
const sessions = ref([])
const currentId = ref(null)
const loadingHistory = ref(false)

async function loadSessions() {
  try {
    const r = await aiApi.sessions(50)
    sessions.value = r.items || []
  } catch (err) { message.error('会话列表加载失败：' + err.message) }
}

async function openSession(id) {
  if (streaming.value) stopStream()
  currentId.value = id
  loadingHistory.value = true
  messages.value = []
  try {
    const s = await aiApi.session(id)
    messages.value = (s.messages || [])
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m) => ({ role: m.role, content: m.content, tools: m.tool_calls || [], time: m.created_at }))
    scrollToBottom()
  } catch (err) { message.error('会话加载失败：' + err.message) }
  finally { loadingHistory.value = false }
}

async function newSession() {
  if (streaming.value) stopStream()
  currentId.value = null
  messages.value = []
  input.value = ''
}

async function removeSession(id) {
  try {
    await aiApi.removeSession(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (currentId.value === id) await newSession()
    message.success('会话已删除')
  } catch (err) { message.error('删除失败：' + err.message) }
}

/* ── 对话 ── */
const messages = ref([])
const input = ref('')
const streaming = ref(false)
const useTools = ref(true)
const useRag = ref(false)
const listRef = ref(null)
let streamCtl = null

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  messages.value.push({ role: 'user', content: text, time: new Date().toISOString() })
  input.value = ''

  const reply = { role: 'assistant', content: '', tools: [], time: new Date().toISOString(), pending: true }
  messages.value.push(reply)
  streaming.value = true
  scrollToBottom()

  streamCtl = streamChat(
    { message: text, session_id: currentId.value, use_tools: useTools.value, use_rag: useRag.value },
    {
      onMeta: (d) => { currentId.value = d.session_id },
      onTool: (t) => {
        reply.tools.push({ name: t.name, arguments: t.arguments, ok: t.ok !== false, round: t.round })
        scrollToBottom()
      },
      onToken: (c) => { reply.content += c; scrollToBottom() },
      onDone: (d) => {
        reply.pending = false; streaming.value = false; streamCtl = null; loadSessions()
        store.applyTokenSummary(d?.token_summary)
      },
      onError: (e) => {
        reply.pending = false
        reply.error = e.message || 'AI 服务异常'
        if (!reply.content) reply.content = ''
        streaming.value = false
        streamCtl = null
        message.error('生成失败：' + e.message)
      },
    },
  )
}

function stopStream() {
  streamCtl?.abort()
  streamCtl = null
  streaming.value = false
  const last = messages.value[messages.value.length - 1]
  if (last?.pending) last.pending = false
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
}

/* ── 工具清单 ── */
const tools = ref([])
const showTools = ref(false)
async function loadTools() {
  if (tools.value.length) { showTools.value = true; return }
  try {
    const r = await aiApi.tools()
    tools.value = r.items || []
    showTools.value = true
  } catch (err) { message.error('工具清单加载失败：' + err.message) }
}

/* AI 运行模式徽标 */
const aiMode = ref('')
onMounted(async () => {
  loadSessions()
  try { aiMode.value = (await aiApi.status())?.ai?.mode || 'mock' } catch { aiMode.value = 'mock' }
})
onBeforeUnmount(() => { streamCtl?.abort() })

const hasChat = computed(() => messages.value.length > 0)
</script>

<template>
  <div class="ai-page">
    <!-- 左：会话列表 -->
    <aside class="side">
      <NButton size="small" type="primary" block @click="newSession">＋ 新对话</NButton>
      <div class="sess-list">
        <div v-if="!sessions.length" class="sess-empty mono">暂无历史会话</div>
        <div v-for="s in sessions" :key="s.id" class="sess" :class="{ on: s.id === currentId }" @click="openSession(s.id)">
          <div class="s-title">{{ s.title || '未命名会话' }}</div>
          <div class="s-meta mono">
            <span>{{ s.message_count }} 条</span>
            <NPopconfirm @positive-click.stop="removeSession(s.id)">
              <template #trigger><button class="s-del" @click.stop>×</button></template>
              删除该会话？
            </NPopconfirm>
          </div>
        </div>
      </div>
      <div class="side-foot">
        <button class="tool-link" @click="loadTools">⚙ 可用工具（{{ tools.length || '…' }}）</button>
        <span class="mode-chip" :class="aiMode">{{ aiMode === 'live' ? 'AI LIVE' : 'AI 演示模式' }}</span>
      </div>
    </aside>

    <!-- 右：对话区 -->
    <section class="chat card">
      <header class="chat-head">
        <div class="card-title">✦ AI 助手 <span class="en">ASSISTANT</span></div>
        <div class="opts">
          <label class="opt"><span>Function Call</span><NSwitch v-model:value="useTools" size="small" /></label>
          <label class="opt"><span>知识库 RAG</span><NSwitch v-model:value="useRag" size="small" /></label>
        </div>
      </header>

      <div ref="listRef" class="msg-list">
        <div v-if="!hasChat && !loadingHistory" class="welcome">
          <div class="w-star">✦</div>
          <div class="w-title">我是你的北极星助手</div>
          <div class="w-sub">可以查询你的课表、任务、财务、教室占用，也能基于知识库回答问题。试试：</div>
          <div class="w-cmds">
            <button v-for="c in ['我今天还有什么课？', '本周有哪些逾期任务？', '这个月学习投入花了多少？', '明天下午哪间教室空闲？']" :key="c" class="w-cmd" @click="input = c">{{ c }}</button>
          </div>
        </div>
        <div v-if="loadingHistory" class="w-sub" style="text-align:center; padding:40px">加载会话…</div>

        <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
          <div class="avatar">{{ m.role === 'user' ? '我' : '✦' }}</div>
          <div class="bubble">
            <div v-if="m.tools?.length" class="tool-trace">
              <div v-for="(t, j) in m.tools" :key="j" class="tt" :class="{ bad: !t.ok }">
                <span class="tt-name">⚡ {{ t.name }}</span>
                <span class="tt-args mono">{{ JSON.stringify(t.arguments || {}) }}</span>
              </div>
            </div>
            <div class="content" :class="{ typing: m.pending && !m.content }">
              <template v-if="m.pending && !m.content">思考中…</template>
              <template v-else>{{ m.content }}<span v-if="m.pending" class="caret" /></template>
            </div>
            <div v-if="m.error" class="m-err mono">⚠ {{ m.error }}</div>
          </div>
        </div>
      </div>

      <footer class="input-bar">
        <textarea v-model="input" class="ipt" rows="1" placeholder="输入问题，Enter 发送 / Shift+Enter 换行" @keydown="onKeydown" />
        <NButton v-if="streaming" size="small" tertiary type="error" @click="stopStream">停止</NButton>
        <NButton v-else size="small" type="primary" :disabled="!input.trim()" @click="send">发送</NButton>
      </footer>
    </section>

    <!-- 工具清单抽屉 -->
    <div v-if="showTools" class="drawer-mask" @click.self="showTools = false">
      <aside class="drawer">
        <header><div class="card-title">可用工具 <span class="en">TOOLS</span></div><button class="s-del" @click="showTools = false">×</button></header>
        <div v-for="t in tools" :key="t.name" class="tool-item">
          <div class="t-name mono">⚡ {{ t.name }}</div>
          <div class="t-desc">{{ t.description }}</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.ai-page { display: flex; gap: 16px; height: calc(100vh - 96px); min-height: 520px; }
.side { width: 216px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; }
.sess-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
.sess-empty { color: #6b7280; font-size: 12px; text-align: center; padding: 20px 0; }
.sess { padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; transition: all .15s; }
.sess:hover { border-color: #4ade8066; }
.sess.on { border-color: #4ade80; background: rgba(74, 222, 128, 0.06); }
.s-title { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s-meta { display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: #6b7280; margin-top: 3px; }
.s-del { background: none; border: none; color: #6b7280; cursor: pointer; font-size: 14px; line-height: 1; }
.s-del:hover { color: #f87171; }
.side-foot { display: flex; flex-direction: column; gap: 8px; }
.tool-link { background: none; border: none; color: #60a5fa; font-size: 12px; cursor: pointer; text-align: left; padding: 0; }
.mode-chip { font-size: 10px; text-align: center; padding: 3px 8px; border-radius: 999px; border: 1px solid #facc1566; color: #facc15; }
.mode-chip.live { border-color: #4ade8066; color: #4ade80; }

.chat { position: relative; flex: 1; display: flex; flex-direction: column; min-width: 0; background: var(--card); border: 1px solid transparent; border-radius: var(--radius); padding: 0; }
/* 荧光边缘：mask 裁出 1.5px 描边环，窄亮段 = 游动粒子，不染色面板内部 */
.chat::before {
  content: ''; position: absolute; inset: -1.5px; z-index: 5;
  border-radius: calc(var(--radius) + 2px);
  padding: 1.5px;
  background: conic-gradient(from var(--glow-angle, 0deg),
    transparent 0 7%, rgba(74, 222, 128, 0.95) 9% 10.5%,
    transparent 12.5% 26%, rgba(96, 165, 250, 0.9) 28% 29%,
    transparent 31% 47%, rgba(74, 222, 128, 0.85) 49% 50%,
    transparent 52% 68%, rgba(192, 132, 252, 0.9) 70% 71.5%,
    transparent 73.5% 88%, rgba(74, 222, 128, 0.9) 90% 91%,
    transparent 93% 100%);
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask-composite: exclude;
  animation: glowSpin 7s linear infinite;
  filter: blur(0.6px) brightness(1.2);
  pointer-events: none;
}
.chat::after {
  content: ''; position: absolute; inset: -8px; z-index: -2; border-radius: calc(var(--radius) + 10px);
  background: radial-gradient(120% 90% at 50% 0%, rgba(74, 222, 128, 0.14), transparent 60%),
              radial-gradient(120% 90% at 50% 100%, rgba(74, 222, 128, 0.1), transparent 60%);
  animation: glowBreath 3.2s ease-in-out infinite; pointer-events: none;
}
@property --glow-angle { syntax: '<angle>'; inherits: false; initial-value: 0deg; }
@keyframes glowSpin { to { --glow-angle: 360deg; } }
@keyframes glowBreath { 0%, 100% { opacity: .55; } 50% { opacity: 1; } }
.chat:focus-within::before { animation-duration: 2.4s; filter: blur(0px) brightness(1.35); }
.chat-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border); gap: 12px; border-radius: calc(var(--radius) - 1px) calc(var(--radius) - 1px) 0 0; }
.opts { display: flex; gap: 16px; }
.opt { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #9ca3af; }

.msg-list { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 16px; }
.welcome { text-align: center; margin: auto; max-width: 460px; }
.w-star { font-size: 34px; color: #4ade80; text-shadow: 0 0 18px #4ade8088; }
.w-title { font-size: 16px; margin-top: 8px; }
.w-sub { font-size: 12px; color: #6b7280; margin-top: 6px; line-height: 1.7; }
.w-cmds { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 14px; }
.w-cmd { background: rgba(107,114,128,.1); border: 1px solid var(--border); color: #9ca3af; border-radius: 999px; padding: 5px 12px; font-size: 12px; cursor: pointer; }
.w-cmd:hover { color: #4ade80; border-color: #4ade8066; }

.msg { display: flex; gap: 10px; }
.msg.user { flex-direction: row-reverse; }
.avatar { width: 30px; height: 30px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; background: rgba(74,222,128,.12); color: #4ade80; border: 1px solid #4ade8033; }
.msg.user .avatar { background: rgba(96,165,250,.12); color: #60a5fa; border-color: #60a5fa33; }
.bubble { max-width: 78%; display: flex; flex-direction: column; gap: 6px; }
.content { padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.75; white-space: pre-wrap; word-break: break-word; background: rgba(107,114,128,.1); border: 1px solid var(--border); }
.msg.user .content { background: rgba(96,165,250,.1); border-color: #60a5fa33; }
.content.typing { color: #6b7280; }
.caret { display: inline-block; width: 7px; height: 14px; background: #4ade80; margin-left: 2px; vertical-align: -2px; animation: blink 1s steps(1) infinite; }
@keyframes blink { 50% { opacity: 0; } }
.m-err { color: #f87171; font-size: 11px; }

.tool-trace { display: flex; flex-direction: column; gap: 4px; }
.tt { display: flex; gap: 8px; align-items: center; font-size: 11px; padding: 5px 10px; border-radius: 8px; background: rgba(74,222,128,.06); border: 1px dashed #4ade8044; }
.tt.bad { background: rgba(248,113,113,.06); border-color: #f8717144; }
.tt-name { color: #4ade80; flex-shrink: 0; }
.tt-args { color: #6b7280; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 320px; }

.input-bar { display: flex; gap: 10px; align-items: flex-end; padding: 14px 18px; border-top: 1px solid var(--border); }
.ipt { flex: 1; background: rgba(107,114,128,.08); border: 1px solid var(--border); border-radius: 10px; color: var(--text-1, #e5e7eb); font-size: 13px; padding: 9px 12px; resize: none; outline: none; font-family: inherit; line-height: 1.5; }
.ipt:focus { border-color: #4ade8066; }

.drawer-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 60; display: flex; justify-content: flex-end; }
.drawer { width: 380px; background: var(--card); border-left: 1px solid var(--border); padding: 18px; overflow-y: auto; }
.drawer header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.tool-item { padding: 10px 0; border-bottom: 1px dashed var(--border); }
.t-name { color: #4ade80; font-size: 12px; }
.t-desc { color: #9ca3af; font-size: 11px; margin-top: 4px; line-height: 1.6; }
</style>
