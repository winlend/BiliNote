from abc import ABC
import os

from app.decorators.timeit import timeit
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.provider import ProviderService
from app.transcriber.base import Transcriber
from app.utils.logger import get_logger
from app.utils.openai_client import build_openai_client
import ffmpeg
import tempfile
from dotenv import load_dotenv
load_dotenv()

logger = get_logger(__name__)
MAX_SIZE_MB = 18
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
DEFAULT_GROQ_TRANSCRIBER_MODEL = "whisper-large-v3-turbo"


def compress_audio(input_path: str, target_bitrate='64k') -> str:
    output_fd, output_path = tempfile.mkstemp(suffix=".mp3")  # 临时输出文件
    os.close(output_fd)  # 关闭文件描述符，ffmpeg 会用路径操作
    ffmpeg.input(input_path).output(output_path, audio_bitrate=target_bitrate).run(quiet=True, overwrite_output=True)
    return output_path

class GroqTranscriber(Transcriber, ABC):


    @timeit
    def transcript(self, file_path: str) -> TranscriptResult:
        file_size = os.path.getsize(file_path)
        if file_size > MAX_SIZE_BYTES:
            logger.info(
                f"文件超过 {MAX_SIZE_MB}MB，开始压缩（当前 {round(file_size / (1024 * 1024), 2)}MB）..."
            )
            file_path = compress_audio(file_path)
            logger.info(f"压缩完成，临时路径：{file_path}")
        provider = ProviderService.get_provider_by_id('groq')

        if not provider:
            raise Exception("Groq 供应商未配置,请配置以后使用。")
        # build_openai_client 会校验 api_key 非空（空 key 会抛天书般的
        # `Illegal header value b'Bearer '`），并自动注入全局代理
        client = build_openai_client(
            api_key=provider.get('api_key'),
            base_url=provider.get('base_url'),
            key_label="Groq 转写引擎的 API Key",
        )
        # 转写模型与供应商 chat 模型无关：配置文件 > env > 默认
        try:
            from app.services.transcriber_config_manager import TranscriberConfigManager
            configured = TranscriberConfigManager().get_groq_transcriber_model()
        except Exception:
            configured = None
        model = (
            (configured or os.getenv("GROQ_TRANSCRIBER_MODEL") or DEFAULT_GROQ_TRANSCRIBER_MODEL)
            or ""
        ).strip()
        if not model:
            raise ValueError(
                "Groq 转写模型未配置：请在「音频转写配置」选择模型，或设置环境变量 "
                f"GROQ_TRANSCRIBER_MODEL（例如 {DEFAULT_GROQ_TRANSCRIBER_MODEL}）"
            )
        filename = file_path
        logger.info(f"开始 Groq 音频转写: file={filename}, model={model}")

        try:
            with open(filename, "rb") as file:
                transcription = client.audio.transcriptions.create(
                    file=(filename, file.read()),
                    model=model,
                    response_format="verbose_json",
                )
        except Exception as e:
            logger.error(f"Groq 转写失败 (model={model}): {e}", exc_info=True)
            raise

        logger.info(
            f"Groq 转写完成: language={getattr(transcription, 'language', None)}, "
            f"text_len={len(transcription.text or '')}"
        )
        logger.debug(f"Groq 转写原文预览: {(transcription.text or '')[:200]}")
        segments = []
        full_text = ""

        for seg in transcription.segments:
            text = seg.text.strip()
            full_text += text + " "
            segments.append(TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=text
            ))

        result = TranscriptResult(
            language=transcription.language,
            full_text=full_text.strip(),
            segments=segments,
            raw=transcription.to_dict()
        )
        return result
