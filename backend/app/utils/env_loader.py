"""统一 .env 加载：适配源码、Docker、Tauri/PyInstaller 桌面端。

桌面 sidecar 的 CWD 往往是主程序目录，而打包进去的 .env 可能在
_internal/ 或 exe 旁。多路径探测避免 GROQ_TRANSCRIBER_MODEL 等读不到。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

_loaded_from: Optional[str] = None


def load_app_dotenv(*, override: bool = False) -> Optional[str]:
    """按优先级加载第一个存在的 .env，返回实际路径；都没有则 fallback 默认行为。"""
    global _loaded_from
    if _loaded_from is not None and not override:
        return _loaded_from

    candidates: List[str] = []
    cwd = os.getcwd()
    candidates.append(os.path.join(cwd, ".env"))

    # backend/ 或 main 所在目录
    here = Path(__file__).resolve()
    # app/utils/env_loader.py → backend/
    backend_dir = here.parents[2] if len(here.parents) >= 2 else here.parent
    candidates.append(str(backend_dir / ".env"))
    # 项目根
    candidates.append(str(backend_dir.parent / ".env"))

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(str(exe_dir / ".env"))
        candidates.append(str(exe_dir / "_internal" / ".env"))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(str(Path(meipass) / ".env"))

    seen = set()
    for path in candidates:
        normalized = os.path.normpath(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(normalized):
            load_dotenv(normalized, override=override)
            _loaded_from = normalized
            return _loaded_from

    load_dotenv(override=override)
    _loaded_from = ""
    return _loaded_from


def get_logs_dir() -> str:
    """日志目录：优先 PathConfigManager（可写用户目录），否则 CWD/logs。"""
    try:
        from app.services.path_config_manager import get_path_config_manager

        return get_path_config_manager().get_logs_dir()
    except Exception:
        p = Path(os.getcwd()) / "logs"
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            p = Path.home() / ".bilinote" / "logs"
            p.mkdir(parents=True, exist_ok=True)
        return str(p.resolve())
