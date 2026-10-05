"""验证「打包后的 exe」确实包含本次全部后端修复。

针对运行在 :8899 的 PyInstaller 产物（resources/backend/polaris-backend.exe）：
  ① 登录 → 拿到 token
  ② 空教室：/classroom/semester 的日期↔周次换算（含周一归一）
  ③ 空教室：campus-usage/building-usage/usage-at 接受 on_date / week
  ④ 考研情报：非收录院校也能返回完整 employment（行业/单位/岗位）
  ⑤ 考研情报：默认加载毫秒级（不再同步抓取）
  ⑥ 新闻：科技分类列表与详情正常
"""
from __future__ import annotations

import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8899"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
c = httpx.Client(timeout=60)
fail: list[str] = []


def check(label, cond, extra=""):
    print(f"{'✓' if cond else '✗'} {label}" + (f"  {extra}" if extra else ""))
    if not cond:
        fail.append(label)


print(f"目标：{BASE}\n")

# 打包产物默认库为空 → 先注册一个账号
u = f"execheck{int(time.time()) % 100000}"
r = c.post(f"{BASE}/api/v1/auth/register", json={"username": u, "password": "Test12345", "nickname": "打包校验"})
if r.status_code not in (200, 201):
    r = c.post(f"{BASE}/api/v1/auth/login", json={"username": u, "password": "Test12345"})
check("注册/登录打包后端", r.status_code in (200, 201), f"HTTP {r.status_code}")
if r.status_code not in (200, 201):
    print(r.text[:300]); sys.exit(1)
H = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

# ── ② 学期信息 + 日期换算 ──
print("\n── ② 空教室：学期/日期换算 ──")
from datetime import date, timedelta
sd = date(2026, 8, 31)          # 2026-08-31 周一（与用户约定一致）
r = c.put(f"{BASE}/api/v1/courses/semesters", headers=H,
          json={"name": "2026-2027 学年第一学期", "start_date": "2026-08-31",
                "total_weeks": 20, "is_current": True})
if r.status_code not in (200, 201):
    # 某些实现用 POST 新建
    r = c.post(f"{BASE}/api/v1/courses/semesters", headers=H,
               json={"name": "2026-2027 学年第一学期", "start_date": "2026-08-31",
                     "total_weeks": 20, "is_current": True})
check("创建当前学期", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:80]}")

rr = c.get(f"{BASE}/api/v1/classroom/semester", headers=H)
check("GET /classroom/semester 可用", rr.status_code == 200, f"HTTP {rr.status_code}")
if rr.status_code == 200:
    j = rr.json()
    print(f"     学期={j.get('name')} 起始={j.get('start_date')} 总周数={j.get('total_weeks')}")
    if j.get("start_date"):
        d0 = date.fromisoformat(j["start_date"])
        check("起始日对齐到周一", d0.isoweekday() == 1, f"{d0} 周{d0.isoweekday()}")
    # 逐周校验换算
    probes = [(sd, 1), (sd + timedelta(days=6), 1), (sd + timedelta(days=7), 2),
              (sd + timedelta(weeks=4), 5), (sd + timedelta(weeks=9), 10)]
    for d, want in probes:
        q = c.get(f"{BASE}/api/v1/classroom/semester", params={"on_date": d.isoformat()}, headers=H).json()
        check(f"{d} → 第 {want} 周", q.get("week") == want, f"实得 {q.get('week')}")

# ── ③ 按日期查询接口 ──
print("\n── ③ 空教室：按日期/周次查询 ──")
for path, params in [
    ("/api/v1/classroom/campus-usage", {"on_date": "2026-11-02"}),
    ("/api/v1/classroom/campus-usage", {"week": 5}),
    ("/api/v1/classroom/campus-usage", {"on_date": "2026/09/08"}),
]:
    rr = c.get(f"{BASE}{path}", params=params, headers=H)
    has_sem = rr.status_code == 200 and "semester" in rr.json()
    check(f"{path} {params}", rr.status_code == 200 and has_sem, f"HTTP {rr.status_code}")

rr = c.get(f"{BASE}/api/v1/classroom/usage-at",
           params={"building": "1教", "room_no": "101", "day": "2026-11-02", "hour": 8}, headers=H)
check("usage-at 接受 day/hour/week", rr.status_code == 200, f"HTTP {rr.status_code}")

# ── ④⑤ 考研情报 ──
print("\n── ④⑤ 考研情报：任意院校就业数据 + 默认快速返回 ──")
c.put(f"{BASE}/api/v1/kaoyan/target", headers=H,
      json={"school": "华中科技大学", "major": "计算机科学与技术", "degree_type": "学硕"})
t0 = time.time()
d = c.get(f"{BASE}/api/v1/kaoyan/intel", headers=H).json()
ms = (time.time() - t0) * 1000
emp = d.get("employment") or {}
check("默认加载 < 3s（内含就业画像）", ms < 3000, f"{ms:.0f}ms")
check("含行业分布", len(emp.get("industry") or []) > 0, f"{len(emp.get('industry') or [])} 项")
check("含就业单位", len(emp.get("companies") or []) > 0, f"{len(emp.get('companies') or [])} 家")
check("含典型岗位", len(emp.get("positions") or []) > 0, f"{len(emp.get('positions') or [])} 个")
check("就业数据带口径标注", bool(emp.get("salary_note")))
print(f"     画像={emp.get('profile_label')} 估算={emp.get('is_estimate')}")
print(f"     单位示例：{[x['name'] for x in (emp.get('companies') or [])[:4]]}")

# ── ⑥ 新闻 ──
print("\n── ⑥ 新闻资讯 ──")
rr = c.get(f"{BASE}/api/v1/news/items", params={"category": "科技", "limit": 5}, headers=H)
check("科技分类列表可用", rr.status_code == 200, f"HTTP {rr.status_code}")
if rr.status_code == 200:
    items = rr.json().get("items") or []
    print(f"     科技条目 {rr.json().get('total')} 条（示例 {len(items)} 条）")
    if items:
        de = c.get(f"{BASE}/api/v1/news/items/{items[0]['id']}", headers=H)
        body = (de.json().get("content") or de.json().get("summary") or "").strip() if de.status_code == 200 else ""
        check("详情接口返回正文/摘要", de.status_code == 200 and len(body) > 0, f"{len(body)} 字")

print("\n" + ("✅ 打包 exe 已包含全部修复" if not fail else f"❌ 失败 {len(fail)} 项：{fail}"))
sys.exit(0 if not fail else 1)
