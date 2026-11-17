"""不依赖 pip 的最小 wheel 安装器。

用途：本机 pip 在受限沙箱里无法解包（写临时目录被拒），但项目还需要
SQLAlchemy / faster-whisper / ctranslate2 这些包才能启动后端。这里直接从
PyPI 下载 wheel 并用 zipfile 解到 `backend/.deps`，运行时把该目录加进
PYTHONPATH 即可，不碰系统环境。

用法：
    python tools/offline_deps.py SQLAlchemy faster-whisper ctranslate2 av tokenizers \
        huggingface-hub setuptools PyExecJS
    # 之后：
    set PYTHONPATH=backend\.deps
    python backend\main.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import zipfile

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "backend", ".deps")
CACHE = os.path.join(ROOT, ".wheels")
INDEX = "https://pypi.org/pypi/{}/json"

PY_VER = sys.version_info
TAGS = [
    f"cp{PY_VER.major}{PY_VER.minor}-cp{PY_VER.major}{PY_VER.minor}-win_amd64",
    f"cp{PY_VER.major}{PY_VER.minor}-abi3-win_amd64",
    "py3-none-any",
    "py2.py3-none-any",
]

SKIP = {"pip", "setuptools-scm", "wheel"}


def installed(name: str) -> bool:
    n = canonicalize_name(name)
    if not os.path.isdir(DEST):
        return False
    for entry in os.listdir(DEST):
        if entry.endswith(".dist-info") and canonicalize_name(entry.split("-")[0]) == n:
            return True
    return False


def pick_wheel(files: list[dict]) -> dict | None:
    wheels = [f for f in files if f["filename"].endswith(".whl")]
    for tag in TAGS:
        for f in wheels:
            if f["filename"].endswith(f"-{tag}.whl"):
                return f
    # 兜底：任意 pure wheel
    for f in wheels:
        if "none-any" in f["filename"]:
            return f
    return None


def deps_of(files: list[dict], wheel: dict) -> list[str]:
    """从 PyPI 的 METADATA 里读 Requires-Dist（不需要下载 wheel）。"""
    meta_url = next((f["url"] for f in files if f["filename"].endswith(".whl.metadata")), None)
    if not meta_url:
        return []
    try:
        with urllib.request.urlopen(meta_url, timeout=30) as r:
            text = r.read().decode("utf-8", "ignore")
    except Exception:
        return []
    env = default_environment()
    out = []
    for line in text.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        spec = line.split(":", 1)[1].strip()
        try:
            req = Requirement(spec)
        except Exception:
            continue
        if req.marker is not None and not req.marker.evaluate(env):
            continue
        out.append(canonicalize_name(req.name))
    return out


def download(url: str, filename: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, filename)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    tmp = path + ".part"
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, path)
    return path


def install_wheel(path: str) -> None:
    os.makedirs(DEST, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        z.extractall(DEST)


def resolve(name: str, depth: int = 0, seen: set | None = None) -> None:
    seen = seen if seen is not None else set()
    n = canonicalize_name(name)
    if n in seen or n in SKIP:
        return
    seen.add(n)
    if installed(n):
        print(f"{'  ' * depth}- {n}: already installed")
        return
    try:
        with urllib.request.urlopen(INDEX.format(n), timeout=60) as r:
            meta = json.load(r)
    except Exception as e:
        print(f"{'  ' * depth}! {n}: 查询失败 {type(e).__name__}: {e}")
        return
    files = meta.get("urls") or []
    wheel = pick_wheel(files)
    if not wheel:
        print(f"{'  ' * depth}! {n}: 无可用 wheel（可能是 sdist-only）")
        return
    print(f"{'  ' * depth}+ {n} {meta['info']['version']} <- {wheel['filename']} "
          f"({wheel['size'] / 1048576:.1f} MB)")
    path = download(wheel["url"], wheel["filename"])
    install_wheel(path)
    for dep in deps_of(files, wheel):
        resolve(dep, depth + 1, seen)


def main() -> int:
    pkgs = sys.argv[1:]
    if not pkgs:
        print(__doc__)
        return 2
    for p in pkgs:
        resolve(p)
    print(f"\n安装目录：{DEST}")
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(DEST) for f in fs)
    print(f"体积：{total / 1048576:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
