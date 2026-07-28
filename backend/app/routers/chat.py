from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.services.chat_service import chat as chat_service
from app.services.vector_store import VectorStoreManager, _note_output_dir
from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper as R
import os

logger = get_logger(__name__)

router = APIRouter()

# 索引状态追踪: task_id -> "indexing" | "indexed" | "failed"
_index_status: dict[str, str] = {}
# 最近一次失败原因，供前端展示
_index_errors: dict[str, str] = {}


class IndexRequest(BaseModel):
    task_id: str
    force: Optional[bool] = False


class ChatMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    task_id: str
    question: str
    history: list[ChatMessage] = []
    provider_id: str
    model_name: str


def _do_index(task_id: str):
    """后台执行索引任务。"""
    try:
        _index_status[task_id] = "indexing"
        _index_errors.pop(task_id, None)
        store = VectorStoreManager()
        n = store.index_task(task_id)
        _index_status[task_id] = "indexed"
        logger.info(f"索引完成: {task_id}, chunks={n}")
    except Exception as e:
        _index_status[task_id] = "failed"
        _index_errors[task_id] = str(e)
        logger.error(f"索引失败: {task_id}, {e}", exc_info=True)


@router.post("/chat/index")
def index_task(data: IndexRequest, background_tasks: BackgroundTasks):
    """触发后台索引，立即返回。"""
    task_id = (data.task_id or "").strip()
    if not task_id:
        return R.error(msg="task_id 不能为空")

    if _index_status.get(task_id) == "indexing" and not data.force:
        return R.success(msg="正在索引中", data={"status": "indexing"})

    # 同步校验笔记文件，避免后台静默失败、前端只看到 failed
    note_path = os.path.join(_note_output_dir(), f"{task_id}.json")
    if not os.path.exists(note_path):
        msg = (
            f"笔记文件不存在: {note_path}。"
            f"请确认该任务已成功生成；若修改过「笔记与任务缓存目录」，请用新目录下的任务，或重新生成笔记。"
        )
        _index_status[task_id] = "failed"
        _index_errors[task_id] = msg
        logger.warning(msg)
        return R.error(msg=msg)

    try:
        store = VectorStoreManager()
    except Exception as e:
        msg = str(e)
        _index_status[task_id] = "failed"
        _index_errors[task_id] = msg
        return R.error(msg=msg)

    if not data.force and store.is_indexed(task_id):
        _index_status[task_id] = "indexed"
        _index_errors.pop(task_id, None)
        return R.success(msg="已完成索引", data={"status": "indexed"})

    _index_status[task_id] = "indexing"
    _index_errors.pop(task_id, None)
    background_tasks.add_task(_do_index, task_id)
    return R.success(msg="开始索引", data={"status": "indexing"})


@router.get("/chat/status")
def chat_status(task_id: str):
    """返回索引状态：idle / indexing / indexed / failed。"""
    try:
        status = _index_status.get(task_id)
        error = _index_errors.get(task_id) or ""
        if status:
            return R.success(
                data={
                    "status": status,
                    "indexed": status == "indexed",
                    "error": error if status == "failed" else "",
                }
            )

        store = VectorStoreManager()
        indexed = store.is_indexed(task_id)
        if indexed:
            _index_status[task_id] = "indexed"
        return R.success(
            data={
                "status": "indexed" if indexed else "idle",
                "indexed": indexed,
                "error": "",
            }
        )
    except Exception as e:
        logger.error(f"查询索引状态失败: {e}", exc_info=True)
        return R.success(
            data={
                "status": "failed",
                "indexed": False,
                "error": str(e),
            }
        )


@router.post("/chat/ask")
def ask_question(data: AskRequest):
    """基于笔记内容的 RAG 问答。"""
    try:
        history = [{"role": m.role, "content": m.content} for m in data.history]
        result = chat_service(
            task_id=data.task_id,
            question=data.question,
            history=history,
            provider_id=data.provider_id,
            model_name=data.model_name,
        )
        return R.success(data=result)
    except ValueError as e:
        return R.error(msg=str(e))
    except Exception as e:
        logger.error(f"Chat 问答失败: {e}", exc_info=True)
        return R.error(msg=f"问答失败: {str(e)}")
