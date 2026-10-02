# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

构建：python -m PyInstaller polaris-backend.spec --noconfirm --clean
产物：dist/polaris-backend/polaris-backend(.exe)

关键点：
- uvicorn 的 loops/protocols/lifespan 是运行时字符串导入 → collect_submodules('uvicorn')
- pdfplumber/pdfminer 依赖 cmap 数据、docx 依赖默认模板、certifi 提供 HTTPS CA → collect_all
- 不打包 .env（避免 DB_BACKEND=mysql 混入；桌面版由 Electron 注入环境变量）
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

SRC = Path(SPECPATH)

hiddenimports = []
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('sqlalchemy.dialects.sqlite')
hiddenimports += collect_submodules('app')
hiddenimports += ['pymysql', 'jwt', 'multipart', 'email_validator', 'anyio', 'sniffio', 'greenlet']

datas, binaries = [], []
for pkg in ['pdfplumber', 'pdfminer', 'docx', 'openpyxl', 'cryptography',
            'pydantic', 'pydantic_core', 'certifi', 'email_validator']:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# 兜底：dnspython（email_validator 可选依赖）
try:
    hiddenimports += collect_submodules('dns')
except Exception:
    pass

a = Analysis(
    [str(SRC / 'run_backend.py')],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'alembic', 'redis'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='polaris-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # 便于排障；正式版可改 False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='polaris-backend',
)
