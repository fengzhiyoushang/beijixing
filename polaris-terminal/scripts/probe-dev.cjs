const http = require('http')

const paths = [
  '/',
  '/src/main.js',
  '/src/App.vue',
  '/src/components/AppLayout.vue',
  '/src/components/SideNav.vue',
  '/src/components/TopBar.vue',
  '/src/components/GlowChart.vue',
  '/src/components/StatusDot.vue',
  '/src/components/AiAssistant.vue',
  '/src/store/index.js',
  '/src/mock/data.js',
  '/src/theme/polaris.js',
  '/src/router/index.js',
  '/src/utils/chart.js',
  '/src/utils/format.js',
  '/src/views/DashboardView.vue',
  '/src/views/CoursesView.vue',
  '/src/views/NotesView.vue',
  '/src/views/ClassroomView.vue',
  '/src/views/KaoyanView.vue',
  '/src/views/KnowledgeView.vue',
  '/src/views/FinanceView.vue',
  '/src/views/HealthView.vue',
  '/src/views/SettingsView.vue',
]

function probe(path) {
  return new Promise((res) => {
    http
      .get({ host: '127.0.0.1', port: 5200, path }, (r) => {
        let b = ''
        r.on('data', (c) => (b += c))
        r.on('end', () => res({ path, status: r.statusCode, body: b }))
      })
      .on('error', (e) => res({ path, status: 0, err: e.message }))
  })
}

;(async () => {
  let bad = 0
  for (const p of paths) {
    const r = await probe(p)
    const ok = r.status === 200
    if (!ok) bad++
    console.log(`${ok ? 'OK  ' : 'FAIL'} ${String(r.status).padEnd(4)} ${p}${r.status === 200 ? '' : ' :: ' + String(r.body || r.err).slice(0, 300)}`)
  }
  console.log(bad === 0 ? 'ALL_MODULES_OK' : `FAILED=${bad}`)
})()
