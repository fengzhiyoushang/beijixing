// Search app.asar for a literal string; prints per-file hits.
// run: ELECTRON_RUN_AS_NODE=1 "<exe>" this.mjs <asar> <needle> [maxFiles]
import fs from 'node:fs'

const root = process.argv[2].replace(/\/$/, '')
const needle = process.argv[3]
const maxFiles = Number(process.argv[4] ?? 5)

const pkg = JSON.parse(fs.readFileSync(`${root}/package.json`, 'utf8'))
let dirs = 0
let files = 0
let readErrors = 0
const found = []

function walk(node, pre) {
  for (const key of Object.keys(node.files ?? {})) {
    const child = node.files[key]
    const full = `${pre}/${key}`
    if (child.files) {
      dirs++
      walk(child, full)
      continue
    }
    files++
    if (!/\.(js|mjs|cjs)$/.test(full)) continue
    let text
    try {
      text = fs.readFileSync(`${root}${full}`, 'utf8')
    } catch {
      readErrors++
      continue
    }
    if (!text.includes(needle)) continue
    const idx = text.indexOf(needle)
    const line = text.slice(0, idx).split('\n').length
    found.push({
      full,
      line,
      size: text.length,
      ctx: text.slice(Math.max(0, idx - 400), idx + 400)
    })
  }
}

walk(pkg, '')
console.log(`walked dirs=${dirs} files=${files} readErrors=${readErrors} hits=${found.length}`)
for (const hit of found.slice(0, maxFiles)) {
  console.log(`\n### ${hit.full} (line ~${hit.line}, size ${hit.size})\n${hit.ctx.replace(/\s+/g, ' ')}`)
}
