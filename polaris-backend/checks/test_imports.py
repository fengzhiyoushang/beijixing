"""导入自检：确保所有路由/服务模块可正常加载（语法与导入无误）。"""
import importlib
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODULES = [
    "app.utils.timeutil",
    "app.services.classroom_service",
    "app.services.kaoyan_intel_service",
    "app.routers.classroom",
    "app.routers.kaoyan",
    "app.routers.news",
    "app.routers.system",
    "app.main",
]

bad = 0
for name in MODULES:
    try:
        importlib.import_module(name)
        print(f"✓ {name}")
    except Exception:
        bad += 1
        print(f"✗ {name}")
        traceback.print_exc()

# 路由数量确认
try:
    from app.main import app
    paths = sorted(app.openapi()["paths"])
    print(f"\nOpenAPI 路径数：{len(paths)}")
    for kw in ("/api/v1/classroom/campus-usage", "/api/v1/classroom/semester",
               "/api/v1/classroom/usage-at", "/api/v1/kaoyan/intel", "/api/v1/news/items"):
        print(f"  {'✓' if kw in paths else '✗'} {kw}")
except Exception:
    bad += 1
    traceback.print_exc()

print("\n" + ("✅ 全部模块导入正常" if not bad else f"❌ {bad} 项失败"))
sys.exit(0 if not bad else 1)
