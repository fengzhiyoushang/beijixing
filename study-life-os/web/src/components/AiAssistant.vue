<script setup>
import { marked } from 'marked'
import { nextTick, ref } from 'vue'
import { aiApi, streamChat } from '../api'

const open = ref(false)
const sending = ref(false)
const input = ref('')
const sessionId = ref(null)
const messages = ref([]) // { role, content, tools?: [{name,args,result}] }
const listEl = ref(null)
let ctrl = null

const suggestions = [
  '今天我有哪些课？',
  '最近 3 天要交的 DDL 有哪些？',
  '帮我记一笔午饭支出 18 元',
  '我这周的学习打卡情况如何？',
  '预测一下现在哪个教室最空？',
]

const md = (text) => marked.parse(text || '')

function scrollBottom() {
  nextTick(() => listEl.value && (listEl.value.scrollTop = listEl.value.scrollHeight))
}

function send(text) {
  const content = (text ?? input.value).trim()
  if (!content || sending.value) return
  messages.value.push({ role: 'user', content })
  input.value = ''
  const asst = { role: 'assistant', content: '', tools: [] }
  messages.value.push(asst)
  sending.value = true
  scrollBottom()
  ctrl = streamChat({
    message: content,
    sessionId: sessionId.value,
    onEvent(type, data) {
      if (type === 'meta') sessionId.value = data.session_id
      else if (type === 'tool') asst.tools.push(data)
      else if (type === 'token') { asst.content += data.text; scrollBottom() }
      else if (type === 'error') asst.content += `\n❌ ${data.message}`
    },
    onFinally() { sending.value = false; scrollBottom() },
  })
}

function stop() { ctrl?.abort(); sending.value = false }

function newChat() {
  stop()
  messages.value = []
  sessionId.value = null
}

async function restoreSession() {
  try {
    const sessions = await aiApi.sessions()
    if (!sessions.length) return
    const data = await aiApi.messages(sessions[0].id)
    sessionId.value = sessions[0].id
    messages.value = data.messages
      .filter((m) => m.role === 'user' || (m.role === 'assistant' && m.content))
      .map((m) => ({ role: m.role, content: m.content, tools: [] }))
    open.value = true
    scrollBottom()
  } catch { /* 忽略 */ }
}
</script>

<template>
  <div class="ai-root">
    <!-- 对话面板 -->
    <transition name="panel">
      <div v-if="open" class="panel">
        <div class="head">
          <span class="mono title"><span class="dot-live" /> AI 终端助手 <span class="fn">fn:call</span></span>
          <n-space :size="4">
            <n-button quaternary size="tiny" @click="restoreSession">历史</n-button>
            <n-button quaternary size="tiny" @click="newChat">新会话</n-button>
            <n-button quaternary size="tiny" @click="open = false">✕</n-button>
          </n-space>
        </div>

        <div ref="listEl" class="list">
          <div v-if="!messages.length" class="welcome">
            <div class="big mono glow-text">✦ 小析</div>
            <div class="desc">我可以查询并操作你终端里的所有数据 —— 课表、DDL、打卡、教室、财务、考研、知识库、健康。</div>
            <div class="sugs">
              <span v-for="s in suggestions" :key="s" class="sug mono" @click="send(s)">{{ s }}</span>
            </div>
          </div>
          <template v-for="(m, i) in messages" :key="i">
            <div v-if="m.role === 'user'" class="row user">
              <div class="bubble user-b">{{ m.content }}</div>
            </div>
            <div v-else class="row">
              <div class="bubble asst-b">
                <div v-if="m.tools && m.tools.length" class="tools">
                  <div v-for="(t, ti) in m.tools" :key="ti" class="tool mono" :title="t.result">
                    ⚙ fn:{{ t.name }}({{ JSON.stringify(t.args || {}) }})
                  </div>
                </div>
                <div class="md-body" v-html="md(m.content)" />
                <span v-if="sending && i === messages.length - 1" class="cursor">▋</span>
              </div>
            </div>
          </template>
        </div>

        <div class="foot">
          <n-input
            v-model:value="input"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="问我任何关于你数据的问题，Enter 发送 / Shift+Enter 换行"
            @keydown.enter.exact.prevent="send()"
          />
          <div class="foot-btns">
            <n-button v-if="sending" size="small" quaternary type="error" @click="stop">停止</n-button>
            <n-button size="small" type="primary" :disabled="sending || !input.trim()" @click="send()">发送 ⏎</n-button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 常驻悬浮入口 -->
    <div class="fab-wrap">
      <button class="fab" :class="{ active: open }" @click="open = !open" title="AI 助手">
        <span class="fab-icon">✦</span>
        <span class="ring" />
      </button>
      <div v-if="!open" class="fab-tip mono">AI 助手</div>
    </div>
  </div>
</template>

<style scoped>
.ai-root { position: fixed; right: 22px; bottom: 22px; z-index: 999; }
.fab-wrap { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.fab {
  position: relative; width: 54px; height: 54px; border-radius: 50%; border: none; cursor: pointer;
  background: linear-gradient(135deg, #00e5a0, #0aa8d8);
  box-shadow: 0 0 22px rgba(0, 229, 160, 0.45), 0 6px 18px rgba(0, 0, 0, 0.5);
  transition: transform 0.15s;
}
.fab:hover { transform: scale(1.08); }
.fab.active { background: linear-gradient(135deg, #14322a, #10263a); }
.fab-icon { font-size: 24px; color: #04110c; }
.fab.active .fab-icon { color: #00e5a0; }
.ring { position: absolute; inset: -4px; border-radius: 50%; border: 1px solid rgba(0, 229, 160, 0.5); animation: pulse 2.4s infinite; }
@keyframes pulse { 0%, 100% { opacity: 0.2; transform: scale(1); } 50% { opacity: 0.8; transform: scale(1.08); } }
.fab-tip { font-size: 10px; color: #5b7290; margin-right: 8px; }

.panel {
  width: 400px; height: min(600px, 72vh); margin-bottom: 12px; display: flex; flex-direction: column;
  background: rgba(10, 17, 30, 0.97); border: 1px solid rgba(0, 229, 160, 0.3); border-radius: 14px;
  box-shadow: 0 0 40px rgba(0, 229, 160, 0.12), 0 20px 60px rgba(0, 0, 0, 0.6); backdrop-filter: blur(6px);
  overflow: hidden;
}
.head { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border-bottom: 1px solid rgba(56, 189, 248, 0.14); }
.title { color: #00e5a0; font-size: 13px; }
.fn { color: #38bdf8; font-size: 10px; opacity: 0.8; }
.dot-live { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #00e5a0; box-shadow: 0 0 8px #00e5a0; margin-right: 5px; }
.list { flex: 1; overflow-y: auto; padding: 12px; }
.welcome { text-align: center; padding: 24px 8px; }
.welcome .big { font-size: 30px; color: #00e5a0; }
.welcome .desc { color: #7d93b2; font-size: 12px; margin: 10px 0 14px; line-height: 1.6; }
.sugs { display: flex; flex-direction: column; gap: 7px; align-items: center; }
.sug { font-size: 11px; color: #9fd8c4; border: 1px dashed rgba(0, 229, 160, 0.4); padding: 5px 10px; border-radius: 14px; cursor: pointer; }
.sug:hover { background: rgba(0, 229, 160, 0.08); }
.row { display: flex; margin-bottom: 10px; }
.row.user { justify-content: flex-end; }
.bubble { max-width: 88%; padding: 8px 11px; border-radius: 10px; font-size: 13px; }
.user-b { background: linear-gradient(135deg, #0b6b4f, #0a5c7a); color: #eafff6; border-top-right-radius: 3px; }
.asst-b { background: rgba(19, 30, 50, 0.9); border: 1px solid rgba(56, 189, 248, 0.15); border-top-left-radius: 3px; }
.tools { margin-bottom: 6px; }
.tool { font-size: 10px; color: #fbbf24; background: rgba(251, 191, 36, 0.08); border: 1px solid rgba(251, 191, 36, 0.3); border-radius: 5px; padding: 2px 6px; margin-bottom: 3px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: help; }
.cursor { animation: blink 0.9s infinite; color: #00e5a0; }
@keyframes blink { 50% { opacity: 0; } }
.foot { padding: 10px 12px; border-top: 1px solid rgba(56, 189, 248, 0.14); }
.foot-btns { display: flex; justify-content: flex-end; margin-top: 8px; gap: 8px; }
.panel-enter-active, .panel-leave-active { transition: all 0.18s ease; }
.panel-enter-from, .panel-leave-to { opacity: 0; transform: translateY(12px) scale(0.97); }
</style>
