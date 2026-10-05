<script setup>
/**
 * 大模型 API 配置窗口：自主配置 OpenAI 兼容供应商（DeepSeek / Kimi / 通义 / Ollama…）。
 * 数据全部来自后端真实接口：GET/PUT /ai/config、POST /ai/config/test、GET /ai/usage。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NInput, NModal, NPopconfirm, NStatistic, NTag, useMessage } from 'naive-ui'
import { aiApi } from '../api'
import { store } from '../store'

const props = defineProps({ show: Boolean })
const emit = defineEmits(['update:show'])

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)

const presets = [
  { label: 'DeepSeek', base_url: 'https://api.deepseek.com', model: 'deepseek-chat', vl_model: 'deepseek-vl' },
  { label: 'Kimi', base_url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k', vl_model: '' },
  { label: '通义千问', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', vl_model: 'qwen-vl-plus' },
  { label: 'Ollama 本地', base_url: 'http://127.0.0.1:11434/v1', model: 'qwen2.5:7b', vl_model: '' },
]

const form = ref({ base_url: '', api_key: '', model: '', vl_model: '', timeout: '60', quota: '0' })
const status = ref(null)
const savedCfg = ref(null)
const usage = ref(null)

const hasKey = computed(() => !!status.value?.configured)
const modeText = computed(() => (status.value?.mode === 'live' ? '实时调用' : '演示模式'))

async function load() {
  loading.value = true
  try {
    const [cfg, u] = await Promise.all([aiApi.llmConfig(), aiApi.usage()])
    form.value = {
      base_url: cfg.config?.base_url || '',
      api_key: '',
      model: cfg.config?.model || '',
      vl_model: cfg.config?.vl_model || '',
      timeout: String(cfg.config?.timeout || 60),
      quota: String(cfg.config?.quota || 0),
    }
    status.value = cfg.status
    savedCfg.value = cfg.config
    usage.value = u
    testResult.value = null
  } catch (err) {
    message.error(`加载配置失败：${err.message}`)
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (v) => { if (v) load() })
onMounted(() => { if (props.show) load() })

function applyPreset(p) {
  form.value.base_url = p.base_url
  form.value.model = p.model
  form.value.vl_model = p.vl_model
}

async function save() {
  saving.value = true
  try {
    const payload = {
      base_url: form.value.base_url.trim(),
      model: form.value.model.trim(),
      vl_model: form.value.vl_model.trim(),
      timeout: Number(form.value.timeout) || 60,
      quota: Number(form.value.quota) || 0,
    }
    // Key 留空 = 保持原值不修改
    if (form.value.api_key.trim()) payload.api_key = form.value.api_key.trim()
    await aiApi.saveLlmConfig(payload)
    message.success('模型配置已保存')
    await load()
    await store.loadTokenUsage()
  } catch (err) {
    message.error(`保存失败：${err.message}`)
  } finally {
    saving.value = false
  }
}

async function clearKey() {
  try {
    // 传 null 显式删除该项（空串在后端视为"不修改"）
    await aiApi.saveLlmConfig({ api_key: null })
    message.success('API Key 已清除（回退全局配置）')
    await load()
  } catch (err) {
    message.error(`清除失败：${err.message}`)
  }
}

async function test() {
  testing.value = true
  testResult.value = null
  try {
    const r = await aiApi.testLlmConfig({
      base_url: form.value.base_url.trim() || undefined,
      api_key: form.value.api_key.trim() || undefined,
      model: form.value.model.trim() || undefined,
      timeout: Number(form.value.timeout) || undefined,
    })
    testResult.value = r
    if (r.ok) {
      message.success(`连接成功 · ${r.model || ''}`)
      await store.loadTokenUsage()
      usage.value = store.tokenSummary
    } else {
      message.warning(`连接失败：${r.message}`)
    }
  } catch (err) {
    testResult.value = { ok: false, message: err.message }
    message.error(`测试请求失败：${err.message}`)
  } finally {
    testing.value = false
  }
}

const fmt = (n) => (n ?? 0).toLocaleString('en-US')
const remainingText = computed(() => {
  const u = usage.value
  if (!u) return '—'
  if (u.remaining === null || u.remaining === undefined) return '未设预算'
  return fmt(u.remaining)
})

function close() { emit('update:show', false) }
</script>

<template>
  <NModal :show="props.show" preset="card" title="⚙ 大模型 API 配置" style="width: 640px; max-width: 94vw"
          :bordered="false" :mask-closable="true" @update:show="close">
    <div v-if="loading" class="loading mono">加载中…</div>
    <div v-else class="body">
      <!-- 当前状态 -->
      <div class="status-row">
        <NTag :type="hasKey ? 'success' : 'warning'" size="small" round>
          {{ modeText }}{{ status?.custom ? ' · 自定义' : ' · 全局默认' }}
        </NTag>
        <span class="mono cur">{{ status?.base_url }} / {{ status?.model }}</span>
      </div>

      <!-- 供应商预设 -->
      <div class="field">
        <label class="lb">快速预设（OpenAI 兼容）</label>
        <div class="presets">
          <button v-for="p in presets" :key="p.label" class="p-chip" @click="applyPreset(p)">{{ p.label }}</button>
        </div>
      </div>

      <div class="field">
        <label class="lb">Base URL</label>
        <NInput v-model:value="form.base_url" placeholder="留空回退全局 .env 配置，如 https://api.deepseek.com" />
      </div>

      <div class="field">
        <label class="lb">API Key <span v-if="savedCfg?.has_key" class="mono saved">已保存 {{ savedCfg?.api_key_masked }}</span></label>
        <NInput v-model:value="form.api_key" type="password" show-password-on="click"
                placeholder="留空 = 不修改已保存的 Key" />
        <div v-if="savedCfg?.has_key" class="hint-row">
          <NPopconfirm @positive-click="clearKey">
            <template #trigger><button class="link-btn">清除已保存的 Key</button></template>
            清除后将回退全局配置（若全局也无 Key 则进入演示模式），确定？
          </NPopconfirm>
        </div>
      </div>

      <div class="two">
        <div class="field">
          <label class="lb">对话模型</label>
          <NInput v-model:value="form.model" placeholder="如 deepseek-chat / moonshot-v1-8k" />
        </div>
        <div class="field">
          <label class="lb">视觉模型（教室识图）</label>
          <NInput v-model:value="form.vl_model" placeholder="如 deepseek-vl / qwen-vl-plus" />
        </div>
      </div>

      <div class="two">
        <div class="field">
          <label class="lb">超时（秒）</label>
          <NInput v-model:value="form.timeout" placeholder="60" />
        </div>
        <div class="field">
          <label class="lb">Token 预算（0 = 不限）</label>
          <NInput v-model:value="form.quota" placeholder="如 1000000" />
        </div>
      </div>

      <!-- 真实用量（后端台账统计，非估算展示） -->
      <div class="usage">
        <div class="u-title mono">TOKEN 真实用量（provider 回传 usage 落库）</div>
        <div class="u-grid">
          <NStatistic label="累计消耗" :value="fmt(usage?.total_tokens)" />
          <NStatistic label="今日" :value="fmt(usage?.today_tokens)" />
          <NStatistic label="近 7 天" :value="fmt(usage?.week_tokens)" />
          <NStatistic label="剩余" :value="remainingText" />
        </div>
        <div v-if="usage?.by_model?.length" class="u-models">
          <span v-for="m in usage.by_model" :key="m.model" class="m-item mono">
            {{ m.model }}：{{ fmt(m.tokens) }} tok / {{ m.calls }} 次
          </span>
        </div>
        <div v-if="usage?.estimated_rows" class="u-est mono">
          注：{{ usage.estimated_rows }} 条记录为 provider 未回传 usage 时的字符估算值
        </div>
      </div>
    </div>

    <template #footer>
      <div class="footer">
        <div v-if="testResult" class="test-res" :class="testResult.ok ? 'ok' : 'fail'">
          {{ testResult.ok ? `✓ ${testResult.message} · ${testResult.model || ''}` : `✕ ${testResult.message}` }}
        </div>
        <div class="btns">
          <NButton quaternary @click="close">关闭</NButton>
          <NButton :loading="testing" @click="test">测试连接</NButton>
          <NButton type="primary" :loading="saving" @click="save">保存配置</NButton>
        </div>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.loading { padding: 30px 0; text-align: center; color: var(--text-3); }
.body { display: flex; flex-direction: column; gap: 13px; }
.status-row { display: flex; align-items: center; gap: 10px; }
.cur { font-size: 11.5px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.field { display: flex; flex-direction: column; gap: 5px; }
.lb { font-size: 12px; color: var(--text-2); }
.saved { color: var(--accent); font-size: 11px; margin-left: 6px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.presets { display: flex; flex-wrap: wrap; gap: 6px; }
.p-chip {
  font-size: 11.5px; padding: 3px 12px; border-radius: 999px; cursor: pointer;
  background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); color: var(--text-2);
  transition: all 0.15s ease;
}
.p-chip:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.45); }
.hint-row { font-size: 11px; }
.link-btn { background: none; border: none; color: var(--text-3); font-size: 11.5px; cursor: pointer; padding: 0; text-decoration: underline; }
.link-btn:hover { color: #f87171; }
.usage { border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; background: rgba(255, 255, 255, 0.02); }
.u-title { font-size: 11px; color: var(--text-3); letter-spacing: 0.5px; margin-bottom: 10px; }
.u-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.u-grid :deep(.n-statistic .n-statistic-value) { font-size: 18px; }
.u-grid :deep(.n-statistic .n-statistic__label) { font-size: 11px; color: var(--text-3); }
.u-models { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
.m-item { font-size: 11px; color: var(--text-2); }
.u-est { font-size: 10.5px; color: var(--text-3); margin-top: 8px; }
.footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.test-res { font-size: 11.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 46%; }
.test-res.ok { color: var(--accent); }
.test-res.fail { color: #f87171; }
.btns { display: flex; gap: 8px; margin-left: auto; }
</style>
