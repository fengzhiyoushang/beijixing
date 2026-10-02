<script setup>
import { marked } from 'marked'
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { knowledgeApi } from '../api'
import { categoryAxis, mountChart, valueAxis } from '../utils/chart'

const message = useMessage()

const docs = ref([])
const cats = ref([])
const search = ref('')
const catFilter = ref(null)
const selId = ref(null)
const isNew = ref(false)
const editor = ref({ title: '', category: '', content: '' })
const tab = ref('edit')
const stats = ref(null)
const growthEl = ref(null)

const qa = ref({ question: '', running: false, history: [] }) // {q, a, references, mode}

async function loadDocs() {
  const d = await knowledgeApi.docs({ search: search.value || undefined, category: catFilter.value || undefined })
  docs.value = d.docs
  cats.value = d.categories
  if (!selId.value && docs.value.length) selectDoc(docs.value[0])
}
async function loadStats() {
  stats.value = await knowledgeApi.stats()
  requestAnimationFrame(() => {
    if (stats.value && growthEl.value) {
      mountChart(growthEl.value, {
        xAxis: categoryAxis(stats.value.growth30.map((g) => g.date.slice(5))),
        yAxis: valueAxis(),
        series: [{ type: 'bar', data: stats.value.growth30.map((g) => g.count), barWidth: '50%' }],
      })
    }
  })
}
onMounted(() => { loadDocs(); loadStats() })

async function selectDoc(d) {
  const full = await knowledgeApi.getDoc(d.id)
  selId.value = d.id
  isNew.value = false
  editor.value = { title: full.title, category: full.category || '', content: full.content || '' }
  tab.value = 'preview'
}

function newDoc() {
  selId.value = null
  isNew.value = true
  editor.value = { title: '新文档', category: '', content: '# 标题\n\n直接书写 Markdown，保存后自动进入 RAG 检索索引。' }
  tab.value = 'edit'
}

async function save() {
  if (isNew.value || !selId.value) {
    const created = await knowledgeApi.createDoc({ ...editor.value, tags: [] })
    selId.value = created.id
    isNew.value = false
    message.success(`已创建，切块 ${created.chunks} 段`)
  } else {
    await knowledgeApi.updateDoc(selId.value, editor.value)
    message.success('已保存并重建索引')
  }
  loadDocs(); loadStats()
}

async function removeSel() {
  if (!selId.value) return
  await knowledgeApi.deleteDoc(selId.value)
  selId.value = null
  editor.value = { title: '', category: '', content: '' }
  loadDocs(); loadStats()
}

function uploadRequest({ file, onFinish, onError }) {
  knowledgeApi.upload(file.file, catFilter.value)
    .then((d) => { message.success(`《${d.title}》入库，切块 ${d.chunks} 段`); loadDocs(); loadStats(); onFinish() })
    .catch((e) => { onError(); message.error('解析失败：' + (e.detail || e.message)) })
}

async function ask() {
  const q = qa.value.question.trim()
  if (!q || qa.value.running) return
  qa.value.running = true
  qa.value.history.unshift({ q, a: '', references: [], mode: '' })
  qa.value.question = ''
  try {
    const res = await knowledgeApi.qa(q)
    Object.assign(qa.value.history[0], res)
  } finally { qa.value.running = false }
}

const md = (s) => marked.parse(s || '')
</script>

<template>
  <div class="page">
    <n-grid :cols="5" :x-gap="12" responsive="screen" item-responsive>
      <!-- 文档列表 -->
      <n-gi span="0:5 1100:2">
        <n-card size="small" title="≡ 文档库">
          <template #header-extra>
            <n-space :size="6">
              <n-button size="tiny" @click="newDoc">＋ 新建</n-button>
              <n-upload :custom-request="uploadRequest" :show-file-list="false" accept=".md,.txt,.docx,.xlsx">
                <n-button size="tiny" type="primary">⬆ 上传</n-button>
              </n-upload>
            </n-space>
          </template>
          <n-space :size="8" style="margin-bottom: 8px">
            <n-input v-model:value="search" size="tiny" placeholder="搜索标题/内容" clearable style="width: 140px" @keyup.enter="loadDocs" @clear="loadDocs" />
            <n-select v-model:value="catFilter" size="tiny" clearable style="width: 110px" placeholder="分类"
              :options="cats.map((c) => ({ label: c.category, value: c.category }))" @update:value="loadDocs" />
          </n-space>
          <div class="doc-list">
            <div v-for="d in docs" :key="d.id" class="doc" :class="{ active: d.id === selId }" @click="selectDoc(d)">
              <div class="dt">
                <span class="d-title">{{ d.title }}</span>
                <n-tag size="tiny" :bordered="false">{{ d.file_type }}</n-tag>
              </div>
              <div class="d-meta mono">{{ d.category || '未分类' }} · {{ d.word_count }}字 · 引用{{ d.read_count }}</div>
            </div>
            <div v-if="!docs.length" class="empty mono">// 暂无文档：新建 Markdown 或上传 .md/.txt/.docx/.xlsx</div>
          </div>
        </n-card>
      </n-gi>

      <!-- 工作区 -->
      <n-gi span="0:5 1100:3">
        <n-card size="small">
          <n-tabs v-model:value="tab" type="line" size="small">
            <n-tab-pane name="edit" tab="✎ Markdown 编辑">
              <n-space :size="8" style="margin-bottom: 8px">
                <n-input v-model:value="editor.title" size="small" placeholder="标题" style="width: 260px" />
                <n-input v-model:value="editor.category" size="small" placeholder="分类" style="width: 120px" />
                <n-button size="small" type="primary" @click="save">保存（重建索引）</n-button>
                <n-popconfirm v-if="selId && !isNew" @positive-click="removeSel">
                  <template #trigger><n-button size="small" type="error" quaternary>删除</n-button></template>
                  删除该文档及其索引？
                </n-popconfirm>
              </n-space>
              <n-input v-model:value="editor.content" type="textarea" class="mono" :rows="18" placeholder="在此书写 Markdown …" />
            </n-tab-pane>

            <n-tab-pane name="preview" tab="◫ 预览">
              <div class="md-body" style="padding: 4px 2px; max-height: 520px; overflow: auto" v-html="md(editor.content)" />
            </n-tab-pane>

            <n-tab-pane name="qa" tab="✦ RAG 问答">
              <n-input-group>
                <n-input v-model:value="qa.question" placeholder="基于你的知识库提问，如：中值定理口诀是什么？" @keyup.enter="ask" />
                <n-button type="primary" :loading="qa.running" @click="ask">提问</n-button>
              </n-input-group>
              <div v-for="(item, i) in qa.history" :key="i" class="qa-item">
                <div class="qa-q">🧠 {{ item.q }}</div>
                <div class="qa-a md-body" v-html="md(item.a || '检索中…')" />
                <div v-if="item.references?.length" class="refs">
                  <n-tag v-for="(r, ri) in item.references" :key="ri" size="tiny" :bordered="false" type="info" class="ref" :title="r.snippet">
                    资料{{ ri + 1 }}·{{ r.doc_title }}
                  </n-tag>
                  <n-tag size="tiny" :bordered="false" :type="item.mode === 'deepseek' ? 'success' : 'warning'">{{ item.mode }}</n-tag>
                </div>
              </div>
            </n-tab-pane>

            <n-tab-pane name="stats" tab="▤ 量化评估">
              <div v-if="stats" class="stat-grid">
                <div class="sg"><span class="k mono">文档数</span><span class="stat-num" style="font-size:20px">{{ stats.doc_count }}</span></div>
                <div class="sg"><span class="k mono">总字数</span><span class="stat-num" style="font-size:20px">{{ stats.total_words }}</span></div>
                <div class="sg"><span class="k mono">检索块</span><span class="stat-num" style="font-size:20px">{{ stats.chunk_count }}</span></div>
                <div class="sg"><span class="k mono">索引覆盖</span><span class="stat-num" style="font-size:20px">{{ Math.round(stats.coverage * 100) }}%</span></div>
                <div class="sg"><span class="k mono">累计引用</span><span class="stat-num" style="font-size:20px">{{ stats.qa_references_total }}</span></div>
              </div>
              <div class="section-title">近 30 天入库节奏</div>
              <div ref="growthEl" class="chart" />
              <div class="section-title">高频被引用文档</div>
              <div v-for="t in (stats?.top_referenced || [])" :key="t.title" class="top-row mono">
                <span>{{ t.title }}</span><span class="cnt">✦ {{ t.read_count }}</span>
              </div>
            </n-tab-pane>
          </n-tabs>
        </n-card>
      </n-gi>
    </n-grid>
  </div>
</template>

<style scoped>
.doc-list { max-height: 460px; overflow-y: auto; }
.doc { padding: 8px 10px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; }
.doc:hover { background: rgba(56,189,248,0.06); }
.doc.active { background: rgba(0,229,160,0.08); border-color: rgba(0,229,160,0.3); }
.dt { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.d-title { font-size: 13px; color: #dce8f7; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.d-meta { font-size: 10px; color: #5b7290; margin-top: 3px; }
.empty { color: #4a617f; font-size: 12px; padding: 14px 4px; }
.qa-item { margin-top: 12px; padding: 10px; background: rgba(13,21,36,0.8); border: 1px solid rgba(56,189,248,0.12); border-radius: 10px; }
.qa-q { color: #86efd4; font-size: 13px; margin-bottom: 6px; }
.refs { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
.ref { cursor: help; }
.stat-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 6px 0 14px; }
.sg { display: flex; flex-direction: column; gap: 4px; }
.sg .k { font-size: 10px; color: #5b7290; }
.top-row { display: flex; justify-content: space-between; font-size: 11px; color: #9fb8ce; padding: 4px 2px; border-bottom: 1px dashed rgba(56,189,248,0.1); }
.top-row .cnt { color: #fbbf24; }
</style>
