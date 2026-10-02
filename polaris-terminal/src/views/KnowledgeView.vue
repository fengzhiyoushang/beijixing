<script setup>
import { computed, onMounted, ref } from 'vue'
import { NButton, NDynamicTags, NForm, NFormItem, NInput, NModal, NPopconfirm, NSelect, useMessage } from 'naive-ui'
import { store } from '../store'
import GlowChart from '../components/GlowChart.vue'
import { axisBase, glowBar, glowLine } from '../utils/chart'

const message = useMessage()
const kb = store.knowledgeStats

/* ── 文件夹树 ── */
const selFolder = ref(null)          // null = 全部文档
const folderDocOptions = computed(() =>
  store.foldersRaw.map((f) => ({ label: `${f.icon || '▸'} ${f.name}`, value: f.id })))

async function selectFolder(id) {
  selFolder.value = id
  try { await store.loadDocsByFolder(id) }
  catch (err) { message.error('加载文档失败：' + err.message) }
}

const showFolderModal = ref(false)
const folderEditing = ref(null)
const folderForm = ref({ name: '', icon: '▸', parent_id: null })
const savingFolder = ref(false)
function newFolder() {
  folderEditing.value = null
  folderForm.value = { name: '', icon: '▸', parent_id: null }
  showFolderModal.value = true
}
function editFolder(f) {
  folderEditing.value = f
  folderForm.value = { name: f.name, icon: f.icon || '▸', parent_id: f.parent_id ?? null }
  showFolderModal.value = true
}
async function saveFolder() {
  if (!folderForm.value.name.trim()) { message.warning('文件夹名称必填'); return }
  savingFolder.value = true
  try {
    const payload = {
      name: folderForm.value.name.trim(),
      icon: folderForm.value.icon || '▸',
      parent_id: folderForm.value.parent_id ?? null,
    }
    if (folderEditing.value) await store.renameFolder(folderEditing.value.id, payload)
    else await store.createFolder(payload)
    message.success('文件夹已保存')
    showFolderModal.value = false
    await selectFolder(selFolder.value)
  } catch (err) {
    message.error('保存失败：' + err.message)
  } finally {
    savingFolder.value = false
  }
}
async function removeFolder(f) {
  try {
    const r = await store.removeFolder(f.id, false)
    message.success(`已删除「${f.name}」（${r.docs_affected ?? 0} 篇文档移至未分类）`)
    if (selFolder.value === f.id) await selectFolder(null)
    else await selectFolder(selFolder.value)
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* ── 文档上传（可选文件夹/标签）── */
const docInput = ref(null)
const uploading = ref(false)
const showUploadOpts = ref(false)
const uploadOpts = ref({ folderId: null, tags: [] })
function pickDoc() {
  uploadOpts.value = { folderId: selFolder.value, tags: [] }
  showUploadOpts.value = true
}
function confirmUpload() {
  showUploadOpts.value = false
  docInput.value?.click()
}
async function onDocFile(e) {
  const f = e.target.files?.[0]
  if (!f) return
  if (!/\.(md|markdown|txt|docx|xlsx)$/i.test(f.name)) {
    message.error('仅支持 md / txt / docx / xlsx')
    e.target.value = ''
    return
  }
  uploading.value = true
  try {
    const doc = await store.uploadKnowledgeDoc({
      file: f,
      folderId: uploadOpts.value.folderId,
      tags: uploadOpts.value.tags.length ? uploadOpts.value.tags.join(',') : null,
    })
    const vc = doc.vectorize
    message.success(`《${doc.title}》已入库${vc ? ` · 切片 ${vc.chunks ?? 0} 个` : ''}`)
    if (selFolder.value != null) await selectFolder(selFolder.value)
  } catch (err) {
    message.error('上传失败：' + err.message)
  } finally {
    uploading.value = false
    e.target.value = ''
  }
}

/* ── 文档新建 / 编辑 / 删除 ── */
const showDocModal = ref(false)
const docEditing = ref(null)   // null = 新建
const savingDoc = ref(false)
const df = ref({ title: '', content: '', folder_id: null, tags: [] })

function newDoc() {
  docEditing.value = null
  df.value = { title: '', content: '', folder_id: selFolder.value, tags: [] }
  showDocModal.value = true
}
async function editDoc(d) {
  try {
    const full = await store.loadDoc(d.id)
    docEditing.value = full
    df.value = {
      title: full.title, content: full.content || '',
      folder_id: full.folder_id ?? null, tags: full.tags || [],
    }
    showDocModal.value = true
  } catch (err) {
    message.error('加载文档失败：' + err.message)
  }
}
async function saveDoc() {
  if (!df.value.title.trim()) { message.warning('文档标题必填'); return }
  savingDoc.value = true
  try {
    const payload = {
      title: df.value.title.trim(), content: df.value.content,
      folder_id: df.value.folder_id ?? null, tags: df.value.tags || [],
      doc_type: 'markdown', auto_vectorize: true,
    }
    await store.saveDoc(payload, { id: docEditing.value?.id ?? null })
    message.success(docEditing.value ? `《${payload.title}》已更新并重建索引` : `《${payload.title}》已入库并向量化`)
    showDocModal.value = false
    if (selFolder.value != null) await selectFolder(selFolder.value)
  } catch (err) {
    message.error('保存失败：' + err.message)
  } finally {
    savingDoc.value = false
  }
}
async function removeDoc(d) {
  try {
    await store.removeDoc(d.id)
    message.success(`已删除《${d.title}》`)
    if (selFolder.value != null) await selectFolder(selFolder.value)
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* 点击标签 → 快速筛选（暂以关键词检索代替：填入标题搜索） */
const q = ref('')
const qa = ref([{ q: store.ragDemo.question, a: store.ragDemo.answer, refs: store.ragDemo.refs }])
const asking = ref(false)

const docs = computed(() => store.knowledgeDocs)
const folderName = (id) => store.foldersRaw.find((f) => f.id === id)?.name || '未分类'

/* 分类占比 */
const catOption = computed(() => {
  const map = {}
  docs.value.forEach((d) => (map[d.cat] = (map[d.cat] || 0) + d.words))
  const palette = ['#4ade80', '#60a5fa', '#c084fc', '#facc15', '#f87171', '#2dd4bf']
  return {
    tooltip: { trigger: 'item', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
    legend: { bottom: 0, textStyle: { color: '#9ca3af', fontSize: 10 }, itemWidth: 8, itemHeight: 8 },
    series: [
      {
        type: 'pie', radius: ['46%', '70%'], center: ['50%', '42%'],
        itemStyle: { borderColor: '#1e1e1e', borderWidth: 2 },
        label: { show: false },
        data: Object.entries(map).map(([name, value], i) => ({
          name, value, itemStyle: { color: palette[i % palette.length], shadowColor: palette[i % palette.length] + '88', shadowBlur: 10 },
        })),
      },
    ],
  }
})

/* 入库节奏 */
const trendOption = computed(() => ({
  grid: { left: 34, right: 12, top: 16, bottom: 24 },
  xAxis: { type: 'category', data: ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7'], ...axisBase(), splitLine: { show: false } },
  yAxis: { type: 'value', ...axisBase() },
  tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
  series: [
    { ...glowBar('#60a5fa'), data: kb.weekNewTrend, barWidth: '44%' },
    { ...glowLine(store.settings.accent), data: [1, 2, 2, 3, 3, 4, 5], name: '累计' },
  ],
}))

/** 真实 RAG 问答：后端检索知识库切片 + DeepSeek 生成，返回引用来源 */
async function ask() {
  const text = q.value.trim()
  if (!text) { message.warning('请输入问题'); return }
  asking.value = true
  try {
    const result = await store.knowledgeAsk(text)
    qa.value.unshift({
      q: text,
      a: result.answer,
      refs: (result.references || []).map((r) => `资料${r.index} 《${r.doc_title}》`),
      mode: result.mode,
    })
    q.value = ''
    message.success(`检索完成 · 模式 ${result.mode} · 引用 ${result.references?.length || 0} 篇`)
  } catch (err) {
    message.error(err.message)
  } finally {
    asking.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>知识整理</h2>
      <span class="sub mono">KNOWLEDGE · 多格式文档 + Markdown + RAG 问答</span>
      <span class="spacer" />
      <input ref="docInput" type="file" accept=".md,.markdown,.txt,.docx,.xlsx" style="display:none" @change="onDocFile" />
      <NButton size="small" quaternary @click="newDoc">✎ 新建文档</NButton>
      <NButton size="small" type="primary" :loading="uploading" @click="pickDoc">⬆ 上传文档</NButton>
    </div>

    <div class="grid" style="margin-bottom: 16px">
      <div class="col-3 stat-card">
        <div class="num-big">{{ kb.docCount }}</div>
        <div class="label-3">文档总数</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#60a5fa; text-shadow:0 0 14px #60a5fa66">{{ kb.mastery }}</div>
        <div class="label-3">平均索引覆盖率</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#facc15; text-shadow:0 0 14px #facc1566">+{{ kb.newThisWeek }}</div>
        <div class="label-3">本周新增</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#c084fc; text-shadow:0 0 14px #c084fc66">{{ (kb.wordTotal / 1000).toFixed(1) }}k</div>
        <div class="label-3">总字数</div>
      </div>
    </div>

    <div class="grid">
      <section class="col-8 card">
        <header class="card-head">
          <div class="card-title">≡ 文档库 <span class="en">DOCUMENTS</span></div>
          <div class="tags">
            <span v-for="t in kb.hotTags.slice(0, 4)" :key="t" class="tag-pill">{{ t }}</span>
          </div>
        </header>
        <div class="kb-layout">
          <!-- 文件夹树 -->
          <aside class="folder-tree">
            <div class="ft-head mono">
              <span>文件夹</span>
              <button class="ft-add" title="新建文件夹" @click="newFolder">＋</button>
            </div>
            <div class="ft-item" :class="{ on: selFolder === null }" @click="selectFolder(null)">
              <span class="ft-ico">📂</span><span class="ft-name">全部文档</span>
              <span class="ft-cnt mono">{{ docs.length }}</span>
            </div>
            <div v-for="f in store.foldersRaw" :key="f.id" class="ft-item"
                 :class="{ on: selFolder === f.id }" @click="selectFolder(f.id)">
              <span class="ft-ico">{{ f.icon || '▸' }}</span>
              <span class="ft-name">{{ f.name }}</span>
              <span class="ft-cnt mono">{{ f.doc_count ?? 0 }}</span>
              <span class="ft-ops">
                <button title="编辑" @click.stop="editFolder(f)">✎</button>
                <NPopconfirm @positive-click="removeFolder(f)">
                  <template #trigger><button title="删除" @click.stop>✕</button></template>
                  删除「{{ f.name }}」？其中文档将移至未分类。
                </NPopconfirm>
              </span>
            </div>
          </aside>

          <!-- 文档列表 -->
          <div class="doc-list">
            <div class="doc-head mono">
              <span style="flex:1.5">标题</span><span style="width:86px">文件夹</span>
              <span style="width:64px">字数</span><span style="width:120px">索引完成度</span>
              <span style="width:84px">更新</span><span style="width:96px">操作</span>
            </div>
            <div v-if="!docs.length" class="doc-empty">该文件夹下暂无文档</div>
            <div v-for="d in docs" :key="d.id" class="doc-row">
              <span style="flex:1.5" class="d-title" :title="d.tags.join(' / ')" @click="editDoc(d)">{{ d.title }}</span>
              <span style="width:86px; font-size:11px" class="c3">{{ folderName(d.folderId) }}</span>
              <span style="width:64px" class="mono c3">{{ d.words }}</span>
              <span style="width:120px" class="m-cell">
                <span class="m-track"><i class="m-fill" :style="{ width: d.mastery + '%', background: d.mastery > 85 ? '#4ade80' : d.mastery > 75 ? '#60a5fa' : '#facc15' }" /></span>
                <span class="mono c3">{{ d.mastery }}</span>
              </span>
              <span style="width:84px" class="mono c3">{{ d.updated }}</span>
              <span style="width:96px; display:flex; gap:4px; justify-content:flex-end">
                <NButton size="tiny" quaternary @click="editDoc(d)">编辑</NButton>
                <NPopconfirm @positive-click="removeDoc(d)">
                  <template #trigger><NButton size="tiny" quaternary type="error">删除</NButton></template>
                  删除《{{ d.title }}》？连带切片一并删除。
                </NPopconfirm>
              </span>
            </div>
          </div>
        </div>
      </section>

      <section class="col-4 card rag-card">
        <header class="card-head">
          <div class="card-title">✦ RAG 问答 <span class="en">ASK YOUR BASE</span></div>
          <span class="chip chip-accent">已索引 {{ kb.docCount }} 篇</span>
        </header>
        <div class="rag-body">
          <div v-for="(item, i) in qa" :key="i" class="qa">
            <div class="qa-q mono">ME ▸ {{ item.q }}</div>
            <div class="qa-a">
              <span class="qa-label mono">AI</span>
              <p>{{ item.a }}</p>
              <div class="refs">
                <span v-for="r in item.refs" :key="r" class="chip chip-blue">{{ r }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="rag-input">
          <NInput v-model:value="q" size="small" placeholder="基于知识库提问…" @keyup.enter="ask" />
          <NButton size="small" type="primary" :loading="asking" @click="ask">提问</NButton>
        </div>
        <div class="mini-note mono">原型：本地 mock 检索；接入后端后走 BM25 + DeepSeek 生成，并返回真实引用片段。</div>
      </section>

      <section class="col-4 card">
        <header class="card-head"><div class="card-title">◔ 分类字数占比 <span class="en">BY CATEGORY</span></div></header>
        <GlowChart :option="catOption" height="236px" />
      </section>

      <section class="col-8 card">
        <header class="card-head"><div class="card-title">◱ 本周入库节奏 <span class="en">INTAKE</span></div></header>
        <GlowChart :option="trendOption" height="236px" />
      </section>
    </div>

    <!-- 上传选项：选择目标文件夹 + 标签 -->
    <NModal v-model:show="showUploadOpts" preset="card" title="⬆ 上传文档" style="width: 420px" :bordered="false">
      <NForm label-placement="left" label-width="72" size="small">
        <NFormItem label="目标文件夹">
          <NSelect v-model:value="uploadOpts.folderId" :options="folderDocOptions" clearable placeholder="未分类" />
        </NFormItem>
        <NFormItem label="标签">
          <NDynamicTags v-model:value="uploadOpts.tags" size="small" />
        </NFormItem>
      </NForm>
      <div class="mini-note mono">支持 md / txt / docx / xlsx，上传后自动解析入库并向量化。</div>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:10px">
          <NButton size="small" @click="showUploadOpts = false">取消</NButton>
          <NButton size="small" type="primary" @click="confirmUpload">选择文件</NButton>
        </div>
      </template>
    </NModal>

    <!-- 文件夹新建/编辑 -->
    <NModal v-model:show="showFolderModal" preset="card" :title="folderEditing ? `✎ 编辑「${folderEditing.name}」` : '＋ 新建文件夹'"
            style="width: 420px" :bordered="false">
      <NForm label-placement="left" label-width="72" size="small">
        <NFormItem label="名称" required><NInput v-model:value="folderForm.name" placeholder="如 操作系统笔记" /></NFormItem>
        <NFormItem label="图标">
          <NInput v-model:value="folderForm.icon" placeholder="▸" style="width: 80px" maxlength="2" />
        </NFormItem>
        <NFormItem label="上级文件夹">
          <NSelect v-model:value="folderForm.parent_id" :options="folderDocOptions.filter((o) => o.value !== folderEditing?.id)"
                   clearable placeholder="根目录" />
        </NFormItem>
      </NForm>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:10px">
          <NButton size="small" @click="showFolderModal = false">取消</NButton>
          <NButton size="small" type="primary" :loading="savingFolder" @click="saveFolder">保存</NButton>
        </div>
      </template>
    </NModal>

    <!-- 文档新建/编辑 -->
    <NModal v-model:show="showDocModal" preset="card" :title="docEditing ? `✎ 编辑《${docEditing.title}》` : '✎ 新建文档'"
            style="width: 720px" :bordered="false">
      <NForm label-placement="top" size="small">
        <div class="df-bar">
          <NInput v-model:value="df.title" placeholder="文档标题" class="df-title" />
          <NSelect v-model:value="df.folder_id" :options="folderDocOptions" clearable placeholder="未分类" style="width: 170px" />
        </div>
        <NFormItem label="标签">
          <NDynamicTags v-model:value="df.tags" size="small" />
        </NFormItem>
        <NFormItem label="正文（Markdown）">
          <NInput v-model:value="df.content" type="textarea" placeholder="# 标题&#10;支持 Markdown 与纯文本，保存后自动切片向量化…"
                  :autosize="{ minRows: 12, maxRows: 20 }" style="font-family: var(--mono, monospace); font-size: 12px" />
        </NFormItem>
      </NForm>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:10px">
          <NButton size="small" @click="showDocModal = false">取消</NButton>
          <NButton size="small" type="primary" :loading="savingDoc" @click="saveDoc">保存并重建索引</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; min-width: 0; }
.stat-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: center; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 10px; }

.doc-head, .doc-row { display: flex; align-items: center; gap: 10px; padding: 8px 2px; font-size: 12.5px; }
.doc-head { color: var(--text-3); font-size: 10px; border-bottom: 1px solid var(--border); }
.doc-row { border-bottom: 1px dashed var(--border); }
.doc-row:last-child { border-bottom: none; }
.doc-row:hover { background: rgba(255, 255, 255, 0.02); }
.d-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c3 { color: var(--text-3); font-size: 11px; }
.m-cell { display: flex; align-items: center; gap: 6px; }
.m-track { flex: 1; height: 6px; border-radius: 3px; background: #262626; overflow: hidden; }
.m-fill { display: block; height: 100%; box-shadow: 0 0 8px currentColor; }

.rag-card { display: flex; flex-direction: column; }
.rag-body { flex: 1; overflow-y: auto; max-height: 320px; display: flex; flex-direction: column; gap: 12px; }
.qa-q { font-size: 11px; color: var(--blue); margin-bottom: 4px; }
.qa-a { background: rgba(74, 222, 128, 0.05); border: 1px solid rgba(74, 222, 128, 0.2); border-radius: 10px; padding: 8px 10px; }
.qa-label { font-size: 9px; color: var(--accent); letter-spacing: 1px; }
.qa-a p { margin: 4px 0 0; font-size: 12.5px; color: var(--text-1); line-height: 1.7; white-space: pre-wrap; }
.refs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.rag-input { display: flex; gap: 8px; margin-top: 12px; }
.mini-note { font-size: 10px; color: var(--text-3); margin-top: 8px; }
.tag-pill { font-size: 10px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-2); }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }

/* 文件夹树 + 文档列表 */
.kb-layout { display: flex; gap: 14px; min-height: 260px; }
.folder-tree { width: 190px; flex-shrink: 0; border-right: 1px solid var(--border); padding-right: 12px; }
.ft-head { display: flex; align-items: center; justify-content: space-between; font-size: 10px; color: var(--text-3); padding: 4px 2px 8px; }
.ft-add { all: unset; cursor: pointer; font-size: 13px; color: var(--text-3); padding: 0 6px; border-radius: 5px; }
.ft-add:hover { color: var(--accent); background: rgba(74,222,128,0.1); }
.ft-item { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 8px; cursor: pointer; font-size: 12px; color: var(--text-2); }
.ft-item:hover { background: rgba(255,255,255,0.03); }
.ft-item.on { background: rgba(74,222,128,0.08); color: var(--text-1); border: 1px solid rgba(74,222,128,0.3); }
.ft-ico { font-size: 11px; }
.ft-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ft-cnt { font-size: 10px; color: var(--text-3); }
.ft-ops { display: none; gap: 2px; }
.ft-item:hover .ft-ops { display: inline-flex; }
.ft-ops button { all: unset; cursor: pointer; font-size: 10px; color: var(--text-3); padding: 1px 4px; border-radius: 4px; }
.ft-ops button:hover { color: #f87171; background: rgba(248,113,113,0.12); }
.doc-list { flex: 1; min-width: 0; }
.doc-empty { padding: 32px 0; text-align: center; color: var(--text-3); font-size: 12px; border: 1px dashed var(--border); border-radius: 10px; }
.d-title { cursor: pointer; }
.d-title:hover { color: var(--accent); }

/* 文档表单 */
.df-bar { display: flex; gap: 10px; margin-bottom: 10px; }
.df-title { flex: 1; }
</style>
