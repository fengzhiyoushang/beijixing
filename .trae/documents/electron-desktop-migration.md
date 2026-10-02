# 北极星终端 Web → Electron 桌面应用迁移计划

## Context（背景与目标）

现有系统为 Web 架构：前端 `polaris-terminal`（Vue3 + Vite + Naive UI，fetch 走相对路径 `/api/v1`），后端 `polaris-backend`（FastAPI + uvicorn:8000，MySQL 可自动回退 SQLite，Redis 可回退内存缓存）。目标：迁移为可在 Windows/macOS 本地独立运行、保留全部功能与联网能力（AI、微信推送配置等）的桌面应用，数据本地存储，提供安装包。

**已确认决策**：① Electron 作桌面壳（本机无 Rust，排除 Tauri）；② 桌面版默认 SQLite 独立运行（无需装 MySQL），并提供一次性 MySQL→SQLite 迁移脚本；③ electron-builder 配好 win(NSIS)+mac(dmg)，Windows 本机产出安装包，macOS 在有 Mac 的机器上构建。

**核心架构**：Electron 主进程内起本地 HTTP 服务（托管前端 dist + 流式代理 `/api|/uploads|/health` 到后端动态端口），`BrowserWindow.loadURL('http://127.0.0.1:<port>')`。因加载的是真实 http origin，前端 `createWebHistory`、相对路径 API、fetch、SSE、blob 下载**全部零改动可用**。后端以子进程方式 spawn（开发态 venv python，生产态 PyInstaller onedir exe），数据/上传/备份目录注入 Electron userData。

```
polaris-desktop/                 ← 新增 Electron 工程
  main/main.js                   ← 选端口→起后端→等/health→起静态服务→loadURL→退出清理
  main/local-server.js           ← 改造自 serve-dist.mjs（流式代理）
  main/backend-manager.js        ← spawn / 就绪检测 / taskkill 树杀防孤儿
  main/preload.js                ← contextBridge 暴露 saveBlob/openExternal（可选增强）
  scripts/copy-dist.mjs          ← 前端 dist → resources/dist
  build/ resources/ package.json electron-builder.yml
运行期数据：%APPDATA%/polaris-desktop/{data/polaris.db, uploads/, backups/, jwt.secret, logs/}
```

## 阶段 1：Electron MVP（开发态跑通）

1. `polaris-desktop/` 初始化：package.json（`main: main/main.js`），安装 `electron`、`electron-builder`（devDependencies）。
2. **`main/local-server.js`**：以 [serve-dist.mjs](file:///f:/deepseek harness  wenjian/polaris-terminal/serve-dist.mjs) 为蓝本改造，**必改点**：原脚本第 25-34 行 `await upstream.arrayBuffer()` 会把 SSE 流憋到结束（AI 打字机失效）→ 改为 `http.request` 双向 pipe（`req.pipe(upstream)`、`uRes.pipe(res)`，响应头原样透传 `transfer-encoding`）；代理目标端口、dist 根路径改为参数注入。保留 SPA fallback。
3. **后端入口 `polaris-backend/run_backend.py`**（新增）：`from app.main import app` 直接传对象（解决 PyInstaller 字符串动态导入失败），host/port 读环境变量 `HOST/PORT`，`reload=False`（解决 reload 子进程孤儿）。
4. **`main/backend-manager.js`**：
   - 开发态 spawn `.venv\Scripts\python.exe run_backend.py`；
   - 环境变量注入：`DB_BACKEND=sqlite`、`SQLITE_PATH/UPLOAD_DIR/BACKUP_DIR` 指向 userData 绝对路径（[config.py](file:///f:/deepseek harness  wenjian/polaris-backend/app/core/config.py) 的 `Path / 绝对路径` 语义支持，且真实环境变量优先于 .env）、`REDIS_ENABLED=false`、`DEBUG=false`、`JWT_SECRET` 从 `userData/jwt.secret` 读取（不存在则随机生成并落盘，避免重启掉登录）、`CORS_ORIGINS=http://127.0.0.1:<frontPort>`；
   - 轮询 `GET /health` 就绪后才 loadURL；子进程 stdout/stderr 写 `userData/logs/backend.log`；
   - 退出清理：Windows 用 `taskkill /pid <pid> /T /F` 树杀，非 Windows SIGTERM→SIGKILL；在 `before-quit`/`window-all-closed`/`uncaughtException` 三处挂接，防孤儿进程。
5. **`main/main.js`**：单实例锁；`net.listen(0)` 探测两个空闲端口；按上述顺序编排；后端异常退出时弹 dialog 提示。
6. **验证**：`npm run dev` 起 Electron → admin/admin123 登录 → 各页面可用 → AI 助手逐 token 流式输出（确认代理不缓冲）→ 退出后任务管理器无残留 python 进程。

## 阶段 2：数据迁移脚本

新增 `polaris-backend/scripts/migrate_mysql_to_sqlite.py`（参考 [init_db.py](file:///f:/deepseek harness  wenjian/polaris-backend/scripts/init_db.py) 的路径注入写法）：
- 源 engine 用 MySQL（root/trr4699288/polaris_terminal），目标 engine 为 userData 下的 SQLite；
- `Base.metadata.create_all(dst)` 建表，按 `Base.metadata.sorted_tables`（外键拓扑序）逐表 `select` + `insert`，JSON 列由 SQLAlchemy 类型层自动序列化；
- **关键坑**：显式插入自增主键后须修正 `sqlite_sequence`（`UPDATE sqlite_sequence SET seq=(SELECT MAX(id) FROM 表) WHERE name=表名`），否则后续新建记录撞主键；
- 运行：`python scripts/migrate_mysql_to_sqlite.py --target "<userData>/data/polaris.db"`。

**验证**：迁移后桌面版重启，课程表/教室/备忘/考研/健康等既有数据可见；新建记录成功不撞主键。

## 阶段 3：PyInstaller 打包后端（最大风险点，独立验收）

1. venv 内 `pip install pyinstaller`。
2. 新增 `polaris-backend/polaris-backend.spec`，**onedir** 模式（启动快、便于 extraResources 整目录打包）：
   - `collect_submodules('uvicorn')`（loops/protocols/lifespan 运行时字符串导入，最常见打包失败根因）；
   - `collect_submodules('sqlalchemy.dialects.sqlite')`；
   - `collect_all`：`pdfplumber`、`pdfminer`（CMap 数据文件）、`docx`（默认模板）、`cryptography`、`pydantic`、`pydantic_core`、`certifi`（HTTPS CA，缺了联网 AI 报 SSL 错）；
   - hiddenimports：`app.*` 各包、`pymysql`、`jwt`、`multipart`、`email_validator`；
   - 不打包 `.env`（避免 DB_BACKEND=mysql 混入）；`console=True` 便于排障。
3. **裸跑验收（脱离 venv、脱离 Electron）**：设环境变量后直接运行 exe → `/health` 返回 `backend=sqlite` → 上传 PDF 课表（pdfplumber）、下载导入模板（openpyxl）、解析 docx、AI 流式对话（httpx+certifi 联网）全部通过。失败对照表：`ModuleNotFoundError: uvicorn.loops.auto`→补 collect_submodules；`FileNotFoundError cmap`→collect_all('pdfminer')；`SSL CERTIFICATE_VERIFY_FAILED`→collect_all('certifi')。

## 阶段 4：electron-builder 打包安装程序

1. `scripts/copy-dist.mjs`：`polaris-terminal/dist` → `polaris-desktop/resources/dist`（vite `base` 保持 `'/'` 不改，本地 http 服务下深链接刷新才正确）。
2. `backend-manager.js` 打包分支：`app.isPackaged` 时 spawn `process.resourcesPath/backend/polaris-backend.exe`。
3. `electron-builder.yml`：appId `com.polaris.terminal`；`files: ["main/**/*","package.json"]`；`extraResources`: `resources/dist→dist`、PyInstaller onedir 产物→`backend`；win target NSIS（oneClick:false、可选安装目录）；mac target dmg + category；图标 `build/icon.ico`/`icon.icns`（程序生成简单图标）。
4. npm scripts：`dev` / `build:web` / `build:backend` / `pack`。
5. **验证**：`npm run pack` 产出 NSIS 安装包 → 本机安装 → 走一遍端到端验证（下节）→ 卸载重装确认 userData 数据保留。macOS dmg 配置就绪，需在 Mac 上执行同一 `pack` 命令构建。

## 阶段 5：桌面体验打磨（小改动）

- [store/index.js](file:///f:/deepseek harness  wenjian/polaris-terminal/src/store/index.js#L133) `window.location.href='/login'` → `router.push('/login')`（避免整页刷新）；
- preload 暴露 `saveBlob`（原生另存为对话框），[api/index.js](file:///f:/deepseek harness  wenjian/polaris-terminal/src/api/index.js) 与 utils/export.js 的 3 处 blob 下载在 `window.electronAPI` 存在时走原生保存，否则保持浏览器行为（Web 端不受影响）；
- 主进程 `setWindowOpenHandler` → `shell.openExternal`（外链走系统浏览器）；
- 窗口标题/菜单适配（默认菜单精简，Ctrl+R 刷新等）。

## 端到端验证清单

1. 启动应用 → 登录 admin/admin123 → 总览/课程表/空教室/备忘/考研/知识/财务/健康/设置逐页 CRUD。
2. 联网：AI 助手流式回答（需 DEEPSEEK_API_KEY，可经 .env/userData 配置）；设置页微信推送配置读取正常。
3. 文件：上传 PDF/Excel 课表解析、照片上报、模板下载。
4. 持久化：新建数据 → 完全退出 → 重开仍在（SQLite 在 userData）。
5. 进程卫生：退出后无残留 `polaris-backend.exe`/python 进程；`userData/logs/backend.log` 有启停记录。
6. 安装包：NSIS 安装/卸载正常；Web 端 `pnpm dev` 原流程不受影响（未破坏现有工程）。

## 关键文件清单

| 操作 | 文件 |
|---|---|
| 新增 | `polaris-desktop/{package.json, electron-builder.yml, main/{main.js, local-server.js, backend-manager.js, preload.js}, scripts/copy-dist.mjs, build/图标}` |
| 新增 | `polaris-backend/{run_backend.py, polaris-backend.spec, scripts/migrate_mysql_to_sqlite.py}` |
| 微调 | `polaris-terminal/src/store/index.js`（logout 用 router）、`src/api/index.js` + `src/utils/export.js`（可选原生保存）、`polaris-desktop` 内可选应用图标 |

## 风险与应对

| 风险 | 应对 |
|---|---|
| SSE 被代理缓冲（serve-dist.mjs 已知缺陷） | local-server.js 双向 pipe，透传 transfer-encoding |
| PyInstaller 冻结后 uvicorn 字符串导入失败 | run_backend.py 直接传 app 对象 |
| pdfminer/docx/certifi 数据文件缺失 | collect_all 显式收集 + 裸跑 exe 独立验收 |
| 迁移后自增主键冲突 | 修正 sqlite_sequence |
| Windows 孤儿后端进程 | taskkill /T /F + 三处退出钩子 |
| 每次重启 JWT 失效掉登录 | 随机密钥持久化到 userData/jwt.secret |
