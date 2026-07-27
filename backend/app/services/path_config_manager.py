"""路径配置：笔记缓存 / 下载目录 / FFmpeg，支持设置页动态修改。

优先级：config/paths.json 非空项 > 环境变量 > 代码默认值。
保存时解析为绝对路径，避免桌面端 CWD 漂移。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_NOTE_OUTPUT_DIR = "note_results"
DEFAULT_DATA_DIR = "data"
DEFAULT_OUT_DIR = "./static/screenshots"


class PathConfigManager:
    def __init__(self, filepath: str = "config/paths.json"):
        self.path = Path(filepath)
        self.path.parent.mkdir(parents=True, exist_ok=True)

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
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _resolve(raw: Optional[str], fallback: str) -> str:
        value = (raw or "").strip() or fallback
        p = Path(value).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        return str(p)

    def get_note_output_dir(self) -> str:
        data = self._read()
        raw = data.get("note_output_dir") or os.getenv("NOTE_OUTPUT_DIR") or DEFAULT_NOTE_OUTPUT_DIR
        path = self._resolve(raw, DEFAULT_NOTE_OUTPUT_DIR)
        Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def get_data_dir(self) -> str:
        data = self._read()
        raw = data.get("data_dir") or os.getenv("DATA_DIR") or DEFAULT_DATA_DIR
        path = self._resolve(raw, DEFAULT_DATA_DIR)
        Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def get_out_dir(self) -> str:
        data = self._read()
        raw = data.get("out_dir") or os.getenv("OUT_DIR") or DEFAULT_OUT_DIR
        path = self._resolve(raw, DEFAULT_OUT_DIR)
        Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def get_ffmpeg_bin_path(self) -> str:
        data = self._read()
        raw = data.get("ffmpeg_bin_path")
        if raw is None or str(raw).strip() == "":
            return (os.getenv("FFMPEG_BIN_PATH") or "").strip()
        return str(raw).strip()

    def get_config(self) -> Dict[str, Any]:
        """返回配置原文 + 当前生效的绝对路径（给设置页展示）。"""
        data = self._read()
        note = self.get_note_output_dir()
        data_dir = self.get_data_dir()
        out_dir = self.get_out_dir()
        ffmpeg = self.get_ffmpeg_bin_path()
        db_url = os.getenv("DATABASE_URL", "sqlite:///bili_note.db")
        return {
            "note_output_dir": data.get("note_output_dir") or "",
            "data_dir": data.get("data_dir") or "",
            "out_dir": data.get("out_dir") or "",
            "ffmpeg_bin_path": data.get("ffmpeg_bin_path") if data.get("ffmpeg_bin_path") is not None else "",
            "effective": {
                "note_output_dir": note,
                "data_dir": data_dir,
                "out_dir": out_dir,
                "ffmpeg_bin_path": ffmpeg,
                "database_url": db_url,
                "cwd": str(Path.cwd()),
            },
        }

    def update_config(
        self,
        note_output_dir: Optional[str] = None,
        data_dir: Optional[str] = None,
        out_dir: Optional[str] = None,
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
            resolved = self._resolve(value, value)
            try:
                Path(resolved).mkdir(parents=True, exist_ok=True)
                # 可写探测
                probe = Path(resolved) / ".bilinote_write_test"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
            except Exception as e:
                raise ValueError(f"目录不可用或不可写: {resolved} ({e})")
            data[key] = resolved

        _save_dir("note_output_dir", note_output_dir)
        _save_dir("data_dir", data_dir)
        _save_dir("out_dir", out_dir)

        if ffmpeg_bin_path is not None:
            fb = ffmpeg_bin_path.strip()
            if not fb:
                data.pop("ffmpeg_bin_path", None)
            else:
                p = Path(fb).expanduser()
                if p.is_file():
                    # 用户可能填到 ffmpeg.exe
                    p = p.parent
                if not p.is_dir():
                    raise ValueError(f"FFmpeg 目录不存在: {fb}")
                data["ffmpeg_bin_path"] = str(p.resolve())

        self._write(data)
        logger.info(f"路径配置已更新: {data}")
        return self.get_config()


_path_config_manager: Optional[PathConfigManager] = None


def get_path_config_manager() -> PathConfigManager:
    global _path_config_manager
    if _path_config_manager is None:
        _path_config_manager = PathConfigManager()
    return _path_config_manager
