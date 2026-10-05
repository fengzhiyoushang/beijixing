"""验证考研情报爬虫增强：搜索兜底 + 表格/正文双解析。

不依赖真实网络（沙箱无 DNS），用合成的院校公告页 HTML 覆盖多种真实版式，
确认解析器都能提取出复试线（这是用户反馈「随机输入几所学校没有曲线图」的核心）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services.kaoyan_intel_service import (_GRAD_DOMAINS, _parse_score_tables,
                                               _parse_score_text, _school_core)

fail = []


def check(label, cond, extra=""):
    print(f"{'✓' if cond else '✗'} {label}" + (f"  {extra}" if extra else ""))
    if not cond:
        fail.append(label)


print("=== 1. 域名注册表覆盖度 ===")
check("注册院校数 ≥ 70", len(_GRAD_DOMAINS) >= 70, f"实得 {len(_GRAD_DOMAINS)}")
for s in ["清华大学", "华中科技大学", "西安电子科技大学", "郑州大学", "昆明理工大学"]:
    check(f"已收录 {s}", s in _GRAD_DOMAINS, str(_GRAD_DOMAINS.get(s))[:46])

print("\n=== 2. 表格解析：含专业代码 ===")
html_code = """
<table><tr><th>专业代码</th><th>专业名称</th><th>复试线</th><th>政治</th><th>外语</th><th>业务课一</th><th>业务课二</th></tr>
<tr><td>081200</td><td>计算机科学与技术</td><td>310</td><td>38</td><td>38</td><td>57</td><td>57</td></tr>
<tr><td>083500</td><td>软件工程</td><td>300</td><td>38</td><td>38</td><td>57</td><td>57</td></tr></table>
"""
r = _parse_score_tables(html_code, "081200", 2026)
check("解析出复试线", bool(r), str(r and r["line"]["line"]))
check("分数正确 = 310", r and r["line"]["line"] == 310)
check("解析出单科线", bool(r and r.get("single")), str(r and r.get("single")))
check("政治单科 = 38", r and r.get("single", {}).get("politics") == 38)

print("\n=== 3. 表格解析：只有专业名、无代码 ===")
html_name = """
<table><tr><td>计算机技术</td><td>085400</td><td>325</td></tr>
<tr><td>电子信息</td><td>330</td></tr></table>
"""
r = _parse_score_tables(html_name, "081200", 2026)
check("凭关键词命中", bool(r), str(r and r["line"]["line"]))
check("分数合理", r and 150 <= r["line"]["line"] <= 500, str(r and r["line"]["line"]))

print("\n=== 4. 正文解析：分数线写在段落里 ===")
html_text = """
<div><p>经学校研究生招生工作领导小组研究决定，2026年我校计算机科学与技术（081200）
复试分数线为 315 分，单科线 40 分。</p></div>
"""
r = _parse_score_text(html_text, "081200", 2026)
check("正文命中复试线", bool(r), str(r and r["line"]["line"]))
check("分数 = 315", r and r["line"]["line"] == 315)

print("\n=== 5. 正文解析：分数与『分』字分离 ===")
html_text2 = "<p>软件工程专业复试基本分数线：308分。</p>"
r = _parse_score_text(html_text2, "085400", 2026)
check("软件工程命中", bool(r), str(r and r["line"]["line"]))

print("\n=== 6. 噪声页面不应误报 ===")
html_noise = "<p>欢迎报考我校研究生，详情请咨询各学院。联系方式：010-1234567。</p>"
check("无分数线页面返回 None", _parse_score_text(html_noise, "081200", 2026) is None)
check("空表格返回 None", _parse_score_tables("<table><tr><td>45</td></tr></table>", "081200", 2026) is None)

print("\n=== 7. 院校归属校验 ===")
check("去掉院校后缀", _school_core("华中科技大学") == "华中科技", _school_core("华中科技大学"))
check("短名不越界", _school_core("北大") == "北大", _school_core("北大"))

print("\n" + ("✅ 爬虫解析增强验证通过" if not fail else f"❌ 失败：{fail}"))
sys.exit(0 if not fail else 1)
