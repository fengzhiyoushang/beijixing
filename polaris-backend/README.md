# 北极星 · 个人战略终端 —— 后端服务（FastAPI + SQLAlchemy + MySQL + Redis + DeepSeek）

分层清晰（路由层 / 服务层 / 数据层 / AI 层 / 工具层）的生产级后端，覆盖 10 张核心数据表、
13 个业务模块共 **100+ 个接口**，并集成 DeepSeek 的 **对话 / Function Call / RAG / 多模态识图 / 考研计划生成** 五大能力；同时支持**微信订阅消息推送**（一次性订阅配额记账 + 定时扫描）与 **Docker / 公网 / 微信云托管** 三种落地方式。

> 全部能力**开箱即跑**：MySQL 不可用自动回退 SQLite、Redis 不可用回退进程内缓存、未配置 API Key 自动进入演示模式。

---

## 一、快速开始

```bash
cd polaris-backend

# 1) 创建虚拟环境并安装依赖（国内建议加镜像）
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
# Linux/macOS: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 2) 配置环境变量（可选：不配也能跑，走 SQLite + 演示 AI）
copy .env.example .env          # Linux/macOS: cp .env.example .env

# 3) 初始化数据库 + 写入演示数据
python scripts/init_db.py --seed

# 4) 启动服务
uvicorn app.main:app --reload --port 8000
#  接口文档： http://127.0.0.1:8000/docs
#  ReDoc：    http://127.0.0.1:8000/redoc
```

**演示账号**：`admin` / `admin123`（含 5 门课程、8 个 DDL、5 间教室 840 条状态快照、
49 条学习记录、3 阶段考研计划、5 篇已向量化文档、122 条财务流水、14 天健康记录）

### 自检

```bash
python -m pytest tests -q              # 端到端冒烟（独立 SQLite，覆盖全部模块）
python tests/verify_http.py            # 对运行中的服务逐个验证真实端点（含 SSE）
```

---

## 二、目录结构（分层架构）

```
polaris-backend/
├── requirements.txt            # 依赖清单
├── .env.example                # 全部可配置项（含注释）
├── scripts/
│   ├── init_db.py              # 数据库初始化（自动建库建表 / --seed / --drop / --stats）
│   └── seed_demo.py            # 演示数据生成
├── tests/
│   ├── test_api.py             # 端到端冒烟测试（11 个模块 + 权限隔离）
│   └── verify_http.py          # 真实 HTTP 端点验证
└── app/
    ├── main.py                 # 入口：CORS / 异常处理 / 路由挂载 / 静态文件 / 文档 / 启动初始化
    ├── core/                   # ── 基础设施层 ──
    │   ├── config.py           # pydantic-settings 配置（.env 注入，派生连接串）
    │   ├── database.py         # 引擎/会话/Base/get_db + MySQL→SQLite 自动回退
    │   ├── security.py         # PBKDF2 密码哈希、JWT 签发校验、微信 openid 派生
    │   ├── cache.py            # Redis 封装 + 进程内 TTL 回退（get_or_set/incr/前缀删除）
    │   ├── exceptions.py       # AppError 体系 + 全局异常处理器（统一 JSON 错误体）
    │   └── deps.py             # get_db / get_current_user / 分页依赖
    ├── models/                 # ── 数据层（ORM，含索引/外键/关联/派生字段）──
    │   ├── user.py course.py task.py classroom.py study.py
    │   ├── kaoyan.py knowledge.py finance.py health.py ai.py system.py
    │   └── base.py             # TimestampMixin / LongText（MySQL LONGTEXT 变体）
    ├── schemas/                # ── 校验层（Pydantic v2 出入参）──
    │   └── auth/course/task/classroom/study/kaoyan/knowledge/finance/health/system/ai.py
    ├── services/               # ── 服务层（业务逻辑，路由只做编排）──
    │   ├── course_service.py   # 冲突检测/批量导入/Excel 解析/周课表/今日课程
    │   ├── task_service.py     # 任务 CRUD/子任务/统计/临近提醒
    │   ├── classroom_service.py# 状态上报/空闲率矩阵/预测推荐/VL 识图落库
    │   ├── study_service.py    # 学习记录/模考/统计/连续打卡
    │   ├── kaoyan_service.py   # 目标/差距分析/成绩录入/计划生成（AI+规则）
    │   ├── knowledge_service.py# 文件夹/文档/解析/量化统计
    │   ├── finance_service.py  # 记账/汇总/趋势/预算/学习投入专项
    │   ├── health_service.py   # 按日 upsert/报告/久坐心跳与打断
    │   ├── system_service.py   # 配置管理/运行态/库表统计/备份恢复
    │   ├── dashboard_service.py# 仪表盘聚合（Redis 缓存 60s）
    │   ├── ai_service.py       # 会话管理/Function Call 循环/SSE 流式
    │   └── storage.py          # 上传落盘（类型/大小校验）
    ├── ai/                     # ── AI 层 ──
    │   ├── deepseek.py         # SDK 封装：chat / stream_chat / vision / embeddings + 重试 + mock
    │   ├── tools.py            # 21 个 Function Call 工具（schema + 处理器）
    │   ├── rag.py              # 切片 → 向量化 → 混合检索 → prompt → 生成
    │   ├── embeddings.py       # 远端 embedding 优先，零依赖本地哈希向量回退
    │   └── prompts.py          # 系统提示词 / RAG / 计划生成 / 识图 / 周复盘模板
    ├── routers/                # ── 路由层（11 个模块，95 个接口）──
    └── utils/timeutil.py       # 周次解析、节次换算、区间重叠、月份工具
```

---

## 三、数据库设计（10 张核心表 + 支撑表，共 23 张）

| # | 表名 | 说明 | 关键索引 / 约束 |
|---|------|------|----------------|
| ① | `users` | 用户信息、账号密码、微信绑定、配置项（JSON） | `username` 唯一、`wx_openid` 唯一 |
| ② | `semesters` / `courses` / `course_schedules` | 学期管理 + 课程（学期/课程名/老师/教室/学分/备注）+ 节次周次安排 | `(user_id, semester_id)`、`(course_id, weekday)`、`(weekday, start_section)` |
| ③ | `ddl_tasks` / `subtasks` | 标题/分类/优先级/截止/状态/关联课程/子任务 | `(user_id, status, due_at)`、`(user_id, category)`、`(user_id, priority)` |
| ④ | `classrooms` | 教学楼/教室编号/容量/座位/开放时间/类型 | `(building, room_no)` 唯一、`building` |
| ⑤ | `classroom_status_logs` | 教室/时间/状态/上报来源/识别置信度/照片 | `(building, room_no, recorded_at)`、`(weekday, hour)`、`(user_id, recorded_at)` |
| ⑥ | `study_records` | 日期/科目/学习时长/完成任务/模考成绩/专注度 | `(user_id, date)`、`(user_id, subject)` |
| ⑦ | `kaoyan_targets` / `kaoyan_plan_phases` / `kaoyan_plan_tasks` | 目标院校专业/各科分数线/当前成绩/差距分析 + 阶段计划 + 每日任务 | `(user_id, status)`、`(target_id, sort_order)`、`(phase_id, plan_date)` |
| ⑧ | `knowledge_folders` / `knowledge_docs` / `knowledge_chunks` | 文件夹/文档（标签、向量化状态）/切片向量 | `(user_id, folder_id)`、`(user_id, vector_status)`、`(doc_id, chunk_index)` |
| ⑨ | `finance_records` / `finance_budgets` | 收支类型/分类/金额/时间/备注/是否学习支出 + 预算 | `(user_id, occurred_at)`、`(user_id, category)`、`(user_id,is_study)`、预算唯一键 |
| ⑩ | `health_records` / `health_settings` | 睡眠/运动/久坐/体重/饮水/步数/心情 + 提醒设置 | `(user_id, date)` 唯一、`(user_id)` 唯一 |
| 支撑 | `ai_sessions` / `ai_messages` / `data_backups` / `system_configs` | AI 会话轨迹、备份记录、键值配置 | `(user_id, updated_at)`、`key` 唯一 |

**关系**：`users` 1→N 全部业务表（`ON DELETE CASCADE`）；`semesters` 1→N `courses` 1→N `course_schedules`；
`ddl_tasks` 1→N `subtasks`、可关联 `courses`；`kaoyan_targets` 1→N 阶段 1→N 任务；
`knowledge_docs` 1→N `knowledge_chunks`、可关联 `knowledge_folders`。

MySQL 建表时自动附带 `utf8mb4` 字符集与中文注释；`init_db.py` 会执行
`CREATE DATABASE IF NOT EXISTS` 并在库上建立全部索引。

---

## 四、接口总览（`/api/v1`，JWT Bearer 认证）

| 模块 | 前缀 | 主要接口 |
|------|------|---------|
| ① 总览仪表盘 | `/dashboard` | `/summary`（课程/任务/学习/考研/知识/财务/健康/教室一次聚合，Redis 缓存 60s）、`/alerts`、`/cache/clear` |
| ① 用户认证 | `/auth` | 注册、登录、微信登录/绑定、`/me`、改密、配置项更新 |
| ② 课程表 | `/courses` | 学期 CRUD/设当前学期、课程 CRUD、**冲突检测**、JSON/Excel 批量导入、`/week`、`/today` |
| ③ DDL 任务 | `/tasks` | CRUD、`/stats`、`/upcoming`、`/today`、`/categories`、完成/取消、子任务 CRUD |
| ④⑤ 空教室 | `/classroom` | 教室 CRUD、状态上报（JSON/带图 multipart）、**AI 识图**、`/free-rate`、`/predict`、`/overview` |
| ⑥ 学习记录 | `/study` | 记录 CRUD、`/stats`、`/progress`、模考成绩录入与列表 |
| ⑦ 考研规划 | `/kaoyan` | 目标 CRUD、`/gap-analysis`、`/scores`、`/plan/generate`、阶段与每日任务 CRUD、`/progress` |
| ⑧ 知识库 | `/knowledge` | 文件夹/文档 CRUD、上传解析（md/txt/docx/xlsx）、`/search`、`/qa`、`/vectorize`、`/stats` |
| ⑨ 财务 | `/finance` | 流水 CRUD、`/summary`、`/trend`、预算 CRUD、`/study-analysis` |
| ⑩ 健康 | `/health` | 记录 upsert/CRUD、`/report`、设置、`/sedentary/heartbeat`、`/sedentary/break` |
| ⑪ 系统管理 | `/system` | 配置 CRUD、`/runtime`、`/tables`、备份创建/列表/下载/删除/**恢复** |
| ⑫ AI 助手 | `/ai` | `/chat`、`/chat/stream`（SSE）、会话 CRUD、`/tools`、`/tools/call`、`/status`、`/reindex` |
| ⑬ 微信订阅消息 | `/wechat` | `/status`、`/quota`、`/subscribe/quota`（授权上报）、`/push/test`、`/push/scan`、`/push-logs` |

统一响应约定：错误返回 `{"code": "...", "message": "...", "detail": {...}}`；
分页参数 `page` / `page_size`；时间统一 `YYYY-MM-DD HH:MM:SS`。

---

## 五、DeepSeek 集成（`app/ai/`）

| 能力 | 实现 | 接口 |
|------|------|------|
| **SDK 统一封装** | `DeepSeekClient`：OpenAI 兼容协议、超时与指数退避重试、演示模式降级、`status()` 自检 | `app/ai/deepseek.py` |
| **基础对话** | 多轮上下文（落库 `ai_messages`）+ 流式输出 | `POST /ai/chat`、`POST /ai/chat/stream` |
| **Function Call** | **21 个工具**：课表查询 / 新建与完成 DDL / 任务统计 / 记学习记录 / 学习进度 / 空闲教室预测 / 上报教室状态 / 空闲率查询 / 考研差距 / 计划生成 / 成绩录入 / 知识检索 / RAG 问答 / 记账 / 财务汇总 / 健康记录 / 健康报告 / 久坐打断 / 总览聚合 …（最多 4 轮工具循环，全部在服务端执行并落轨迹） | `GET /ai/tools`、`POST /ai/tools/call` |
| **RAG 问答** | 段落感知切片（500 字/80 重叠）→ 向量化（远端 embedding 优先，本地哈希向量回退）→ **向量 0.65 + 关键词 0.35 混合检索** → 组装带引用编号的 prompt → 生成；无 Key 时输出抽取式答案 | `POST /knowledge/qa`、`POST /knowledge/search` |
| **多模态识图** | 接收 base64 → `deepseek-vl` 识别教室状态（返回 status/占用率/置信度/座位数），解析 JSON 并落库为 `classroom_status_logs`（source=`ai_vision`） | `POST /classroom/recognize`、`POST /classroom/recognize/upload` |
| **考研计划生成** | 依据目标分数、科目差距、剩余周数与每日可投入时长，生成 2~4 个阶段 + 每日任务拆解（严格 JSON 解析；AI 失败自动回退 45%/35%/20% 规则引擎） | `POST /kaoyan/plan/generate` |

启用真实 AI：在 `.env` 中设置

```ini
DEEPSEEK_API_KEY=sk-xxxxxxxx
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_VL_MODEL=deepseek-vl        # 视觉模型
EMBEDDING_PROVIDER=deepseek          # 使用远端向量；local 表示零依赖本地向量
```

---

## 六、MySQL / Redis 接入

```ini
# .env
DB_BACKEND=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的密码
MYSQL_DB=polaris_terminal
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_ENABLED=true
```

```bash
python scripts/init_db.py --seed      # 自动建库 + 建表 + 演示数据
python scripts/init_db.py --stats     # 查看各表行数
python scripts/init_db.py --drop --seed   # 重建（危险）
```

**降级行为**（无需任何配置即可开发）
- MySQL 连接失败 → 自动切换 SQLite（`data/polaris.db`），日志给出明确提示
- Redis 不可用 → 进程内 TTL 缓存，接口签名与行为不变（仪表盘 60s 缓存照常生效）
- 未配置 `DEEPSEEK_API_KEY` → 演示模式：对话返回提示、Function Call 用规则触发工具、识图返回启发式结果

---

## 七、部署与落地

三种落地方式，**完整操作步骤见 [../docs/落地部署手册.md](../docs/落地部署手册.md)**（含准备清单、费用、排错速查表、51 项上线检查清单）。

| 方式 | 适用 | 产物 |
| --- | --- | --- |
| **A. 本机 / 局域网自用** | 今天就能用，0 成本 | `uvicorn --host 0.0.0.0`；手机同一 WiFi 直连 |
| **B. 公网服务器** | 长期使用（需域名 + ICP 备案 + HTTPS） | `deploy/polaris.service`（systemd）、`deploy/nginx.conf`（含 SSE 免缓冲配置） |
| **C. Docker 一键起** | 换机器 / 云端部署 | `Dockerfile`、`docker-compose.yml`（api + MySQL 8 + Redis 7）、`docker-compose.override.yml`、`.dockerignore` |
| **D. 微信云托管** | 免备案、小程序体验最好 | 同一镜像推到云托管，用平台默认 HTTPS 域名 + 定时触发器跑提醒 |

```bash
# Docker 方式（首次）
cp .env.example .env            # 填 MYSQL_PASSWORD / DEEPSEEK_API_KEY
docker compose up -d
docker compose exec api python scripts/init_db.py --seed
# 接口文档 http://127.0.0.1:8000/docs  账号 admin/admin123
```

小程序服务器域名（公众平台 → 开发设置）需配置 `request` / `uploadFile` / `downloadFile` 为你的 HTTPS 域名；
订阅消息需在「订阅消息 → 我的模板」申请后把模板 ID 填入 `.env` 的 `WX_TEMPLATE_DDL` / `WX_TEMPLATE_CLASS`，
并按 cron 或云托管定时触发器运行：

```bash
python scripts/push_reminders.py            # DDL + 上课提醒一起扫
python scripts/push_reminders.py --kind ddl --ahead 180
# crontab： */10 * * * * cd /opt/polaris-backend && .venv/bin/python scripts/push_reminders.py >> backups/push.log 2>&1
```

> 一次性订阅限制：个人主体小程序每次授权只能推送一条，因此服务端会**精确记账**（`wx_subscription_quotas` 的
> `remaining`）并做**去重**（`wx_push_logs.dedup_key`），额度不足时写 `skipped_no_quota` 而不是无效调用。

## 八、验证结果（实测）

| 项目 | 命令 | 结果 |
|------|------|------|
| 建表 + 演示数据 | `python scripts/init_db.py --seed` | ✓ **25 张表**、1103 行演示数据（含 840 条教室快照、5 篇已向量化文档） |
| 端到端冒烟 | `python -m pytest tests -q` | ✓ **1 passed**，覆盖 13 个模块（含总览聚合、订阅配额记账、备份恢复 19 表） |
| 真实端点 | `python tests/verify_http.py` | ✓ 全部 200，OpenAPI **100+ 路径**，SSE 事件 `meta → tool×4 → token… → done` |
| 提醒扫描 | `python scripts/push_reminders.py` | ✓ 未配置微信时走演示模式：写日志 + 扣配额，不真实发送 |
| Function Call | 演示模式对话 | ✓ 单轮触发 4 次工具并给出结论 |
| 备份/恢复 | `/system/backups` | ✓ 用户维度备份 14 张业务表并可恢复 |

实测输出（节选）

```
health: sqlite memory mock
course conflict detected: 课程时间与已有安排冲突
classroom ok: samples 5 predict 东一舍 A302 80 | vision free mock
study ok: minutes 210 streak 2
kaoyan ok: plan source rule phases 3 daily 5 | gap 131.0 -> 119.0
knowledge ok: chunks 1 coverage 1.0 | qa mode extractive refs 1
finance ok: expense 405.0 balance 2095.0 study ratio 0.79
system ok: tables 23 backup rows 2 | restored tables 14
ai ok: tools 21 traces 4 | sse ['meta', 'tool', 'tool', 'tool', 'tool']
```

---

## 九、工程细节

- **统一异常体系**：业务异常 `AppError`（404/409/403…）、参数校验 422、唯一键冲突 409、数据库错误 500，全部返回结构化 JSON
- **CORS**：`CORS_ORIGINS` 逗号分隔，默认放行本地 5200/5173（前端开发端口）
- **上传安全**：扩展名白名单 + 大小限制（默认 20MB）+ UUID 重命名 + 按 `年月` 分目录
- **缓存**：仪表盘聚合结果缓存 60s，写操作自动失效（`dashboard_service.invalidate`）
- **可观测**：`/health`、`/system/runtime`（数据库/缓存/AI/向量/限额）、`/system/tables`（各表行数）
- **安全**：密码 PBKDF2-HMAC-SHA256（26 万次迭代，无 C 依赖）、JWT 含 `iss/iat/exp`、所有业务查询强制带 `user_id` 隔离
