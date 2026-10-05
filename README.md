# 北极星 · Polaris

> 个人战略终端 —— 把课程、任务、空教室、考研、知识库、财务、健康和 AI 助手收拢到一块深色极客风的大屏里。

一个面向大学生的全栈个人管理系统：**Vue 3 + Vite 终端前端**、**FastAPI 分层后端（DeepSeek 全链路 AI）**、**Electron 桌面壳**、**微信小程序采集端**，开箱即跑，缺什么依赖自动降级，不影响核心功能演示。

---

## ✨ 核心特性

- **三端一体**：Web 深度管理端 + 微信小程序轻量采集端 + Electron 桌面壳，共用同一套 FastAPI 后端。
- **AI 全链路**：集成 DeepSeek，覆盖 **对话 / Function Call / RAG 知识库问答 / 多模态识图 / 考研计划生成** 五大能力。
- **开箱即跑**：
  - MySQL 不可用 → 自动回退 **SQLite**；
  - Redis 不可用 → 自动回退 **进程内缓存**；
  - 未配置 `DEEPSEEK_API_KEY` → 自动进入 **演示模式**，核心流程全部可用。
- **工程化分层**：后端按 `路由层 / 服务层 / 数据层 / AI 层 / 工具层` 切分，10 张核心数据表、13 个业务模块、**100+ 接口**，附端到端冒烟测试与真实 HTTP 端点验证脚本。
- **微信生态**：支持微信订阅消息推送（一次性订阅配额记录 + 定时扫描）与微信云托管部署。

## 🧱 技术栈

| 端 | 技术 |
|---|---|
| 终端前端 `polaris-terminal` | Vue 3 · Vite · Naive UI · ECharts · Vue Router |
| 后端 `polaris-backend` | FastAPI · SQLAlchemy 2.0 · PyMySQL · Redis · Pydantic v2 · PyJWT · Alembic · pytest |
| 桌面壳 `polaris-desktop` | Electron · electron-builder |
| 小程序 `study-life-os/miniprogram` | 原生微信小程序 · Vant Weapp |
| AI | DeepSeek（对话 / Function Call / RAG / VL 多模态识图） |
| 部署 | Docker Compose · 公网部署 · 微信云托管 |

## 📂 目录结构

```
.
├── polaris-terminal/        # Vue3 + Vite + Naive UI 深色极客风终端前端
├── polaris-backend/         # FastAPI 分层后端（路由/服务/数据/AI/工具）
│   ├── app/
│   │   ├── core/             # 配置、数据库、安全、缓存、异常、依赖
│   │   ├── models/           # ORM 模型（user/course/task/classroom/study/kaoyan/...）
│   │   ├── schemas/         # Pydantic v2 入参出参校验
│   │   └── services/        # 业务逻辑（路由只做编排）
│   ├── scripts/             # 初始化建库 / 演示数据 seed
│   ├── tests/               # 端到端冒烟 + 真实 HTTP 端点验证
│   ├── Dockerfile / docker-compose.yml
│   └── requirements.txt
├── polaris-desktop/         # Electron 无边框桌面壳（纯黑底 / 荧光绿 / 大圆角）
├── study-life-os/           # 三端一体的学习·工作·生活管理系统
│   ├── web/                 # Vue3 管理端
│   ├── miniprogram/         # 微信小程序（课表 / 空教室 / DDL / 打卡）
│   └── backend/             # 独立 FastAPI 后端
├── docs/                    # 落地部署手册、修复说明
├── build-all.ps1            # 一键构建脚本
└── start-dsh-web.ps1       # 本地启动脚本
```

## 🚀 快速开始

### 1. 启动后端（零依赖即可跑）

```bash
cd polaris-backend

# 创建虚拟环境并安装依赖（国内建议加镜像）
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
# Linux/macOS: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 配置环境变量（可选：不配也能跑，走 SQLite + 演示 AI）
copy .env.example .env          # Linux/macOS: cp .env.example .env

# 初始化数据库并写入演示数据
python scripts/init_db.py --seed

# 启动服务
uvicorn app.main:app --reload --port 8000
```

- Swagger 文档：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>

### 2. 启动终端前端

```bash
cd polaris-terminal
npm install        # 或 pnpm install
npm run dev        # 默认 http://localhost:5173，已代理 /api 与 /uploads 到 :8000
```

### 3. 演示账号

> `admin` / `admin123`

内置演示数据：5 门课程、4 张 DDL、空教室 840 条状态快照、49 条学习记录、阶段考研计划、精简版量化文档、22 条财务流水、4 天健康记录。

### 4. 自检

```bash
python -m pytest tests -q                # 端到端冒烟（独立 SQLite，覆盖全部模块）
python tests/verify_http.py              # 对运行中的服务逐端点验证（含 SSE）
```

## 🧩 核心功能模块

1. **课程表管理** — Web 编排 / Excel·JSON 导入 / 冲突检测；小程序周课表查询 + 上课提醒。
2. **DDL 任务** — 全生命周期周视图 + 统计分析；快速录入 + 倒计时。
3. **空教室** — 拍照定位采集 → 规律分析 → 空闲预测；集成 VL 识图落地库。
4. **考研规划** — 目标差距分析 → 阶段生成 → 每日拆解 → AI 复盘。
5. **知识库** — 多格式文档（Word / PDF / Markdown）→ RAG 问答 → 量化评估。
6. **财务** — 收支记账 / 学习投入专项 / 预算。
7. **健康** — 久坐提醒 / 作息 / 健康报告。
8. **全局 AI 助手** — 悬浮窗 + Function Call，可查询并操作系统内所有数据。

## 📄 部署

三种落地方式见 [`docs/落地部署手册.md`](docs/落地部署手册.md)：

- **Docker Compose** 一键起；
- **公网部署**（Nginx + Uvicorn 反代）；
- **微信云托管**（小程序直连）。

## 📝 License

仅用于学习与交流用途。
