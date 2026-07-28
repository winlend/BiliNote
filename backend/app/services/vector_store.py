"""基于 ChromaDB 的笔记向量存储。

桌面安装版注意：
1) 向量库路径走 PathConfigManager：默认 CWD（安装目录）可写则用安装目录旁 vector_db；
   仅不可写时回退 %LOCALAPPDATA%/BiliNote/vector_db
2) PyInstaller 漏打 chromadb.telemetry.product.posthog → 导入前注入 stub / 打包 collect-all
"""
from __future__ import annotations

import json
import os
import re
import sys
import types
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

NOTE_OUTPUT_DIR = os.getenv("NOTE_OUTPUT_DIR", "note_results")
VECTOR_DB_DIR = os.getenv("VECTOR_DB_DIR", "vector_db")

# 在 import chromadb 之前关闭遥测，减少对 posthog 的依赖
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
os.environ.setdefault("CHROMA_ANONYMIZED_TELEMETRY", "False")


def _install_chromadb_telemetry_stubs() -> None:
    """PyInstaller 常漏打 chromadb.telemetry.product.posthog，导入前补空模块。"""
    stubs = [
        "chromadb.telemetry",
        "chromadb.telemetry.product",
        "chromadb.telemetry.product.posthog",
    ]
    for name in stubs:
        if name in sys.modules:
            continue
        # 不预先 stub 已存在的包；仅在真正缺 posthog 时由 _import_chromadb 调用

    if "chromadb.telemetry.product.posthog" in sys.modules:
        return

    # product 包
    if "chromadb.telemetry.product" not in sys.modules:
        product = types.ModuleType("chromadb.telemetry.product")
        product.__path__ = []  # type: ignore[attr-defined]
        sys.modules["chromadb.telemetry.product"] = product

    posthog_mod = types.ModuleType("chromadb.telemetry.product.posthog")

    class _NoopTelemetry:
        def __init__(self, *args, **kwargs):
            pass

        def capture(self, *args, **kwargs):
            return None

        def __getattr__(self, _name):
            def _noop(*args, **kwargs):
                return None

            return _noop

    posthog_mod.Posthog = _NoopTelemetry  # type: ignore[attr-defined]
    posthog_mod.PostHog = _NoopTelemetry  # type: ignore[attr-defined]
    sys.modules["chromadb.telemetry.product.posthog"] = posthog_mod


def _import_chromadb():
    """导入 chromadb；若缺 posthog 子模块则 stub 后重试。"""
    try:
        import chromadb
        from chromadb.config import Settings

        return chromadb, Settings
    except ModuleNotFoundError as e:
        msg = str(e)
        if "posthog" in msg or "telemetry" in msg:
            logger.warning(f"chromadb 遥测模块缺失，使用 stub 重试: {e}")
            _install_chromadb_telemetry_stubs()
            import chromadb
            from chromadb.config import Settings

            return chromadb, Settings
        raise


def _note_output_dir() -> str:
    try:
        from app.services.path_config_manager import get_path_config_manager

        return get_path_config_manager().get_note_output_dir()
    except Exception:
        return os.getenv("NOTE_OUTPUT_DIR", "note_results")


def _is_writable_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".bilinote_write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


def _default_user_vector_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "BiliNote", "vector_db")
    return os.path.join(os.path.expanduser("~"), ".bilinote", "vector_db")


def _vector_db_dir() -> str:
    """向量库目录：设置页 / VECTOR_DB_DIR / 可写默认（用户数据根）。"""
    try:
        from app.services.path_config_manager import get_path_config_manager

        return get_path_config_manager().get_vector_db_dir()
    except Exception:
        raw = (os.getenv("VECTOR_DB_DIR") or "").strip()
        if raw:
            path = raw
        else:
            if sys.platform == "win32":
                base = (
                    os.environ.get("LOCALAPPDATA")
                    or os.environ.get("APPDATA")
                    or os.path.expanduser("~")
                )
                path = os.path.join(base, "BiliNote", "vector_db")
            else:
                path = os.path.join(os.path.expanduser("~"), ".bilinote", "vector_db")
        os.makedirs(path, exist_ok=True)
        return os.path.abspath(path)


def _chunk_markdown(markdown: str) -> list[dict]:
    """按 H2/H3 标题拆分 markdown 为语义块。"""
    sections = re.split(r"(?=^#{2,3}\s)", markdown, flags=re.MULTILINE)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section or len(section) < 30:
            continue
        heading_match = re.match(r"^(#{2,3})\s+(.+)", section)
        title = heading_match.group(2).strip() if heading_match else "intro"
        chunks.append(
            {
                "text": section,
                "metadata": {"source_type": "markdown", "section_title": title},
            }
        )
    return chunks


def _chunk_transcript(segments: list[dict], window_size: int = 15, overlap: int = 3) -> list[dict]:
    """将转录 segments 按滑动窗口分组。"""
    if not segments:
        return []
    chunks = []
    step = max(window_size - overlap, 1)
    for i in range(0, len(segments), step):
        window = segments[i : i + window_size]
        if not window:
            break
        text = "\n".join(f"[{seg.get('start', 0):.0f}s] {seg.get('text', '')}" for seg in window)
        chunks.append(
            {
                "text": text,
                "metadata": {
                    "source_type": "transcript",
                    "start_time": window[0].get("start", 0),
                    "end_time": window[-1].get("end", 0),
                },
            }
        )
    return chunks


def _build_meta_chunk(audio_meta: dict) -> list[dict]:
    """将视频元信息（标题、作者、描述、标签等）构建为可检索的 chunk。"""
    if not audio_meta:
        return []

    raw = audio_meta.get("raw_info", {}) or {}
    parts = []

    title = audio_meta.get("title") or raw.get("title", "")
    if title:
        parts.append(f"视频标题：{title}")

    uploader = raw.get("uploader", "")
    if uploader:
        parts.append(f"视频作者/UP主：{uploader}")

    desc = raw.get("description", "")
    if desc:
        parts.append(f"视频简介：{desc[:500]}")

    tags = raw.get("tags", [])
    if tags and isinstance(tags, list):
        parts.append(f"标签：{', '.join(str(t) for t in tags[:20])}")

    duration = audio_meta.get("duration", 0)
    if duration:
        m, s = divmod(int(duration), 60)
        parts.append(f"视频时长：{m}分{s}秒")

    platform = audio_meta.get("platform", "")
    if platform:
        parts.append(f"平台：{platform}")

    url = raw.get("webpage_url", "")
    if url:
        parts.append(f"链接：{url}")

    if not parts:
        return []

    return [
        {
            "text": "\n".join(parts),
            "metadata": {"source_type": "meta"},
        }
    ]


class VectorStoreManager:
    """基于 ChromaDB 的笔记向量存储管理器。"""

    def __init__(self):
        db_path = _vector_db_dir()
        os.makedirs(db_path, exist_ok=True)
        self._db_path = db_path
        try:
            chromadb, Settings = _import_chromadb()
            self._client = chromadb.PersistentClient(
                path=db_path,
                settings=Settings(anonymized_telemetry=False),
            )
        except ModuleNotFoundError as e:
            logger.error(f"chromadb 未安装或不完整: {e}", exc_info=True)
            raise RuntimeError(
                "未正确安装 chromadb（或桌面打包时未打入依赖）。"
                "开发环境请: pip install 'chromadb>=0.5.0'；"
                "安装版请使用包含 chromadb collect-all 的新包重新 publish。"
                f" 详情: {e}"
            ) from e
        except Exception as e:
            logger.error(f"初始化 ChromaDB 失败 path={db_path}: {e}", exc_info=True)
            hint = ""
            err = str(e)
            if "posthog" in err:
                hint = (
                    " 这通常是安装包漏打了 chromadb 遥测模块；"
                    "请更新/重装用新 build.bat 打的版本，或把 VECTOR_DB_DIR 设到可写目录后重试。"
                )
            if "Permission" in err or "Access is denied" in err:
                hint += f" 目录可能不可写，已尝试使用: {db_path}。"
            raise RuntimeError(
                f"向量数据库初始化失败（{db_path}）。请确认 chromadb 完整且目录可写。{hint} 详情: {e}"
            ) from e

    def _collection_name(self, task_id: str) -> str:
        """ChromaDB collection 名称：直接使用 task_id（UUID 格式合法）。"""
        return task_id

    def index_task(self, task_id: str) -> int:
        """读取笔记结果并建立向量索引。成功返回 chunk 数；失败抛异常。"""
        result_path = os.path.join(_note_output_dir(), f"{task_id}.json")
        if not os.path.exists(result_path):
            raise FileNotFoundError(
                f"笔记文件不存在，无法索引: {result_path}。"
                f"请确认任务已成功生成；若改过「笔记目录」，需用新目录下的任务。"
            )

        with open(result_path, "r", encoding="utf-8") as f:
            note_data = json.load(f)

        markdown = note_data.get("markdown", "") or ""
        if isinstance(markdown, list):
            parts = []
            for item in markdown:
                if isinstance(item, dict):
                    parts.append(item.get("content") or "")
                elif isinstance(item, str):
                    parts.append(item)
            markdown = "\n\n".join(p for p in parts if p)
        transcript = note_data.get("transcript", {}) or {}
        if not isinstance(transcript, dict):
            transcript = {}
        segments = transcript.get("segments", []) or []

        audio_meta = note_data.get("audio_meta", {}) or {}

        meta_chunks = _build_meta_chunk(audio_meta)
        md_chunks = _chunk_markdown(markdown)
        tr_chunks = _chunk_transcript(segments)
        all_chunks = meta_chunks + md_chunks + tr_chunks

        if not all_chunks:
            raise ValueError(
                f"笔记内容过短或为空，无法建立索引: {task_id}。"
                f"请确认 markdown/转写至少有一段可用文本。"
            )

        col_name = self._collection_name(task_id)

        try:
            self._client.delete_collection(col_name)
        except Exception:
            pass

        try:
            collection = self._client.create_collection(
                name=col_name,
                metadata={"hnsw:space": "cosine"},
            )

            documents = [c["text"] for c in all_chunks]
            metadatas = [c["metadata"] for c in all_chunks]
            ids = [f"{task_id}_{i}" for i in range(len(all_chunks))]

            collection.add(documents=documents, metadatas=metadatas, ids=ids)
        except Exception as e:
            logger.error(f"写入向量索引失败 task_id={task_id}: {e}", exc_info=True)
            try:
                self._client.delete_collection(col_name)
            except Exception:
                pass
            raise RuntimeError(
                f"建立向量索引失败: {e}。"
                f"常见原因：首次需下载 Embedding 模型（需联网）、chromadb 损坏、磁盘满。"
            ) from e

        logger.info(
            f"向量索引完成: task_id={task_id}, chunks={len(all_chunks)}, db={self._db_path}"
        )
        return len(all_chunks)

    def _parse_results(self, results: dict) -> list[dict]:
        """将 ChromaDB query 结果转换为 chunk 列表。"""
        chunks = []
        if not results or not results.get("documents") or not results["documents"][0]:
            return chunks
        for i in range(len(results["documents"][0])):
            chunks.append(
                {
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                }
            )
        return chunks

    def query(self, task_id: str, query_text: str, n_results: int = 6) -> list[dict]:
        """
        按固定配额从各来源检索：meta 1 条、markdown 2 条、transcript 3 条，
        确保三种来源都被召回。
        """
        col_name = self._collection_name(task_id)
        try:
            collection = self._client.get_collection(col_name)
        except Exception:
            logger.warning(f"Collection 不存在: {col_name}")
            return []

        all_chunks = []
        quotas = {"meta": 1, "markdown": 2, "transcript": 3}

        for source_type, quota in quotas.items():
            try:
                results = collection.query(
                    query_texts=[query_text],
                    n_results=quota,
                    where={"source_type": source_type},
                )
                all_chunks.extend(self._parse_results(results))
            except Exception:
                pass

        return all_chunks

    def delete_index(self, task_id: str) -> None:
        """删除指定任务的向量索引。"""
        col_name = self._collection_name(task_id)
        try:
            self._client.delete_collection(col_name)
            logger.info(f"已删除向量索引: {task_id}")
        except Exception:
            pass

    def is_indexed(self, task_id: str) -> bool:
        """检查指定任务是否已建立完整索引（含 meta 信息）。"""
        col_name = self._collection_name(task_id)
        try:
            col = self._client.get_collection(col_name)
            if col.count() == 0:
                return False
            meta = col.get(where={"source_type": "meta"}, limit=1)
            return len(meta["ids"]) > 0
        except Exception:
            return False
