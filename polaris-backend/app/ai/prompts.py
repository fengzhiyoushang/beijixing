"""提示词模板集中管理。"""
from __future__ import annotations

SYSTEM_ASSISTANT = """你是「北极星 · 个人战略终端」的 AI 助手，服务于一名正在备考研究生的中国大学生。
你的职责：
1. 用简洁、务实、鼓励式的中文回答（默认 3 段以内，必要时用列表）；
2. 涉及个人数据（课表、DDL、学习时长、财务、健康、考研进度）时，必须先调用工具获取真实数据，禁止编造；
3. 需要写入数据（新建 DDL、记一笔支出、记录学习/健康）时，先调用工具完成，再向用户确认结果；
4. 时间表述使用中文日期，金额使用 ¥ 符号，时长给出小时与分钟。
当前时间：{now}
用户：{nickname}（{school} {role}）
"""

RAG_PROMPT = """请严格依据下面提供的「知识库片段」回答用户问题。

要求：
- 只使用片段中的信息；片段不足以回答时，明确说明「知识库中未找到相关内容」，并给出可行的补充建议；
- 回答末尾用 [资料1]、[资料2] 标注引用来源编号；
- 保持结构清晰，可用小标题与列表。

知识库片段：
{context}

用户问题：{question}
"""

KAOYAN_PLAN_PROMPT = """请为以下考研学生生成分阶段学习计划。

目标信息：
- 院校专业：{school} {major}（{degree_type}）
- 初试日期：{exam_date}（剩余 {days_left} 天，约 {total_weeks} 周）
- 总分目标：{total_target}，当前预估：{total_current}
- 各科情况（科目/当前/目标/满分）：{subjects}
- 每日可投入：{daily_minutes} 分钟

要求输出严格的 JSON（不要任何额外文字、不要 markdown 代码块），结构：
{{
  "phases": [
    {{
      "name": "阶段名（如 基础阶段/强化阶段/冲刺阶段）",
      "weeks": 6,
      "focus": "该阶段重点（60 字以内）",
      "subjects": ["数学", "408"],
      "progress": 0
    }}
  ],
  "daily_tasks": [
    {{"subject": "数学", "title": "具体任务（30 字以内）", "minutes": 90}}
  ],
  "advice": "整体建议（120 字以内，指出提分优先级）"
}}
约束：phases 数量 2~4 个且 weeks 之和等于 {total_weeks}；daily_tasks 数量 4~8 条；daily_tasks 的 minutes 之和不超过 daily_minutes。
"""

VISION_PROMPT = """你是教室使用状态识别助手。请观察这张教室照片，判断当前使用情况。

只输出严格 JSON（不要 markdown 代码块、不要多余文字）：
{{
  "status": "free | busy | unknown",
  "occupied_ratio": 0.0~1.0,
  "confidence": 0.0~1.0,
  "seats_visible": 估计可见座位数（整数，未知填 0）,
  "occupied_seats": 估计已占用座位数（整数，未知填 0）,
  "reason": "判断依据（30 字以内，如：多数座位无人、桌面干净）"
}}
判定标准：可见座位大多空置且无人 → free；多数座位有人或放置大量物品 → busy；画面模糊/非教室场景 → unknown。
"""

WEEKLY_REVIEW_PROMPT = """基于以下本周数据，写一份 150 字以内的中文复盘。

数据：
- 学习时长（分钟/天）：{study_series}
- 各科分布：{subject_dist}
- DDL 完成：{ddl_done}/{ddl_total}
- 睡眠（小时/天）：{sleep_series}
- 久坐提醒触发次数：{sedentary_alerts}

要求：先给一句总体评价，再指出 1 个亮点与 1 个改进点，最后给 1 条下周可执行建议。不要罗列原始数字。
"""

MOCK_REPLY = (
    "（当前未配置 DEEPSEEK_API_KEY，运行在演示模式）我已收到你的请求：「{question}」。\n"
    "配置 .env 中的 DEEPSEEK_API_KEY 后，我将具备真实对话、Function Call 数据操作与 RAG 问答能力。\n"
    "现在你也可以直接调用工具接口获取真实数据，例如：GET /api/v1/tasks/stats 。"
)
