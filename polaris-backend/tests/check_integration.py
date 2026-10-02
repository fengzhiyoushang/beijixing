"""验证：后端运行态、微信配置状态、总览接口（联调自检脚本，可保留复用）。"""
import json

import httpx

BASE = "http://127.0.0.1:8000"
client = httpx.Client(timeout=20)

print("① 健康检查：")
health = client.get(f"{BASE}/health").json()
print("   ", json.dumps({k: health[k] for k in ("status", "database", "cache", "ai")},
                         ensure_ascii=False)[:220])

token = client.post(f"{BASE}/api/v1/auth/login",
                    json={"username": "admin", "password": "admin123"}).json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("\n② 微信订阅消息状态：")
wx = client.get(f"{BASE}/api/v1/wechat/status", headers=headers).json()
print("   ", json.dumps(wx, ensure_ascii=False))

print("\n③ 总览聚合：")
summary = client.get(f"{BASE}/api/v1/dashboard/summary", headers=headers).json()
print(f"    课程 {len(summary['courses_today'])} 节 · 待办 {summary['tasks']['pending']} 项 · "
      f"今日到期 {summary['tasks']['due_today']} 项 · 学习 {summary['study']['total_hours']}h · "
      f"提醒 {len(summary['alerts'])} 条")
kaoyan = summary["kaoyan"]
print(f"    考研：{kaoyan.get('school')} 距初试 {kaoyan.get('days_left')} 天 · "
      f"总分 {kaoyan.get('total_current')}/{kaoyan.get('total_target')} · 进度 {kaoyan.get('progress')}%")
print(f"    阶段数 {len(kaoyan.get('subjects') or [])} 个科目 · 快讯 {len(summary['alerts'])} 条")
print("\n✅ 联调自检完成")
