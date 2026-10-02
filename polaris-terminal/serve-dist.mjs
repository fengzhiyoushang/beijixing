/* 生产构建静态服务器：服务 dist/ 并将 /api /uploads /health 代理到后端 8000 */
import http from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize } from 'node:path'

const ROOT = join(process.cwd(), 'dist')
const BACKEND = 'http://127.0.0.1:8000'
const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.jpg': 'image/jpeg',
}

http.createServer(async (req, res) => {
  const url = req.url || '/'
  try {
    if (/^\/(api|uploads|health)(\/|$|\?)/.test(url)) {
      const body = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(req.method) ? await new Promise((r) => {
        const c = []; req.on('data', (d) => c.push(d)); req.on('end', () => r(Buffer.concat(c)))
      }) : undefined
      const fwdHeaders = {}
      for (const [k, v] of Object.entries(req.headers)) {
        if (!['host', 'connection', 'content-length', 'transfer-encoding'].includes(k)) fwdHeaders[k] = v
      }
      const upstream = await fetch(BACKEND + url, {
        method: req.method, body, duplex: body ? 'half' : undefined,
        headers: fwdHeaders,
      })
      const outHeaders = {}
      for (const [k, v] of upstream.headers.entries()) {
        if (!['content-length', 'transfer-encoding', 'content-encoding'].includes(k)) outHeaders[k] = v
      }
      res.writeHead(upstream.status, outHeaders)
      res.end(Buffer.from(await upstream.arrayBuffer()))
      return
    }
    let p = normalize(decodeURIComponent(url.split('?')[0]))
    if (p.includes('..')) { res.writeHead(403); res.end(); return }
    let file = join(ROOT, p)
    try {
      const data = await readFile(file)
      res.writeHead(200, { 'content-type': MIME[extname(file)] || 'application/octet-stream', 'cache-control': 'no-cache' })
      res.end(data)
    } catch {
      const html = await readFile(join(ROOT, 'index.html'))
      res.writeHead(200, { 'content-type': 'text/html', 'cache-control': 'no-cache' })
      res.end(html)
    }
  } catch (e) {
    res.writeHead(500); res.end(String(e))
  }
}).listen(5300, '127.0.0.1', () => console.log('dist server: http://127.0.0.1:5300/'))
