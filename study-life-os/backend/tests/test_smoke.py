"""接口冒烟测试：TestClient 走完整 lifespan（建表+seed），覆盖核心链路。

运行：pytest tests -q （于 backend 目录）
"""
from fastapi.testclient import TestClient

from app.main import app


def _login(client: TestClient) -> str:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_health_and_core_flows():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"

        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

        week = client.get("/api/v1/courses/week", headers=headers)
        assert week.status_code == 200 and len(week.json()["days"]) == 7

        # 新建任务 → 完成
        created = client.post("/api/v1/tasks", headers=headers,
                              json={"title": "冒烟测试任务", "category": "study"})
        assert created.status_code == 201
        tid = created.json()["id"]
        assert client.post(f"/api/v1/tasks/{tid}/complete", headers=headers).status_code == 200

        # 打卡 → 统计
        assert client.post("/api/v1/checkin", headers=headers,
                           json={"subject": "测试", "minutes": 45}).status_code == 201
        assert client.get("/api/v1/checkin/stats", headers=headers).status_code == 200

        # 仪表盘聚合
        summary = client.get("/api/v1/dashboard/summary", headers=headers)
        assert summary.status_code == 200
        assert "classes_today" in summary.json()

        # 知识库 RAG
        qa = client.post("/api/v1/knowledge/qa", headers=headers,
                         json={"question": "中值定理口诀是什么"})
        assert qa.status_code == 200 and qa.json()["references"]

        # 冲突检测：与演示课程「高等数学A」周一 8:00-9:40 相撞
        conflict = client.post("/api/v1/courses", headers=headers,
                               json={"name": "冲突测试课",
                                     "slots": [{"weekday": 1, "start_time": "09:00", "end_time": "10:00"}]})
        assert conflict.status_code == 409

        # 考研流程
        client.put("/api/v1/kaoyan/goal", headers=headers, json={
            "target_school": "测试大学", "total_target": 400, "total_current": 300,
            "detail": {"subjects": {"数学": {"target": 150, "current": 100, "max": 150}}},
        })
        gap = client.post("/api/v1/kaoyan/gap-analysis", headers=headers)
        assert gap.status_code == 200 and gap.json()["numeric"]["total_gap"]

        # 财务 & 健康
        assert client.get("/api/v1/finance/summary", headers=headers).status_code == 200
        assert client.get("/api/v1/health/report", headers=headers).status_code == 200

        # AI（未配置 Key 走降级）
        ai = client.post("/api/v1/ai/chat", headers=headers, json={"message": "今天有什么课"})
        assert ai.status_code == 200 and ai.json()["reply"]
