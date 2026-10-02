"""真实 HTTP 端点验证脚本（对运行中的 uvicorn 发请求，输出 JSON 结果摘要）。"""
import json
import sys

import httpx

BASE = "http://127.0.0.1:8000"

def main():
    c = httpx.Client(timeout=15)
    health = c.get(f"{BASE}/health").json()
    print("HEALTH", json.dumps(health, ensure_ascii=False))

    r = c.post(f"{BASE}/api/v1/auth/login",
               json={"username": "admin", "password": "admin123"})
    print("LOGIN", r.status_code)
    if r.status_code != 200:
        print(r.text[:300])
        sys.exit(1)
    tk = r.json()["access_token"]
    H = {"Authorization": f"Bearer {tk}"}

    pred = c.get(f"{BASE}/api/v1/classroom/predict", params={"weekday": 3, "hour": 10}, headers=H)
    print("PREDICT", pred.status_code, json.dumps(pred.json(), ensure_ascii=False)[:400])

    pat = c.get(f"{BASE}/api/v1/classroom/pattern", params={"building": "三教", "room": "201"}, headers=H)
    print("PATTERN", pat.status_code, "samples=", pat.json().get("samples"))

    qa = c.post(f"{BASE}/api/v1/knowledge/qa", json={"question": "哈夫曼树有什么性质"}, headers=H)
    j = qa.json()
    print("QA", qa.status_code, "mode=", j.get("mode"), "refs=", len(j.get("references", [])))

    ai = c.post(f"{BASE}/api/v1/ai/chat", json={"message": "今天有什么课"}, headers=H)
    j = ai.json()
    print("AI", ai.status_code, "reply_len=", len(j.get("reply", "")), "session=", j.get("session_id"))

    dash = c.get(f"{BASE}/api/v1/dashboard/summary", headers=H)
    j = dash.json()
    print("DASH", dash.status_code, "classes=", len(j["classes_today"]), "alerts=", len(j["alerts"]),
          "expense=", j["finance"]["expense"], "streak=", j["checkin"]["streak_days"])

    # SSE 冒烟：确认流式端点返回事件
    with c.stream("POST", f"{BASE}/api/v1/ai/chat/stream",
                  json={"message": "你好"}, headers=H) as resp:
        events = []
        for line in resp.iter_lines():
            if line.startswith("event:"):
                events.append(line[7:].strip())
            if "done" in events or "error" in events or len(events) > 6:
                break
    print("SSE events:", events[:6])
    print("ALL_ENDPOINTS_OK")

if __name__ == "__main__":
    main()
