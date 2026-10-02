"""真实 HTTP 端点验证脚本（对运行中的服务发请求，输出结果摘要）。

用法： .venv\\Scripts\\python tests\\verify_http.py [base_url]
"""
from __future__ import annotations

import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"


def main() -> int:
    client = httpx.Client(timeout=20)
    ok = True

    def show(label: str, resp: httpx.Response, extra: str = "") -> dict | None:
        nonlocal ok
        flag = "OK " if resp.status_code < 400 else "ERR"
        if resp.status_code >= 400:
            ok = False
        print(f"[{flag}] {label:<38} {resp.status_code} {extra}")
        if resp.status_code >= 400:
            print("      ", resp.text[:200])
        try:
            return resp.json()
        except Exception:
            return None

    health = show("GET /health", client.get(f"{BASE}/health"))
    if health:
        print(f"       db={health['database']['engine']} cache={health['cache']['mode']} "
              f"ai={health['ai']['mode']}")

    docs = show("GET /docs（接口文档）", client.get(f"{BASE}/docs"))
    openapi = client.get(f"{BASE}/openapi.json").json()
    print(f"[OK ] OpenAPI 路径数：{len(openapi['paths'])}")

    login = show("POST /auth/login（admin）", client.post(
        f"{BASE}/api/v1/auth/login", json={"username": "admin", "password": "admin123"}))
    if not login:
        print("! 请先执行：python scripts/init_db.py --seed")
        return 1
    token = login["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"       用户：{login['user']['nickname']}（{login['user']['school'] if 'school' in login['user'] else login['user']['config'].get('school')}）")

    show("GET /courses/week", client.get(f"{BASE}/api/v1/courses/week", headers=headers))
    show("GET /courses/today", client.get(f"{BASE}/api/v1/courses/today", headers=headers))
    show("GET /tasks/stats", client.get(f"{BASE}/api/v1/tasks/stats", headers=headers))
    show("GET /tasks/today", client.get(f"{BASE}/api/v1/tasks/today", headers=headers))
    show("GET /classroom/predict", client.get(f"{BASE}/api/v1/classroom/predict", headers=headers))
    show("GET /classroom/buildings", client.get(f"{BASE}/api/v1/classroom/buildings", headers=headers))
    show("GET /study/stats?days=7", client.get(f"{BASE}/api/v1/study/stats?days=7", headers=headers))
    show("GET /kaoyan/gap-analysis", client.get(f"{BASE}/api/v1/kaoyan/gap-analysis", headers=headers))
    show("GET /knowledge/stats", client.get(f"{BASE}/api/v1/knowledge/stats", headers=headers))
    show("POST /knowledge/qa（RAG）", client.post(
        f"{BASE}/api/v1/knowledge/qa", headers=headers,
        json={"question": "时间片轮转和优先级调度有什么区别"}))
    show("GET /finance/summary", client.get(f"{BASE}/api/v1/finance/summary", headers=headers))
    show("GET /health/report（健康）", client.get(f"{BASE}/api/v1/health/report", headers=headers))
    show("GET /system/runtime", client.get(f"{BASE}/api/v1/system/runtime", headers=headers))
    show("GET /system/tables", client.get(f"{BASE}/api/v1/system/tables", headers=headers))

    tools = show("GET /ai/tools", client.get(f"{BASE}/api/v1/ai/tools", headers=headers))
    if tools:
        names = ", ".join(t["name"] for t in tools["items"][:8])
        print(f"       工具 {tools['total']} 个：{names} …")

    called = show("POST /ai/tools/call（总览）", client.post(
        f"{BASE}/api/v1/ai/tools/call", headers=headers,
        json={"name": "get_dashboard_summary", "arguments": {"days": 7}}))
    if called:
        print(f"       今日课程 {len(called.get('courses_today', []))} 节 · "
              f"待办 {called['tasks']['pending']} · 本周学习 {called['study']['total_hours']}h")

    chat = show("POST /ai/chat（对话+工具）", client.post(
        f"{BASE}/api/v1/ai/chat", headers=headers, json={"message": "今天有什么课？"}))
    if chat:
        print(f"       工具轨迹 {len(chat['tool_traces'])} 条 · 回复 {len(chat['reply'])} 字")

    print("\n—— SSE 流式对话 ——")
    events: list[str] = []
    with client.stream("POST", f"{BASE}/api/v1/ai/chat/stream", headers=headers,
                       json={"message": "帮我看看学习进度"}) as resp:
        for line in resp.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
            if "done" in events or "error" in events:
                break
    print("      事件序列：", " → ".join(events[:8]))

    print("\n" + ("✅ 全部端点验证通过" if ok else "⚠️ 存在失败端点，请查看上方输出"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
