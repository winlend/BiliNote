import os
import subprocess
from app.utils.env_loader import load_app_dotenv
from app.utils.logger import get_logger

logger = get_logger(__name__)
load_app_dotenv()

# 缓存探测结果：桌面端 /sys_health 每 5s 轮询一次，若每次都
# 改 PATH + 跑 `ffmpeg -version` + 打 INFO，app.log 会被刷爆。
# 进程生命周期内 PATH/安装状态基本不变，探测一次即可。
_ffmpeg_checked: bool = False
_ffmpeg_available: bool = False
_ffmpeg_path_applied: bool = False


def _apply_ffmpeg_path_once() -> None:
    """把 FFMPEG_BIN_PATH 或系统 PATH 里的 ffmpeg 目录前置到 PATH，只做一次。"""
    global _ffmpeg_path_applied
    if _ffmpeg_path_applied:
        return
    _ffmpeg_path_applied = True

    # 设置页 paths.json 优先于环境变量
    try:
        from app.services.path_config_manager import get_path_config_manager
        ffmpeg_bin_path = get_path_config_manager().get_ffmpeg_bin_path() or os.getenv("FFMPEG_BIN_PATH")
    except Exception:
        ffmpeg_bin_path = os.getenv("FFMPEG_BIN_PATH")
    if ffmpeg_bin_path and os.path.isdir(ffmpeg_bin_path):
        os.environ["PATH"] = ffmpeg_bin_path + os.pathsep + os.environ.get("PATH", "")
        os.environ["FFMPEG_BIN_PATH"] = ffmpeg_bin_path
        logger.info(f"使用 FFMPEG_BIN_PATH: {ffmpeg_bin_path}")
        return

    # 遍历系统 PATH 寻找 ffmpeg（Windows 优先 .exe；其它平台裸 ffmpeg）
    system_path = os.environ.get("PATH", "")
    for path_dir in system_path.split(os.pathsep):
        if not path_dir:
            continue
        candidates = (
            os.path.join(path_dir, "ffmpeg.exe"),
            os.path.join(path_dir, "ffmpeg"),
        )
        if any(os.path.isfile(p) for p in candidates):
            os.environ["PATH"] = path_dir + os.pathsep + system_path
            logger.info(f"在系统 PATH 中找到 ffmpeg: {path_dir}")
            return

    logger.debug("未在 FFMPEG_BIN_PATH / PATH 中定位到 ffmpeg 目录，将直接尝试调用")


def check_ffmpeg_exists(force: bool = False) -> bool:
    """检查 ffmpeg 是否可用。默认缓存结果，避免健康检查反复探测。

    force=True 时强制重新探测（例如用户刚装完 ffmpeg 想立刻刷新状态）。
    """
    global _ffmpeg_checked, _ffmpeg_available
    if _ffmpeg_checked and not force:
        return _ffmpeg_available

    _apply_ffmpeg_path_once()
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        _ffmpeg_available = True
        # 只在首次成功时打 INFO；后续命中缓存完全静默
        if not _ffmpeg_checked:
            logger.info("ffmpeg 已安装")
    except (FileNotFoundError, OSError, subprocess.CalledProcessError):
        _ffmpeg_available = False
        if not _ffmpeg_checked:
            logger.warning("ffmpeg 未安装或不可用")
        else:
            logger.debug("ffmpeg 重新探测仍不可用")

    _ffmpeg_checked = True
    return _ffmpeg_available


def ensure_ffmpeg_or_raise():
    """
    校验 ffmpeg 是否可用，否则抛出异常并提示安装方式。
    """
    if not check_ffmpeg_exists():
        # 错误只在真正需要 ffmpeg 的业务路径上抛；健康检查应优先用 check_ffmpeg_exists
        logger.error("未检测到 ffmpeg，请先安装后再使用本功能。")
        raise EnvironmentError(
            " 未检测到 ffmpeg，请先安装后再使用本功能。\n"
            "👉 下载地址：https://ffmpeg.org/download.html\n"
            "🪟 Windows 推荐：https://www.gyan.dev/ffmpeg/builds/\n"
            "💡 如果你已安装，请将其路径写入 `.env` 文件，例如：\n"
            "FFMPEG_BIN_PATH=/your/custom/ffmpeg/bin"
        )
