"""检查非宁大院校 /kaoyan/intel 的实际返回（employment 是否含 industry/companies）。"""
import sys

import httpx

BASE = "http://127.0.0.1:8000"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
c = httpx.Client(timeout=90)
r = c.post(f"{BASE}/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
H = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

# 当前目标
t = c.get(f"{BASE}/api/v1/kaoyan/target", headers=H).json()
print(f"当前目标：{t.get('school')} / {t.get('major')}")

# 切到华中科技大学并强制刷新情报
c.put(f"{BASE}/api/v1/kaoyan/target", headers=H,
      json={"school": "华中科技大学", "major": "计算机科学与技术", "degree_type": "学硕"})
print("\n已切换 → 拉取 /kaoyan/intel?force=true（真实抓取，可能较慢）…")
import time
t0 = time.time()
resp = c.get(f"{BASE}/api/v1/kaoyan/intel", params={"force": "true"}, headers=H)
print(f"HTTP {resp.status_code}  用时 {time.time()-t0:.1f}s")
if resp.status_code != 200:
    print(resp.text[:400]); sys.exit(1)
j = resp.json()
print(f"available={j.get('available')}  from_cache={j.get('from_cache')}  "
      f"is_national_fallback={j.get('is_national_fallback')}")
print(f"reason={j.get('reason')}")
print(f"source={str(j.get('source'))[:110]}")

emp = j.get("employment") or {}
print(f"\nemployment 键：{list(emp.keys())}")
print(f"  industry : {len(emp.get('industry') or [])} 项")
for x in (emp.get("industry") or [])[:6]:
    print(f"     - {x.get('name')} {x.get('share')}%")
print(f"  companies: {len(emp.get('companies') or [])} 家")
for x in (emp.get("companies") or [])[:6]:
    print(f"     - {x.get('name')} / {x.get('industry')} / {x.get('roles')}")
print(f"  positions: {len(emp.get('positions') or [])} 个 → {(emp.get('positions') or [])[:4]}")
print(f"  rate_3y  : {emp.get('rate_3y')}")
print(f"  profile_label={emp.get('profile_label')}  is_estimate={emp.get('is_estimate')}")
print(f"\n  salary_note={str(emp.get('salary_note'))[:150]}")
print(f"\nscore_lines: {len(j.get('score_lines') or [])} 条")
print(f"retest: {bool(j.get('retest'))}  content={len((j.get('retest') or {}).get('content') or [])}")

# 恢复
c.put(f"{BASE}/api/v1/kaoyan/target", headers=H,
      json={"school": t.get("school"), "major": t.get("major"),
            "degree_type": t.get("degree_type") or "学硕"})
print(f"\n已恢复目标为 {t.get('school')}")
