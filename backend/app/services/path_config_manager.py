"""路径配置：笔记 / 下载 / 截图 / 向量库 / FFmpeg。

默认策略（与历史桌面行为一致，并兼顾权限）：
- 未单独配置时：优先 CWD（安装目录 / 开发 backend 目录）下的相对子目录
  例如 D:\\Program Files\\BiliNote\\note_results —— 只要该处可写
- 仅当 CWD 不可写时，才回退到用户数据根：
  Windows %LOCALAPPDATA%\\BiliNote\\...  或  ~/.bilinote/...
- 设置页可覆盖为任意**可写**绝对路径；不可写则保存失败并提示

优先级：config/paths.json > 环境变量 > 上述默认
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_NOTE_OUTPUT_DIR = "note_results"
DEFAULT_DATA_DIR = "data"
DEFAULT_OUT_DIR = "static/screenshots"
DEFAULT_VECTOR_DB_DIR = "vector_db"


def get_user_data_root() -> Path:
    """跨平台用户数据根目录（始终应可写）。"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "BiliNote"
    return Path.home() / ".bilinote"


def _is_program_files_path(path: Path) -> bool:
    try:
        resolved = str(path.resolve()).lower().replace("/", "\\")
    except Exception:
        resolved = str(path).lower().replace("/", "\\")
    markers = (
        "\\program files\\",
        "\\program files (x86)\\",
        "/program files/",
        "/program files (x86)/",
    )
    return any(m in resolved for m in markers)


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".bilinote_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def default_data_root() -> Path:
    """未配置时的数据根：CWD（安装目录）可写则用 CWD，否则用户目录。

    与历史行为对齐：sidecar current_dir 即安装目录时，缓存默认就在安装目录旁。
    Program Files 若当前用户可写（你机器上常见），继续用安装目录，不强制迁到 AppData。
    """
    cwd = Path.cwd()
    if _is_writable_dir(cwd):
        return cwd
    root = get_user_data_root()
    root.mkdir(parents=True, exist_ok=True)
    logger.info(f"CWD 不可写，数据根回退到用户目录: {cwd} -> {root}")
    return root


class PathConfigManager:
    def __init__(self, filepath: str = "config/paths.json"):
        # config 本身也尽量放可写处：优先 CWD/config，不可写则用户目录
        self.path = self._resolve_config_file(filepath)

    @staticmethod
    def _resolve_config_file(filepath: str) -> Path:
        p = Path(filepath)
        if not p.is_absolute():
            cwd_cfg = Path.cwd() / p
            if _is_writable_dir(cwd_cfg.parent):
                return cwd_cfg
            user_cfg = get_user_data_root() / p
            user_cfg.parent.mkdir(parents=True, exist_ok=True)
            return user_cfg
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                import json

                return json.load(f) or {}
        except Exception:
            return {}

    def _write(self, data: Dict[str, Any]) -> None:
        import json

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _resolve_path(self, raw: Optional[str], default_name: str) -> str:
        """解析配置/env/默认目录名；优先保持安装目录，不可写再回退。"""
        value = (raw or "").strip()
        if value:
            p = Path(value).expanduser()
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            else:
                p = p.resolve()
        else:
            # 默认：安装目录（CWD）下的子目录，与历史一致
            p = (default_data_root() / default_name).resolve()

        if _is_writable_dir(p):
            return str(p)

        # 显式配置了路径但不可写：仍尝试用户目录回退，避免直接崩
        fallback = (get_user_data_root() / default_name).resolve()
        if _is_writable_dir(fallback):
            logger.warning(f"目录不可写，回退: {p} -> {fallback}")
            return str(fallback)
        raise RuntimeError(f"目录不可写且无法回退: {p}")

    def get_note_output_dir(self) -> str:
        data = self._read()
        raw = data.get("note_output_dir") or os.getenv("NOTE_OUTPUT_DIR")
        return self._resolve_path(raw, DEFAULT_NOTE_OUTPUT_DIR)

    def get_data_dir(self) -> str:
        data = self._read()
        raw = data.get("data_dir") or os.getenv("DATA_DIR")
        return self._resolve_path(raw, DEFAULT_DATA_DIR)

    def get_out_dir(self) -> str:
        data = self._read()
        raw = data.get("out_dir") or os.getenv("OUT_DIR")
        return self._resolve_path(raw, DEFAULT_OUT_DIR)

    def get_vector_db_dir(self) -> str:
        data = self._read()
        raw = data.get("vector_db_dir") or os.getenv("VECTOR_DB_DIR")
        return self._resolve_path(raw, DEFAULT_VECTOR_DB_DIR)

    def get_logs_dir(self) -> str:
        data = self._read()
        raw = data.get("logs_dir") or os.getenv("LOGS_DIR")
        return self._resolve_path(raw, "logs")

    def get_ffmpeg_bin_path(self) -> str:
        data = self._read()
        raw = data.get("ffmpeg_bin_path")
        if raw is None or str(raw).strip() == "":
            return (os.getenv("FFMPEG_BIN_PATH") or "").strip()
        return str(raw).strip()

    def get_suggested_layout(self) -> Dict[str, str]:
        """给设置页展示的推荐布局（用户数据根下）。"""
        root = get_user_data_root()
        return {
            "data_root": str(root),
            "note_output_dir": str(root / DEFAULT_NOTE_OUTPUT_DIR),
            "data_dir": str(root / DEFAULT_DATA_DIR),
            "vector_db_dir": str(root / DEFAULT_VECTOR_DB_DIR),
            "logs_dir": str(root / "logs"),
            "out_dir": str(root / "static" / "screenshots"),
        }

    def get_config(self) -> Dict[str, Any]:
        data = self._read()
        note = self.get_note_output_dir()
        data_dir = self.get_data_dir()
        out_dir = self.get_out_dir()
        vector_db = self.get_vector_db_dir()
        logs_dir = self.get_logs_dir()
        ffmpeg = self.get_ffmpeg_bin_path()
        db_url = os.getenv("DATABASE_URL", "sqlite:///bili_note.db")
        suggested = self.get_suggested_layout()
        cwd = str(Path.cwd())
        return {
            "note_output_dir": data.get("note_output_dir") or "",
            "data_dir": data.get("data_dir") or "",
            "out_dir": data.get("out_dir") or "",
            "vector_db_dir": data.get("vector_db_dir") or "",
            "logs_dir": data.get("logs_dir") or "",
            "ffmpeg_bin_path": data.get("ffmpeg_bin_path")
            if data.get("ffmpeg_bin_path") is not None
            else "",
            "config_file": str(self.path.resolve()),
            "suggested": suggested,
            "effective": {
                "note_output_dir": note,
                "data_dir": data_dir,
                "out_dir": out_dir,
                "vector_db_dir": vector_db,
                "ffmpeg_bin_path": ffmpeg,
                "database_url": db_url,
                "logs_dir": logs_dir,
                "cwd": cwd,
                "user_data_root": suggested["data_root"],
                "cwd_looks_like_program_files": _is_program_files_path(Path.cwd()),
            },
        }

    def apply_recommended_layout(self) -> Dict[str, Any]:
        """一键写入推荐可写布局（用户数据根）。不自动迁移旧文件。"""
        s = self.get_suggested_layout()
        return self.update_config(
            note_output_dir=s["note_output_dir"],
            data_dir=s["data_dir"],
            out_dir=s["out_dir"],
            vector_db_dir=s["vector_db_dir"],
            logs_dir=s["logs_dir"],
        )

    def update_config(
        self,
        note_output_dir: Optional[str] = None,
        data_dir: Optional[str] = None,
        out_dir: Optional[str] = None,
        vector_db_dir: Optional[str] = None,
        logs_dir: Optional[str] = None,
        ffmpeg_bin_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = self._read()

        def _save_dir(key: str, value: Optional[str]) -> None:
            if value is None:
                return
            value = value.strip()
            if not value:
                data.pop(key, None)
                return
            p = Path(value).expanduser()
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            else:
                p = p.resolve()
            if not _is_writable_dir(p):
                extra = ""
                if _is_program_files_path(p):
                    extra = (
                        f" 若在 Program Files 下无权限，可改用安装目录旁其它可写盘，"
                        f"或 {get_user_data_root()} ，或点击「使用推荐可写目录」。"
                    )
                raise ValueError(f"目录不可用或不可写: {p}.{extra}")
            if _is_program_files_path(p):
                logger.info(f"使用 Program Files 下可写路径（当前用户可写）: {p}")
            data[key] = str(p)

        _save_dir("note_output_dir", note_output_dir)
        _save_dir("data_dir", data_dir)
        _save_dir("out_dir", out_dir)
        _save_dir("vector_db_dir", vector_db_dir)
        _save_dir("logs_dir", logs_dir)

        if ffmpeg_bin_path is not None:
            fb = ffmpeg_bin_path.strip()
            if not fb:
                data.pop("ffmpeg_bin_path", None)
            else:
                p = Path(fb).expanduser()
                if p.is_file():
                    p = p.parent
                if not p.is_dir():
                    raise ValueError(f"FFmpeg 目录不存在: {fb}")
                data["ffmpeg_bin_path"] = str(p.resolve())

        self._write(data)
        # 同步环境变量，便于同进程内 vector_store / 其它模块立刻读到
        cfg = self.get_config()
        eff = cfg["effective"]
        os.environ["NOTE_OUTPUT_DIR"] = eff["note_output_dir"]
        os.environ["DATA_DIR"] = eff["data_dir"]
        os.environ["OUT_DIR"] = eff["out_dir"]
        os.environ["VECTOR_DB_DIR"] = eff["vector_db_dir"]
        os.environ["LOGS_DIR"] = eff["logs_dir"]
        logger.info(f"路径配置已更新: file={self.path}, data={data}")
        return cfg


_path_config_manager: Optional[PathConfigManager] = None


def get_path_config_manager() -> PathConfigManager:
    global _path_config_manager
    if _path_config_manager is None:
        _path_config_manager = PathConfigManager()
    return _path_config_manager
