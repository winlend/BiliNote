"""GPT 分块进度回调与清空缓存单测。"""
from app.models.gpt_model import GPTSource
from app.gpt.universal_gpt import UniversalGPT
from app.models.transcriber_model import TranscriptSegment
from app.services.note import clear_task_pipeline_cache, _cache_flags, get_note_output_dir


def test_gpt_source_accepts_progress_callback():
    calls = []

    def cb(**kwargs):
        calls.append(kwargs)

    src = GPTSource(
        segment=[TranscriptSegment(start=0, end=1, text="hello")],
        title="t",
        tags="",
        progress_callback=cb,
    )
    UniversalGPT._emit_progress(
        src, phase="summarize", current=1, total=2, message="AI 总结中（第 1/2 段）…"
    )
    assert len(calls) == 1
    assert calls[0]["current"] == 1
    assert calls[0]["total"] == 2
    assert "1/2" in calls[0]["message"]


def test_progress_callback_exception_swallowed():
    def bad(**_kwargs):
        raise RuntimeError("boom")

    src = GPTSource(
        segment=[],
        title="t",
        tags="",
        progress_callback=bad,
    )
    # 不应抛出
    UniversalGPT._emit_progress(src, phase="merge", current=1, total=1, message="x")


def test_clear_task_pipeline_cache_and_flags(tmp_path, monkeypatch):
    # 指向临时目录，避免污染真实 note_results
    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    # path manager 可能仍读 json；直接 patch get_note_output_dir
    import app.services.note as note_mod

    monkeypatch.setattr(note_mod, "get_note_output_dir", lambda: tmp_path)

    tid = "task-clear-test"
    (tmp_path / f"{tid}_audio.json").write_text("{}", encoding="utf-8")
    (tmp_path / f"{tid}_transcript.json").write_text("{}", encoding="utf-8")
    (tmp_path / f"{tid}_markdown.md").write_text("# hi", encoding="utf-8")
    (tmp_path / f"{tid}.gpt.checkpoint.json").write_text("{}", encoding="utf-8")
    (tmp_path / f"{tid}.json").write_text('{"keep": true}', encoding="utf-8")

    flags = note_mod._cache_flags(tid)
    assert flags["audio"] and flags["transcript"] and flags["markdown"] and flags["gpt_checkpoint"]

    result = note_mod.clear_task_pipeline_cache(tid)
    assert f"{tid}_audio.json" in result["deleted"]
    assert not (tmp_path / f"{tid}_audio.json").exists()
    assert not (tmp_path / f"{tid}.gpt.checkpoint.json").exists()
    # 最终成功文件应保留
    assert (tmp_path / f"{tid}.json").exists()
