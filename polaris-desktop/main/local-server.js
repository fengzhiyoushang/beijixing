/*
 * 本地静态 + 代理服务（Electron 主进程内运行）：
 * - 托管前端 dist（SPA fallback，支持 createWebHistory 深链接刷新）
 * - /api /uploads /health 代理到后端动态端口
 * - 代理使用双向 pipe 流式转发，保证 SSE（/ai/chat/stream）逐块到达、不被缓冲
 *
 * 改造自 polaris-terminal/serve-dist.mjs，核心差异：原实现 arrayBuffer() 全量读入
 * 再写出，会破坏流式响应；此处改为 req.pipe(upstream) + upstream.pipe(res)。
 */
const http = require('node:http')
const { readFile } = require('node:fs/promises')
const { extname, join, normalize } = require('node:path')

const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp',
  '.map': 'application/json', '.txt': 'text/plain',
}

/**
 * @param {{ frontPort: number, backendPort: number, distRoot: string }} opts
 * @returns {Promise<import('node:http').Server & { closeAsync(): Promise<void> }>}
 */
function createLocalServer({ frontPort, backendPort, distRoot }) {
  const proxyAgent = new http.Agent({ keepAlive: false })

  const server = http.createServer((req, res) => {
    const url = req.url || '/'
    if (/^\/(api|uploads|health)(\/|$|\?)/.test(url)) {
      proxy(req, res)
      return
    }
    serveStatic(req, res)
  })

  // ── 流式代理：双向 pipe，SSE 不缓冲 ──
  function proxy(req, res) {
    const fwdHeaders = { ...req.headers, host: `127.0.0.1:${backendPort}` }
    delete fwdHeaders.connection
    delete fwdHeaders['transfer-encoding']

    const upstream = http.request(
      { host: '127.0.0.1', port: backendPort, path: req.url, method: req.method, headers: fwdHeaders, agent: proxyAgent },
      (uRes) => {
        // 原样透传状态行与响应头（含 content-type / cache-control）；
        // Node 自动处理 chunked 分帧，无需手动转发 content-length/transfer-encoding
        const headers = { ...uRes.headers }
        delete headers['transfer-encoding']
        res.writeHead(uRes.statusCode || 502, headers)
        uRes.pipe(res)
      },
    )
    upstream.on('error', () => {
      if (!res.headersSent) res.writeHead(502, { 'content-type': 'application/json' })
      res.end('{"detail":"后端服务不可用"}')
    })
    req.pipe(upstream)
  }

  // ── 静态文件 + SPA fallback ──
  async function serveStatic(req, res) {
    let p = normalize(decodeURIComponent((req.url || '/').split('?')[0]))
    if (p.includes('..')) { res.writeHead(403); res.end(); return }
    if (p === '/' || p === '.') p = '/index.html'
    try {
      const data = await readFile(join(distRoot, p))
      res.writeHead(200, {
        'content-type': MIME[extname(p)] || 'application/octet-stream',
        'cache-control': 'no-cache',
      })
      res.end(data)
    } catch {
      try {
        const html = await readFile(join(distRoot, 'index.html'))
        res.writeHead(200, { 'content-type': 'text/html', 'cache-control': 'no-cache' })
        res.end(html)
      } catch {
        res.writeHead(500)
        res.end('dist 未构建：请先执行 npm run build:web')
      }
    }
  }

  return new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(frontPort, '127.0.0.1', () => {
      server.closeAsync = () => new Promise((r) => server.close(r))
      resolve(server)
    })
  })
}

/** 探测 count 个空闲端口（先占后放，供后端与静态服务分别使用） */
function pickFreePorts(count = 2) {
  const probes = []
  for (let i = 0; i < count; i++) {
    probes.push(new Promise((resolve, reject) => {
      const srv = http.createServer()
      srv.once('error', reject)
      srv.listen(0, '127.0.0.1', () => {
        const { port } = srv.address()
        srv.close(() => resolve(port))
      })
    }))
  }
  return Promise.all(probes)
}

module.exports = { createLocalServer, pickFreePorts }
