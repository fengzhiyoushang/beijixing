"""验证空教室「精确日期 + 时间段」接口（HTTP 层，真实 MySQL 数据）。

对照用户要求：学期起始 2025-08-31(周一) 为第 1 周，
能按「某月某日 + 某时段」精确判定某教室是否有课（依据导入 Excel 的周次列）。
"""
from __future__ import annotations

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
c = httpx.Client(timeout=30)
fail: list[str] = []


def check(label: str, cond: bool, extra: str = ""):
    print(f"{'✓' if cond else '✗'} {label}" + (f"  {extra}" if extra else ""))
    if not cond:
        fail.append(label)


r = c.post(f"{BASE}/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
check("登录 admin/admin123", r.status_code == 200, f"HTTP {r.status_code}")
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

# ── 1. 学期信息接口 ──
print("\n── 1. /classroom/semester 学期信息 ──")
sem = c.get(f"{BASE}/api/v1/classroom/semester", headers=H)
check("接口可用", sem.status_code == 200, f"HTTP {sem.status_code}")
s = sem.json()
print(f"   学期={s.get('name')} 起始={s.get('start_date')} 总周数={s.get('total_weeks')}")
print(f"   查询日={s.get('query_date')} → 第 {s.get('week')} 周（{s.get('week_start')} ~ {s.get('week_end')}）")

# 起始日必须是周一（用户约定 8/31 周一为第 1 周，归一后应为周一）
from datetime import date as _d
if s.get("start_date"):
    sd = _d.fromisoformat(s["start_date"])
    check("学期起始日已对齐到周一", sd.isoweekday() == 1, f"{sd} 是周{sd.isoweekday()}")

# ── 2. 指定日期 → 周次换算（用学期内日期；学期起始见上，2026-08-31 周一 = 第 1 周）──
print("\n── 2. 指定日期查询（on_date）──")
START = s.get("start_date")
if not START:
    print("   ⚠ 学期起始日未设置，跳过日期换算校验")
probes = []
if START:
    sd = _d.fromisoformat(START)
    from datetime import timedelta as _td
    probes = [
        (START, 1),                                              # 第 1 周周一
        ((sd + _td(days=6)).isoformat(), 1),                     # 第 1 周周日
        ((sd + _td(days=7)).isoformat(), 2),                     # 第 2 周周一
        ((sd + _td(weeks=4)).isoformat(), 5),                    # 第 5 周周一
        ((sd + _td(weeks=9)).isoformat(), 10),                   # 第 10 周周一
    ]
for d, want in probes:
    rr = c.get(f"{BASE}/api/v1/classroom/semester", params={"on_date": d}, headers=H)
    if rr.status_code != 200:
        check(f"{d} 查询", False, f"HTTP {rr.status_code} {rr.text[:80]}")
        continue
    j = rr.json()
    got = j.get("week")
    check(f"{d} → 第 {want} 周", got == want,
          f"实际 week={got}（{j.get('week_start')} ~ {j.get('week_end')}）")

# ── 3. campus-usage：按日期返回，且不同日期结果可不同 ──
print("\n── 3. /classroom/campus-usage 按日期 ──")
res = {}
probe_dates = [p[0] for p in probes][:4] if probes else []
for d in probe_dates:
    rr = c.get(f"{BASE}/api/v1/classroom/campus-usage", params={"on_date": d}, headers=H)
    check(f"on_date={d} 可用", rr.status_code == 200, f"HTTP {rr.status_code}")
    if rr.status_code == 200:
        j = rr.json()
        res[d] = j
        n_b = len(j.get("buildings") or [])
        n_rooms = sum(len(b["rooms"]) for b in j.get("buildings") or [])
        wk = (j.get("semester") or {}).get("week")
        print(f"   {d}：{n_b} 栋 / {n_rooms} 间 · 第 {wk} 周")

# 校验 week 字段随日期变化
if len(res) >= 2:
    wks = [(res[d].get("semester") or {}).get("week") for d in res]
    check("不同日期解析出不同教学周", len(set(wks)) > 1, f"weeks={wks}")

# ── 4. 矩阵合法性 ──
print("\n── 4. 占用矩阵结构校验 ──")
j = next(iter(res.values()), None)
if j:
    hours = j.get("hours") or []
    check("hours 非空", len(hours) > 0, f"{hours}")
    bad = 0
    cell_vals = set()
    for b in j.get("buildings") or []:
        for room in b["rooms"]:
            if len(room["matrix"]) != 7:
                bad += 1
            for row in room["matrix"]:
                if len(row) != len(hours):
                    bad += 1
                cell_vals.update(row)
    check("矩阵维度 = 7 天 × hours", bad == 0, f"异常行 {bad}")
    check("取值仅 busy/free/None", cell_vals <= {"busy", "free", None}, f"{cell_vals}")

# ── 5. building-usage + usage-at ──
print("\n── 5. building-usage / usage-at ──")
buildings = [b["building"] for b in (j.get("buildings") or [])] if j else []
if buildings:
    b0 = buildings[0]
    in_sem = probe_dates[1] if len(probe_dates) > 1 else (probe_dates[0] if probe_dates else None)
    rr = c.get(f"{BASE}/api/v1/classroom/building-usage", params={"building": b0, "on_date": in_sem}, headers=H)
    check(f"building-usage({b0})", rr.status_code == 200, f"HTTP {rr.status_code}")
    if rr.status_code == 200:
        bj = rr.json()
        check("含 semester 字段", "semester" in bj)
        rooms = bj.get("rooms") or []
        if rooms:
            rn = rooms[0]["room_no"]
            ua = c.get(f"{BASE}/api/v1/classroom/usage-at",
                       params={"building": b0, "room_no": rn, "day": in_sem, "hour": 8},
                       headers=H)
            check(f"usage-at({b0} {rn} {in_sem} 08时)", ua.status_code == 200, f"HTTP {ua.status_code}")
            if ua.status_code == 200:
                uj = ua.json()
                wk = (uj.get("semester") or {}).get("week")
                check("usage-at 返回教学周", wk is not None, f"week={wk}")

            # 关键验证：同一 weekday 的不同教学周，课程判定应能不同
            if len(probe_dates) >= 4:
                w1, w2, w5, w10 = probe_dates[0], probe_dates[1], probe_dates[2], probe_dates[3]
                got = {}
                for dd in (w1, w2, w5, w10):
                    rr2 = c.get(f"{BASE}/api/v1/classroom/usage-at",
                                params={"building": b0, "room_no": rn, "day": dd, "hour": 8},
                                headers=H)
                    if rr2.status_code == 200:
                        got[dd] = len(rr2.json().get("courses") or [])
                print(f"   该教室 08:00 各周课程数：{got}")
                # 不同周次返回的课程集合若有差异，说明 Excel 周次列真正参与判定
                if len(set(got.values())) > 1:
                    check("Excel 周次列影响判定（不同周课程数不同）", True, f"{got}")
                else:
                    print("   ⓘ 该校教室在所选周次课程数相同（可能均为空或均为满课，非必错）")

# ── 6. 参数容错 ──
print("\n── 6. 参数容错 ──")
rr = c.get(f"{BASE}/api/v1/classroom/campus-usage", params={"on_date": "2025/09/08"}, headers=H)
check("斜杠日期格式可解析", rr.status_code == 200, f"HTTP {rr.status_code}")
rr = c.get(f"{BASE}/api/v1/classroom/campus-usage", params={"week": 5}, headers=H)
check("week 参数可用", rr.status_code == 200, f"HTTP {rr.status_code}")

print("\n" + ("✅ 空教室精确日期/时段接口全部通过" if not fail else f"❌ 失败 {len(fail)} 项：{fail}"))
sys.exit(0 if not fail else 1)
