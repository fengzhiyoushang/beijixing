// Search every file inside an asar for a literal substring (Electron patched fs).
// run: ELECTRON_RUN_AS_NODE=1 "<exe>" this.mjs <asar> <needle> [maxHits]
import fs from 'node:fs'

const [asar, needle, maxHitsArg] = process.argv.slice(2)
const maxHits = Number(maxHitsArg ?? 20)
const root = asar.endsWith('/') ? asar.slice(0, -1) : asar

const header = JSON.parse(fs.readFileSync(`${root}/package.json`, 'utf8'))
let hits = 0
let scanned = 0
const errors = new Set()

function walk(node, pre) {
  for (const key of Object.keys(node.files ?? {})) {
    if (hits >= maxHits) return
    const child = node.files[key]
    const full = `${pre}/${key}`
    if (child.files) {
      walk(child, full)
      continue
    }
    if (!/\.(js|mjs|cjs|json|yml|yaml)$/.test(full)) continue
    let text
    try {
      text = fs.readFileSync(`${root}${full}`, 'utf8')
    } catch (err) {
      errors.add(String(err.code))
      continue
    }
    scanned++
    if (!text.includes(needle)) continue
    const idx = text.indexOf(needle)
    const line = text.slice(0, idx).split('\n').length
    hits++
    const ctx = text.slice(Math.max(0, idx - 300), idx + 300).replace(/\s+/g, ' ')
    console.log(`\n### ${full} (line ~${line})\n${ctx}`)
  }
}

walk(header, '')
console.log(`\n[scanned ${scanned}, hits ${hits}, read errors: ${[...errors].join(',') || 'none'}]`)
