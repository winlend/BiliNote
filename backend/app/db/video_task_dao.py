from app.db.models.video_tasks import VideoTask
from app.db.engine import get_db
from app.utils.logger import get_logger

logger = get_logger(__name__)


# 插入任务
def insert_video_task(video_id: str, platform: str, task_id: str):
    db = next(get_db())
    try:
        task = VideoTask(video_id=video_id, platform=platform, task_id=task_id)
        db.add(task)
        db.commit()
        db.refresh(task)
        logger.info(f"Video task inserted successfully. video_id: {video_id}, platform: {platform}, task_id: {task_id}")
    except Exception as e:
        logger.error(f"Failed to insert video task: {e}")
    finally:
        db.close()


# 查询任务（最新一条）
def get_task_by_video(video_id: str, platform: str):
    db = next(get_db())
    try:
        task = (
            db.query(VideoTask)
            .filter_by(video_id=video_id, platform=platform)
            .order_by(VideoTask.created_at.desc())
            .first()
        )
        if task:
            logger.info(f"Task found for video_id: {video_id} and platform: {platform}")
            return task.task_id
        else:
            logger.info(f"No task found for video_id: {video_id} and platform: {platform}")
            return None
    except Exception as e:
        logger.error(f"Failed to get task by video: {e}")
    finally:
        db.close()


# 删除任务
def delete_task_by_video(video_id: str, platform: str):
    db = next(get_db())
    try:
        tasks = (
            db.query(VideoTask)
            .filter_by(video_id=video_id, platform=platform)
            .all()
        )
        for task in tasks:
            db.delete(task)
        db.commit()
        logger.info(f"Task(s) deleted for video_id: {video_id} and platform: {platform}")
    except Exception as e:
        logger.error(f"Failed to delete task by video: {e}")
    finally:
        db.close()


def list_video_tasks(limit: int = 50, offset: int = 0, platform: str = None,
                     dedupe: bool = True):
    """按创建时间倒序分页列出任务记录，返回 (total, rows)。

    前端任务历史原先只存在浏览器 IndexedDB 里，只能看到「本机本浏览器点过生成」
    的任务；换设备、换浏览器、或由脚本/API 发起的任务都看不到。这个函数给
    /api/task_history 提供数据源（表里只存 video_id/platform/task_id/created_at，
    标题封面等元数据在 note_results/{task_id}.json 里，由路由层补齐）。

    dedupe=True 时同一个视频只保留最新一条：换模型/改风格重跑会为同一个 video_id
    产生多个 task_id，历史列表里不应该出现两条一模一样的标题。表规模很小（每行
    只有四个字段），这里直接取全量后在内存里去重再分页，避免相关子查询的复杂度。
    """
    db = next(get_db())
    try:
        query = db.query(VideoTask)
        if platform:
            query = query.filter_by(platform=platform)

        all_rows = query.order_by(VideoTask.created_at.desc(), VideoTask.id.desc()).all()

        if dedupe:
            latest_by_video = {}
            for row in all_rows:
                key = (row.platform, row.video_id)
                if key not in latest_by_video:  # 已按时间倒序，先到的是最新的
                    latest_by_video[key] = row
            all_rows = list(latest_by_video.values())

        total = len(all_rows)
        page = all_rows[max(offset, 0): max(offset, 0) + max(min(limit, 200), 1)]
        return total, [
            {
                "video_id": row.video_id,
                "platform": row.platform,
                "task_id": row.task_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in page
        ]
    except Exception as e:
        logger.error(f"Failed to list video tasks: {e}")
        return 0, []
    finally:
        db.close()
