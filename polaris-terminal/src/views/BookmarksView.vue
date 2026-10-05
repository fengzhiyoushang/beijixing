<script setup>
import { computed, onMounted, ref } from 'vue'
import { NButton, NForm, NInput, NModal, NPopconfirm, NSelect, useMessage } from 'naive-ui'
import { store } from '../store'
import { openExternal, normalizeExternalUrl } from '../utils/openExternal'

const message = useMessage()

async function openBookmark(b) {
  if (!normalizeExternalUrl(b.url)) { message.error('该地址链接无效，请编辑后重试'); return }
  openExternal(b.url)
  await store.clickBookmark(b.id)
  b.click_count = (b.click_count || 0) + 1
}

/* ── 筛选 ── */
const filterCat = ref('全部')
const keyword = ref('')
const catOptions = computed(() => [
  { label: '全部', value: '全部' },
  ...store.bookmarks.categories.map((c) => ({ label: c, value: c })),
])
const filtered = computed(() => {
  let list = store.bookmarks.items
  if (filterCat.value !== '全部') list = list.filter((b) => b.category === filterCat.value)
  const k = keyword.value.trim().toLowerCase()
  if (k) list = list.filter((b) => (b.title + b.note + b.url).toLowerCase().includes(k))
  return list
})
const grouped = computed(() => {
  const map = {}
  filtered.value.forEach((b) => {
    (map[b.category] = map[b.category] || []).push(b)
  })
  return Object.entries(map).map(([cat, items]) => ({ cat, items }))
})

/* ── 编辑弹窗 ── */
const showEdit = ref(false)
const editing = ref(null)          // null=新增
const saving = ref(false)
const form = ref({ title: '', url: '', category: '常用', note: '', icon: '🔗', color: '#4ade80' })
const catPresets = ['常用', '学习', '考研', '就业', '工具', '开发', '生活', '资讯'].map((c) => ({ label: c, value: c }))
const iconPresets = ['🔗', '📚', '', '💼', '🛠', '💻', '🏠', '📰', '🎯', '', '', '⭐']
const colorPresets = ['#4ade80', '#60a5fa', '#c084fc', '#facc15', '#f87171', '#2dd4bf', '#fb923c']

function openAdd() {
  editing.value = null
  form.value = { title: '', url: '', category: filterCat.value !== '全部' ? filterCat.value : '常用', note: '', icon: '🔗', color: '#4ade80' }
  showEdit.value = true
}
function openEdit(b) {
  editing.value = b
  form.value = { title: b.title, url: b.url, category: b.category, note: b.note, icon: b.icon, color: b.color }
  showEdit.value = true
}
async function save() {
  if (!form.value.title.trim()) { message.warning('请填写名称'); return }
  const norm = normalizeExternalUrl(form.value.url)
  if (!norm) { message.warning('请填写有效的网址（如 https://…）'); return }
  saving.value = true
  try {
    const payload = { ...form.value, title: form.value.title.trim(), url: norm }
    if (editing.value) {
      await store.updateBookmark(editing.value.id, payload)
      message.success('已更新')
    } else {
      await store.createBookmark(payload)
      message.success('已添加，点击卡片即可在 Edge 中打开')
    }
    showEdit.value = false
  } catch (err) {
    message.error(err.message)
  } finally {
    saving.value = false
  }
}
async function remove(b) {
  try {
    await store.removeBookmark(b.id)
    message.success('已删除')
  } catch (err) { message.error(err.message) }
}

function domain(url) {
  try { return new URL(url).hostname } catch { return url }
}

onMounted(() => store.loadBookmarks())
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h2 class="title">🌐 地址中心 <span class="en">BOOKMARKS</span></h2>
      </div>
      <NButton type="primary" @click="openAdd">＋ 添加地址</NButton>
    </header>

    <div class="toolbar">
      <div class="cats">
        <button v-for="c in catOptions" :key="c.value" class="cat" :class="{ on: filterCat === c.value }" @click="filterCat = c.value">{{ c.label }}</button>
      </div>
      <NInput v-model:value="keyword" size="small" placeholder="搜索名称 / 备注 / 域名…" clearable style="width:220px" />
    </div>

    <div v-if="store.bookmarks.loading" class="empty">加载中…</div>
    <div v-else-if="!filtered.length" class="empty">
      <div class="e-ico"></div>
      <div>{{ keyword ? '没有匹配的地址' : '还没有收藏任何地址' }}</div>
      <NButton v-if="!keyword" size="small" type="primary" ghost style="margin-top:12px" @click="openAdd">添加第一个常用地址</NButton>
    </div>

    <section v-for="g in grouped" :key="g.cat" class="group">
      <div class="g-title"><span class="g-dot" />{{ g.cat }}<span class="g-count mono">{{ g.items.length }}</span></div>
      <div class="grid">
        <div v-for="b in g.items" :key="b.id" class="card" :style="{ '--bc': b.color || '#4ade80' }" @click="openBookmark(b)">
          <div class="c-top">
            <span class="c-icon">{{ b.icon || '🔗' }}</span>
            <div class="c-meta">
              <div class="c-name">{{ b.title }}</div>
              <div class="c-domain mono">{{ domain(b.url) }}</div>
            </div>
            <div class="c-ops" @click.stop>
              <button class="op" title="编辑" @click="openEdit(b)">✎</button>
              <NPopconfirm @positive-click="remove(b)">
                <template #trigger><button class="op del" title="删除">×</button></template>
                删除「{{ b.title }}」？
              </NPopconfirm>
            </div>
          </div>
          <div v-if="b.note" class="c-note">{{ b.note }}</div>
          <div class="c-foot mono">
            <span class="c-cat">{{ b.category }}</span>
            <span>打开 {{ b.click_count || 0 }} 次 ↗</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 编辑弹窗 -->
    <NModal v-model:show="showEdit" preset="card" :title="editing ? '编辑地址' : '添加常用地址'" style="width:480px" :bordered="false">
      <NForm label-placement="top" size="small">
        <div class="two">
          <NFormItem label="名称">
            <NInput v-model:value="form.title" placeholder="例如：中国研究生招生信息网" maxlength="120" />
          </NFormItem>
          <NFormItem label="分组">
            <NSelect v-model:value="form.category" :options="catOptions.slice(1)" tag filterable placeholder="选择或输入分组" />
          </NFormItem>
        </div>
        <NFormItem label="网址">
          <NInput v-model:value="form.url" placeholder="https://…（缺省协议自动补 https://）" maxlength="500" />
        </NFormItem>
        <NFormItem label="备注">
          <NInput v-model:value="form.note" type="textarea" :rows="2" placeholder="用途说明，如：考研报名 / 查课表 / 报销入口" maxlength="255" />
        </NFormItem>
        <div class="two">
          <NFormItem label="图标">
            <div class="pick-row">
              <button v-for="i in iconPresets" :key="i" class="pick" :class="{ on: form.icon === i }" @click="form.icon = i">{{ i }}</button>
            </div>
          </NFormItem>
          <NFormItem label="主色">
            <div class="pick-row">
              <button v-for="c in colorPresets" :key="c" class="pick color" :class="{ on: form.color === c }" :style="{ background: c }" @click="form.color = c" />
            </div>
          </NFormItem>
        </div>
      </NForm>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="showEdit = false">取消</NButton>
          <NButton type="primary" :loading="saving" @click="save">{{ editing ? '保存修改' : '添加' }}</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.page { padding: 20px 24px 40px; }
.head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.title { margin: 0; font-size: 20px; letter-spacing: .5px; }
.en { font-size: 11px; color: var(--text-3); letter-spacing: 2px; margin-left: 6px; }
.desc { margin: 6px 0 0; font-size: 12.5px; color: var(--text-3); }

.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 18px 0 6px; flex-wrap: wrap; }
.cats { display: flex; gap: 6px; flex-wrap: wrap; }
.cat { font-size: 12px; padding: 4px 13px; border-radius: 999px; cursor: pointer; background: rgba(255,255,255,.02); border: 1px solid var(--border); color: var(--text-2); transition: all .15s; }
.cat:hover { color: var(--accent); border-color: rgba(74,222,128,.4); }
.cat.on { color: var(--accent); border-color: rgba(74,222,128,.5); background: rgba(74,222,128,.12); }

.empty { text-align: center; color: var(--text-3); font-size: 13px; padding: 70px 0; }
.e-ico { font-size: 34px; margin-bottom: 10px; opacity: .7; }

.group { margin-top: 22px; }
.g-title { display: flex; align-items: center; gap: 8px; font-size: 13.5px; font-weight: 650; color: var(--text-1); margin-bottom: 10px; }
.g-dot { width: 8px; height: 8px; border-radius: 3px; background: var(--accent); box-shadow: 0 0 10px var(--accent); }
.g-count { font-size: 10.5px; color: var(--text-3); background: rgba(255,255,255,.04); border: 1px solid var(--border); border-radius: 999px; padding: 1px 8px; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(258px, 1fr)); gap: 12px; }
.card {
  position: relative; cursor: pointer; border-radius: 14px; padding: 13px 14px 10px;
  background: linear-gradient(160deg, rgba(255,255,255,.035), rgba(255,255,255,.012));
  border: 1px solid var(--border); transition: all .18s ease; overflow: hidden;
}
.card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--bc); box-shadow: 0 0 12px var(--bc); opacity: .85; }
.card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--bc) 55%, transparent); box-shadow: 0 8px 26px rgba(0,0,0,.4), 0 0 18px color-mix(in srgb, var(--bc) 18%, transparent); }
.c-top { display: flex; align-items: center; gap: 10px; }
.c-icon { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; font-size: 18px; background: color-mix(in srgb, var(--bc) 12%, transparent); border: 1px solid color-mix(in srgb, var(--bc) 35%, transparent); flex-shrink: 0; }
.c-meta { min-width: 0; flex: 1; }
.c-name { font-size: 13.5px; font-weight: 600; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-domain { font-size: 10.5px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-ops { display: flex; gap: 4px; opacity: 0; transition: opacity .15s; }
.card:hover .c-ops { opacity: 1; }
.op { width: 22px; height: 22px; border-radius: 6px; border: 1px solid var(--border); background: transparent; color: var(--text-2); cursor: pointer; font-size: 11px; }
.op:hover { color: var(--accent); border-color: rgba(74,222,128,.4); }
.op.del:hover { color: #f87171; border-color: rgba(248,113,113,.4); }
.c-note { margin-top: 9px; font-size: 11.5px; color: var(--text-2); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.c-foot { display: flex; justify-content: space-between; margin-top: 10px; font-size: 10px; color: var(--text-3); }
.c-cat { color: var(--bc); }

.two { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }
.pick-row { display: flex; flex-wrap: wrap; gap: 6px; }
.pick { width: 28px; height: 28px; border-radius: 8px; border: 1px solid var(--border); background: rgba(255,255,255,.03); cursor: pointer; font-size: 14px; display: grid; place-items: center; }
.pick.on { border-color: var(--accent); box-shadow: 0 0 10px rgba(74,222,128,.35); }
.pick.color { font-size: 0; }
.pick.color.on { outline: 2px solid var(--text-1); }
</style>
