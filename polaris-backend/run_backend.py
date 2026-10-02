"""桌面版后端启动入口：供 Electron 子进程 / PyInstaller 冻结产物调用。

与 app/main.py 的 __main__ 分支不同：
1. 直接传入 app 对象（避免 uvicorn 字符串 "app.main:app" 动态导入在冻结环境失败）；
2. reload=False（reload 会派生子进程，Electron 无法可靠回收）；
3. host/port 由环境变量注入（Electron 动态分配空闲端口）。

用法：
    python run_backend.py                # 默认 127.0.0.1:8000
    HOST=127.0.0.1 PORT=8123 python run_backend.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 保证以脚本或冻结产物运行时都能 import app 包
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
