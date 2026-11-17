"""抖音作者作品批量生成笔记。

参数已按「方案 A」固化，可直接改文件顶部的 CONFIG：
    style=tutorial, format=[summary,toc,screenshot],
    video_understanding=True, video_interval=2, grid_size=[2,2]

三种模式：
    # 1) 只验证链接/作品可解析，不碰后端
    python tools/batch_douyin_notes.py --list backend/data/_post_list_items.json --verify-only

    # 2) 建任务 + 轮询到完成（后端需已启动，端口默认 8483）
    python tools/batch_douyin_notes.py --list backend/data/_post_list_items.json \
        --provider-id <PROVIDER_ID> --model <MODEL_NAME>

    # 3) 断点续跑：重复执行会自动跳过已完成的条目（读 batch_state.json）

前置条件（缺一不可）：
    * 后端已启动：http://127.0.0.1:8483
    * 「模型供应商」里已配置 provider，且所选模型支持图片输入（video_understanding 会送图）
    * 转写引擎可用（默认 fast-whisper，首次会下载 tiny 模型）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# 只做批量编排，不需要 FastAPI 应用的初始化副作用；注册一个命名空间包，
# 让 `from app.downloaders...` 直接加载子模块而不执行 app/__init__.py
# （后者会连带导入 routers → transcriber → faster_whisper 等重依赖）。
if "app" not in sys.modules:
    import types

    _pkg = types.ModuleType("app")
    _pkg.__path__ = [os.path.join(BACKEND, "app")]
    sys.modules["app"] = _pkg

CONFIG = {
    "platform": "douyin",
    "quality": "fast",          # fast | medium | slow
    "style": "tutorial",
    "format": ["summary", "toc", "screenshot"],
    "video_understanding": True,
    "video_interval": 2,
    "grid_size": [2, 2],
}

NOTE_OUTPUT_DIR = os.path.join(BACKEND, "note_results")
STATE_PATH = os.path.join(NOTE_OUTPUT_DIR, "batch_state.json")


# ----------------------------------------------------------------------------- 列表


def load_items(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    out = []
    for it in items:
        aid = str(it.get("aweme_id") or "").strip()
        if not aid.isdigit():
            continue
        out.append({
            "aweme_id": aid,
            "title": (it.get("title") or it.get("alt") or "")[:80],
            "pinned": bool(it.get("pinned")),
            "url": it.get("url") or f"https://www.douyin.com/video/{aid}",
        })
    # 去重，保持顺序
    seen, uniq = set(), []
    for it in out:
        if it["aweme_id"] in seen:
            continue
        seen.add(it["aweme_id"])
        uniq.append(it)
    return uniq


# ----------------------------------------------------------------------------- 状态


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"updated_at": None, "tasks": {}}


def save_state(state: dict) -> None:
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------------- 验证模式


def verify_only(items: list[dict]) -> int:
    from app.downloaders.douyin_downloader import DouyinDownloader

    dy = DouyinDownloader()
    bad = 0
    for i, it in enumerate(items, 1):
        try:
            info = dy.fetch_video_info(it["url"])["aweme_detail"]
            meta = dy._build_meta(info)
            kind = "图文" if info.get("images") else "视频"
            print(f"[{i}/{len(items)}] OK  {it['aweme_id']}  {kind}  "
                  f"{meta['duration']:.1f}s  {meta['title'][:40]}", flush=True)
            it["verified"] = {
                "kind": kind,
                "duration": meta["duration"],
                "title": meta["title"],
                "has_video": bool(meta["video_url"]),
                "has_music": bool(meta["music_url"]),
            }
        except Exception as e:
            bad += 1
            print(f"[{i}/{len(items)}] FAIL {it['aweme_id']}  {type(e).__name__}: {e}", flush=True)
            it["verified"] = {"error": str(e)[:200]}
        time.sleep(1.5)
    out = os.path.join(NOTE_OUTPUT_DIR, "batch_verify.json")
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"\n验证完成：{len(items) - bad}/{len(items)} 可解析，明细 {out}")
    return 0 if bad == 0 else 1


# ----------------------------------------------------------------------------- 任务模式


def api(session, method: str, base: str, path: str, **kwargs):
    import requests

    url = base.rstrip("/") + path
    resp = session.request(method, url, timeout=kwargs.pop("timeout", 60), **kwargs)
    resp.raise_for_status()
    return resp.json()


def pick_model(session, base: str, provider_id: str | None, model: str | None):
    if provider_id and model:
        return provider_id, model
    providers = api(session, "GET", base, "/api/get_all_providers")
    plist = providers.get("data") or providers.get("providers") or []
    if not plist:
        raise SystemExit("后端没有任何 provider，请先在前端「模型供应商」里配置并填入 API Key")
    pid = provider_id or str(plist[0].get("id"))
    models = api(session, "GET", base, f"/api/model_list/{pid}")
    mlist = models.get("data") or models.get("models") or []
    names = [m.get("model_name") or m.get("name") for m in mlist if isinstance(m, dict)]
    names = [n for n in names if n]
    if model:
        return pid, model
    if not names:
        raise SystemExit(f"provider {pid} 下没有可用模型，请在前端为它添加模型")
    return pid, names[0]


def submit_and_wait(session, base: str, item: dict, pid: str, model: str,
                    timeout_s: int, poll_s: int) -> dict:
    payload = {
        "video_url": item["url"],
        "platform": CONFIG["platform"],
        "quality": CONFIG["quality"],
        "model_name": model,
        "provider_id": pid,
        "style": CONFIG["style"],
        "format": CONFIG["format"],
        "video_understanding": CONFIG["video_understanding"],
        "video_interval": CONFIG["video_interval"],
        "grid_size": CONFIG["grid_size"],
    }
    res = api(session, "POST", base, "/api/generate_note", json=payload)
    task_id = (res.get("data") or {}).get("task_id")
    if not task_id:
        return {"status": "failed", "error": f"未拿到 task_id: {res}"}

    print(f"    task_id={task_id}，轮询中…", flush=True)
    deadline = time.time() + timeout_s
    status = "unknown"
    while time.time() < deadline:
        time.sleep(poll_s)
        try:
            st = api(session, "GET", base, f"/api/task_status/{task_id}")
        except Exception as e:
            print(f"    轮询异常：{e}", flush=True)
            continue
        data = st.get("data") or {}
        status = str(data.get("status") or "").upper()
        phase = data.get("phase") or ""
        print(f"    [{datetime.now().strftime('%H:%M:%S')}] status={status} phase={phase}", flush=True)
        if status in ("SUCCESS", "FAILED"):
            return {"status": status.lower(), "task_id": task_id,
                    "result": data.get("result"), "message": data.get("message")}
    return {"status": "timeout", "task_id": task_id}


def run_tasks(items: list[dict], base: str, provider_id: str | None,
              model: str | None, timeout_s: int, poll_s: int, limit: int | None) -> int:
    import requests

    session = requests.Session()
    pid, mname = pick_model(session, base, provider_id, model)
    print(f"使用 provider={pid} model={mname}", flush=True)
    print(f"参数：style={CONFIG['style']} format={CONFIG['format']} "
          f"video_understanding={CONFIG['video_understanding']} "
          f"interval={CONFIG['video_interval']} grid={CONFIG['grid_size']}", flush=True)

    state = load_state()
    todo = [it for it in items if state["tasks"].get(it["aweme_id"], {}).get("status") != "success"]
    if limit:
        todo = todo[:limit]
    print(f"待处理 {len(todo)}/{len(items)} 条\n", flush=True)

    ok = 0
    for i, it in enumerate(todo, 1):
        print(f"({i}/{len(todo)}) {it['aweme_id']}  {it['title'][:40]}", flush=True)
        try:
            res = submit_and_wait(session, base, it, pid, mname, timeout_s, poll_s)
        except Exception as e:
            res = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        state["tasks"][it["aweme_id"]] = {**res, "title": it["title"], "url": it["url"],
                                          "finished_at": datetime.now().isoformat(timespec="seconds")}
        save_state(state)
        if res.get("status") == "success":
            ok += 1
            md = ((res.get("result") or {}).get("markdown") or "")
            if md:
                path = os.path.join(NOTE_OUTPUT_DIR, f"{it['aweme_id']}.md")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(md)
                print(f"    已保存 {path}（{len(md)} 字符）", flush=True)
        else:
            print(f"    失败：{res.get('message') or res.get('error') or res.get('status')}", flush=True)
        time.sleep(2)

    print(f"\n完成 {ok}/{len(todo)}，状态文件 {STATE_PATH}")
    return 0 if ok == len(todo) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default=os.path.join(BACKEND, "data", "_post_list_items.json"))
    ap.add_argument("--base", default="http://127.0.0.1:8483")
    ap.add_argument("--provider-id")
    ap.add_argument("--model")
    ap.add_argument("--timeout", type=int, default=1800, help="单条任务最长等待秒数")
    ap.add_argument("--poll", type=int, default=5)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    items = load_items(args.list)
    if not items:
        print(f"列表为空或格式不对：{args.list}")
        return 2
    print(f"共 {len(items)} 条作品，来源 {args.list}\n")

    if args.verify_only:
        return verify_only(items)
    return run_tasks(items, args.base, args.provider_id, args.model,
                     args.timeout, args.poll, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
