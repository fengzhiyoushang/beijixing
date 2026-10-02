# StudyLifeOS · 个人学习·工作·生活管理终端

三端一体的个人管理系统：**Web 深度管理端**（Vue 3 + Vite + Naive UI + ECharts，深色极客风，右下角常驻 AI 助手）＋ **微信小程序采集端**（原生 + Vant Weapp：课表 / 空教室 / DDL / 打卡）＋ **FastAPI 统一后端**（MySQL/Redis 可回退 SQLite/内存，DeepSeek 全链路 AI）。

> 完整设计见 [docs/技术方案设计.md](docs/技术方案设计.md)

## 目录结构

```
study-life-os/
├── docs/          # 技术方案设计
├── backend/       # FastAPI 后端（8 大模块 REST + AI 编排 + RAG）
├── web/           # Vue3 管理端（深色主题仪表盘）
└── miniprogram/   # 微信小程序（轻量查询与采集）
```

## 核心功能模块

1. **课程表管理** — Web 编辑 / Excel·JSON 导入 / 冲突检测；小程序周课表查询 + 上课提醒
2. **DDL 任务** — 全生命周期 + 统计分析；快速录入 + 倒计时
3. **空教室** — 拍照标注采集 → 规律分析 → 空闲预测
4. **考研规划** — 差距分析 → 阶段生成 → 每日拆解 → AI 复盘
5. **知识库** — 多格式文档 / Markdown / RAG 问答 / 量化评估
6. **财务** — 收支记账 / 学习投入专项 / 预算
7. **健康** — 久坐提醒 / 作息 / 健康报告
8. **全局 AI 助手** — 悬浮窗 Function Call，可查询并操作系统内所有数据

## 快速开始

### 后端（零依赖即可运行：默认 SQLite + 内存缓存）
```bash
cd backend
python -m venv .venv
# 国内网络建议加镜像：-i https://mirrors.aliyun.com/pypi/simple/
.venv\Scripts\pip install -r requirements.txt     # Linux/Mac: source .venv/bin/activate
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```
- 首次启动自动建表并写入演示账号：**admin / admin123**（含课表/DDL/教室快照/财务/健康等演示数据）
- Swagger 文档：<http://localhost:8000/docs>
- 无 DEEPSEEK_API_KEY / Redis / MySQL 时全部自动降级，功能照常可用
- 自检：`.venv\Scripts\python -m pytest tests -q`；服务拉起后可再跑 `.venv\Scripts\python tests\verify_http.py` 验证真实端点

### Web 端
```bash
cd web
npm install        # 或 pnpm install（pnpm v10+ 首次构建 esbuild 需信任：仓库已内置 pnpm-workspace.yaml）
npm run dev        # http://localhost:5173 （已代理 /api、/uploads → :8000）
```
- 生产构建验证：`npm run build`（产物在 `web/dist/`）

### 微信小程序
1. 先 `cd miniprogram && npm install`，再在微信开发者工具中「构建 npm」生成 `miniprogram_npm`
2. 工具菜单 → 详情 → 本地设置 → 勾选「不校验合法域名」
3. 页面：今日总览 / 课表 / DDL 列表+快速录入 / 学习打卡 / 教室拍照采集 / 我的
4. 「我的」页可切换后端地址（真机填电脑局域网 IP）、用 Web 账号（admin/admin123）登录实现**双端同数据**，或保持小程序独立身份

## AI 配置说明

`backend/.env` 中设置 `DEEPSEEK_API_KEY` 后，悬浮助手即具备 Function Call 全数据操作能力；未配置时后端进入降级模式（基础问答 + 本地数据直查），不影响其他模块联调。
