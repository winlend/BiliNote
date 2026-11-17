"""从 chat completion 的 message 里统一取正文。

背景：部分 OpenAI 兼容中转会把最终答案放在 `message.reasoning` /
`reasoning_content` 里，`message.content` 返回 None 或空串（实测 cline 中转上的
`deepseek-v4.1-flash` 就是这种形态）。旧代码直接 `response.choices[0].message.content.strip()`，
遇到 None 会抛 AttributeError，整个笔记生成直接失败。

这里做一层取值回退，并把回落情况写进日志——回落意味着拿到的是推理文本，
正文里可能夹着思考过程，需要通过日志及时发现是哪个供应商的返回形态不对。
"""
from __future__ import annotations

from typing import Any, List

from app.utils.logger import get_logger

logger = get_logger(__name__)

_FALLBACK_ATTRS = ("reasoning_content", "reasoning", "thinking", "thinking_content")


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):  # 多模态分段返回
        parts: List[str] = []
        for part in value:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts).strip()
    return str(value).strip()


def message_text(message: Any, *, context: str = "unknown") -> str:
    """取 message 正文：优先 content，空则回退 reasoning 类字段，最终返回空串。"""
    content = _as_text(getattr(message, "content", None))
    if content:
        return content

    for attr in _FALLBACK_ATTRS:
        alt = _as_text(getattr(message, attr, None))
        if alt:
            logger.warning(
                "模型响应缺少 content，回退使用 message.%s（%s）：拿到的是推理文本，"
                "笔记正文可能包含思考过程", attr, context
            )
            return alt

    extra = getattr(message, "model_extra", None)
    if isinstance(extra, dict):
        for key in _FALLBACK_ATTRS:
            alt = _as_text(extra.get(key))
            if alt:
                logger.warning(
                    "模型响应缺少 content，回退使用 model_extra[%s]（%s）", key, context
                )
                return alt

    logger.error("模型响应既没有 content 也没有 reasoning 类字段（%s）", context)
    return ""
