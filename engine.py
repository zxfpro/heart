#!/usr/bin/env python3
"""idea-engine — 黑盒想法生成器（潜意识）。指向一个文件夹，像晶振一样定时产生想法。

本质就是一个 while True：
    扫文件夹 → 随机思维生成想法 → 挂到树上 → 留存（不评判，只产生）
"""
import argparse
import json
import os
import random
import re
import sys
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

DEFAULT_CONFIG = {
    "interval": 3600,      # tick 间隔（秒）
    "active_hours": "",    # 动态频率：活跃时段 "HH:MM-HH:MM"（留空=不启用，用 interval）
    "active_interval": 90,  # 活跃时段 tick 间隔（秒）
    "rest_interval": 300,   # 非活跃时段 tick 间隔（秒）
    "timezone": "",         # 时区（如 Asia/Shanghai），留空=实例本地时区
    "clinginess": 1.0,      # 粘人程度 0-1：缩放 proactive_files 的触发权重
    "proactive_files": "关于你,关于朋友",  # 触发「主动找对方」的人设文件名关键词（逗号分隔）
    "limit": 1,            # 每轮生成条数（默认 1 条）
    "recent": 20,          # 生成时回看最近 N 条想法
    "max_chars": 20000,    # 喂给模型的原料字符上限
    "methods": "联想,类比,比喻,反转,嫁接,跨界组合,逆向,极端化,欲望",
    "base_url": "",
    "api_key": "",
    "model": "deepseek-v4-flash",
    "temperature": 0.8,
    "fact_weight": 3.0,        # 事实的触发权重（高于想法）
    "idea_weight": 1.0,        # 想法的触发权重
    "recency_half_life": 86400.0,  # 新旧衰减半衰期（秒，默认 24h）
    "distill_age": 3600,       # 想法多久后开始蒸馏（秒）
    "distill_max": 3,          # 蒸馏到第几轮后遗忘（压缩到 0）
    "executor": "hermes",      # 执行层「身体」：hermes / opencode（可插拔）
    "hermes_base_url": "http://127.0.0.1:8642",  # Hermes API Server（OpenAI 协议）
    "hermes_api_key": "",      # Hermes API Server 鉴权 key（走 HERMES_API_KEY 环境变量）
    "hermes_model": "hermes-agent",
}

TEXT_EXTS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".sh", ".go", ".rs", ".java", ".c",
    ".cpp", ".h", ".html", ".css", ".vue", ".sql",
}

SKIP_DIRS = {
    ".git", "node_modules", ".ideas", "__pycache__", "venv",
    ".venv", ".DS_Store", "dist", "build", ".next", ".opencode",
}

IDEAS_DIR_NAME = ".ideas"  # 想法文件夹，与事实分开存放（地位等同，仅用于区分）


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _load_flat_yaml(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = re.sub(r"\s+#.*$", "", v).strip()
        if v == "":
            out[k] = ""
        elif v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        elif re.fullmatch(r"-?\d+", v):
            out[k] = int(v)
        elif re.fullmatch(r"-?\d+\.\d+", v):
            out[k] = float(v)
        else:
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            out[k] = v
    return out


def load_config(path: Path) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if path.exists():
        try:
            data = _load_flat_yaml(path)
            cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
        except Exception as e:
            print(f"[warn] 配置读取失败，用默认: {e}", file=sys.stderr)
    # 环境变量优先，避免把密钥/端点写死在代码或配置里
    for _key, _env in (("api_key", "HEART_API_KEY"), ("base_url", "HEART_BASE_URL"),
                       ("hermes_api_key", "HERMES_API_KEY"), ("hermes_base_url", "HERMES_BASE_URL")):
        _val = os.environ.get(_env)
        if _val:
            cfg[_key] = _val
    return cfg


def list_fact_files(folder: Path) -> list:
    out = []
    for p in sorted(folder.rglob("*")):
        if p.is_dir() or p.name.startswith("."):
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(folder).parts):
            continue
        if p.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            if p.stat().st_size > 200_000:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not text.strip():
            continue
        out.append({
            "kind": "fact",
            "ref": str(p.relative_to(folder)),
            "ts": p.stat().st_mtime,
            "text": text,
        })
    return out


def facts_blob(facts: list, max_chars: int) -> str:
    blocks, total = [], 0
    for f in facts:
        block = f"### {f['ref']}\n{f['text']}\n"
        if total + len(block) > max_chars:
            remain = max_chars - total
            if remain > 60:
                block = f"### {f['ref']}\n{f['text'][:remain - 40]}...\n(截断)"
                blocks.append(block)
            break
        blocks.append(block)
        total += len(block)
    return "\n".join(blocks)


def _parse_ts(ts_str: str):
    try:
        return datetime.fromisoformat(ts_str).timestamp()
    except Exception:
        return None


_IDEA_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def parse_idea_md(text: str) -> dict:
    m = _IDEA_FRONT.match(text)
    if not m:
        return {"idea": text.strip()}
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    meta["idea"] = m.group(2).strip()
    return meta


def list_ideas(ideas_dir: Path) -> list:
    if not ideas_dir.exists():
        return []
    out = []
    for p in ideas_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        idea = parse_idea_md(text)
        if idea.get("idea"):
            idea["file"] = p.name
            out.append(idea)
    out.sort(key=lambda x: x.get("ts", ""))
    return out


def write_idea(ideas_dir: Path, idea: dict) -> None:
    ideas_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{int(time.time() * 1000)}_{idea['id']}.md"
    lines = [
        "---",
        "type: idea",
        f"method: {idea.get('method', '')}",
        f"parent_kind: {idea.get('parent_kind', '')}",
        f"parent: {idea.get('parent', '')}",
        f"seed: {idea.get('seed', '')}",
        f"ts: {idea['ts']}",
        "---",
        "",
        idea["idea"],
    ]
    (ideas_dir / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")


def ideas_blob(ideas_dir: Path, max_chars: int, limit: int) -> str:
    ideas = list_ideas(ideas_dir)[-limit:][::-1]  # 新的在前
    blocks, total = [], 0
    for it in ideas:
        block = (
            f"### [想法] {it.get('file', '')} · 方法={it.get('method', '')}\n"
            f"{it.get('idea', '')}\n"
        )
        if total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n".join(blocks)


def weighted_pick(facts: list, ideas: list, cfg: dict):
    now = time.time()
    fact_w = float(cfg.get("fact_weight", 3.0))
    idea_w = float(cfg.get("idea_weight", 1.0))
    half = float(cfg.get("recency_half_life", 86400.0))
    clinginess = float(cfg.get("clinginess", 1.0))
    proactive_keys = [k.strip() for k in str(cfg.get("proactive_files", "") or "").split(",") if k.strip()]
    sources, weights = [], []
    for f in facts:
        w = fact_w * (0.5 ** (max(0.0, now - f["ts"]) / half))
        ref = f.get("ref", "")
        if proactive_keys and any(k in ref for k in proactive_keys):
            w *= clinginess  # 粘人程度：缩放「主动找对方」类人设的触发权重
        sources.append(f)
        weights.append(w)
    for it in ideas:
        src = dict(it)
        src["kind"] = "idea"
        src["text"] = it.get("idea", "")
        t = _parse_ts(it.get("ts", ""))
        if t is None:
            t = now
        w = idea_w * (0.5 ** (max(0.0, now - t) / half))
        sources.append(src)
        weights.append(w)
    if not sources:
        return None
    if sum(weights) <= 0:
        return random.choice(sources)
    return random.choices(sources, weights=weights, k=1)[0]


def render_focus(focus) -> str:
    if not focus:
        return "(无)"
    kind = focus.get("kind", "")
    ref = focus.get("ref") or focus.get("file", "")
    text = focus.get("text") or focus.get("idea", "")
    label = "事实" if kind == "fact" else "想法"
    return f"### 焦点（{label}）: {ref}\n{text}\n"


def _hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def current_interval(cfg: dict) -> int:
    """按当前时间返回 tick 间隔；支持白天/晚上动态频率（active_hours）。"""
    window = str(cfg.get("active_hours", "") or "").strip()
    if not window or "-" not in window:
        return int(cfg.get("interval", 3600))
    try:
        frm, to = window.split("-", 1)
        frm_m = _hhmm(frm.strip())
        to_m = _hhmm(to.strip())
        tz = str(cfg.get("timezone", "") or "").strip()
        now = datetime.now(ZoneInfo(tz)) if tz else datetime.now()
        cur = now.hour * 60 + now.minute
        if frm_m <= to_m:
            active = frm_m <= cur < to_m
        else:  # 跨午夜（如 23:00-09:00）
            active = cur >= frm_m or cur < to_m
        return int(cfg.get("active_interval", 90)) if active else int(cfg.get("rest_interval", 300))
    except Exception:
        return int(cfg.get("interval", 3600))


def _now_str(cfg: dict) -> str:
    """当前时间的中文友好描述，注入提示词让小鹿有时间感（早上别道晚安）。"""
    tz = str(cfg.get("timezone", "") or "").strip()
    now = datetime.now(ZoneInfo(tz)) if tz else datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    wd = weekdays[now.weekday()]
    h = now.hour
    if 5 <= h < 9:
        part = "清晨"
    elif 9 <= h < 12:
        part = "上午"
    elif 12 <= h < 14:
        part = "中午"
    elif 14 <= h < 18:
        part = "下午"
    elif 18 <= h < 23:
        part = "晚上"
    else:
        part = "深夜"
    return f"{now.year}年{now.month}月{now.day}日 {wd} {part} {h}:{now.minute:02d}"


def print_tree(ideas_dir: Path) -> None:
    ideas = list_ideas(ideas_dir)
    if not ideas:
        print("(尚无想法)")
        return
    children = {}
    roots = []
    for it in ideas:
        if it.get("parent_kind") == "idea" and it.get("parent"):
            children.setdefault(it["parent"], []).append(it)
        else:
            roots.append(it)

    def label(it):
        return f"[{it.get('method', '')}] {it.get('idea', '')}  ({it.get('file', '')})"

    def walk(item, indent, prefix):
        print(f"{indent}{prefix}{label(item)}")
        kids = children.get(item.get("file", ""), [])
        for i, k in enumerate(kids):
            walk(k, indent + "    ", "└─ " if i == len(kids) - 1 else "├─ ")

    fact_groups = {}
    for it in roots:
        fact_groups.setdefault(it.get("parent") or "(未挂载)", []).append(it)

    print("想法树（事实为根，想法沿树生长）：")
    for fact, items in fact_groups.items():
        print(f"[事实] {fact}")
        for i, it in enumerate(items):
            walk(it, "", "├─ " if i < len(items) - 1 else "└─ ")


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def dedup(candidates: list, existing: list, min_ratio: float = 0.6) -> list:
    kept = []
    for c in candidates:
        text = c.get("idea", "")
        if not text:
            continue
        if any(_similarity(text, e.get("idea", "")) > min_ratio for e in existing):
            continue
        if any(_similarity(text, k.get("idea", "")) > min_ratio for k in kept):
            continue
        kept.append(c)
    return kept


def generate(prompt: str, cfg: dict):
    base = (cfg.get("base_url") or "").strip()
    if not base:
        return "", "未配置 base_url：请设置环境变量 HEART_BASE_URL（或 config.yaml 的 base_url）", -1
    if not base.startswith(("http://", "https://")):
        return "", f"base_url 无效（需以 http(s):// 开头）：{base}", -1
    url = base.rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.get("model", ""),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(cfg.get("temperature", 0.8)),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg.get("api_key", ""),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return "", e.read().decode("utf-8", "ignore"), e.code
    except Exception as e:
        return "", str(e), -1

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"].get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
    except Exception as e:
        return "", f"解析响应失败: {e} raw={raw[:300]}", -2
    return content, "", 0


def extract_json(text: str):
    try:
        return json.loads(text[text.index("["): text.rindex("]") + 1])
    except Exception:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


def run_once(folder: Path, cfg: dict, ideas_dir: Path, template: str) -> int:
    facts = list_fact_files(folder)
    ideas = list_ideas(ideas_dir)
    facts_content = facts_blob(facts, cfg["max_chars"])
    ideas_content = ideas_blob(ideas_dir, cfg["max_chars"], cfg["recent"])
    existing = ideas

    persona_path = folder / "AGENTS.md"
    persona = persona_path.read_text(encoding="utf-8") if persona_path.exists() else ""

    methods = [m.strip() for m in str(cfg.get("methods", "")).split(",") if m.strip()]
    method = random.choice(methods) if methods else "联想"

    focus = weighted_pick(facts, ideas, cfg)
    focus_str = render_focus(focus)

    prompt = (
        template.replace("{facts}", facts_content)
        .replace("{ideas}", ideas_content or "(尚无想法)")
        .replace("{focus}", focus_str)
        .replace("{method}", method)
        .replace("{persona}", persona or "(无)（用自然、口语化的普通人语气）")
        .replace("{now}", _now_str(cfg))
    )

    stdout, stderr, rc = generate(prompt, cfg)
    data = extract_json(stdout)
    if not data:
        print("[warn] 未能解析模型输出，跳过本轮", file=sys.stderr)
        print(f"[warn] rc={rc} stdout={stdout[:300]!r}", file=sys.stderr)
        print(f"[warn] stderr={stderr[:300]!r}", file=sys.stderr)
        return 0

    cands = []
    for item in data:
        if not isinstance(item, dict) or not item.get("idea"):
            continue
        pk = str(item.get("parent_kind", "")).strip().lower()
        if pk not in ("fact", "idea"):
            pk = "fact" if item.get("parent") else ""
        cands.append({
            "id": _new_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "seed": str(item.get("seed", "")).strip(),
            "parent_kind": pk,
            "parent": str(item.get("parent", "")).strip(),
            "idea": str(item["idea"]).strip(),
        })

    kept = dedup(cands, existing)
    for k in kept:
        write_idea(ideas_dir, k)

    now = datetime.now().strftime("%H:%M:%S")
    focus_ref = (focus.get("ref") or focus.get("file", "")) if focus else "-"
    print(f"[tick {now}] 思维={method} · 焦点={focus_ref} 产生 {len(kept)} 条")
    for k in kept:
        src = f"  [源自: {k['seed']}]" if k.get("seed") else ""
        print(f"  + {k['idea']}{src}")
    return len(kept)


def main() -> None:
    ap = argparse.ArgumentParser(description="idea-engine 黑盒想法生成器")
    ap.add_argument("folder", help="指定的文件夹（知识/经验原料来源）")
    ap.add_argument("--interval", type=int, default=None, help="覆盖 tick 间隔（秒）")
    ap.add_argument("--limit", type=int, default=None, help="覆盖每轮生成条数")
    ap.add_argument("--once", action="store_true", help="只跑一轮后退出（调试）")
    ap.add_argument("--tree", action="store_true", help="打印想法树后退出")
    ap.add_argument("--config", default=None, help="config.yaml 路径，默认用脚本同目录")
    args = ap.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"[error] 不是文件夹: {folder}", file=sys.stderr)
        sys.exit(1)

    skill_dir = Path(__file__).resolve().parent
    cfg_path = Path(args.config) if args.config else skill_dir / "config.yaml"
    cfg = load_config(cfg_path)
    if args.interval:
        cfg["interval"] = args.interval
    if args.limit:
        cfg["limit"] = args.limit

    ideas_dir = folder / IDEAS_DIR_NAME
    template = (skill_dir / "prompts" / "think.md").read_text(encoding="utf-8")

    print(f"idea-engine 启动: folder={folder}, interval={cfg['interval']}s")
    print(f"想法存到: {ideas_dir}")

    if args.tree:
        print_tree(ideas_dir)
        return

    if args.once:
        run_once(folder, cfg, ideas_dir, template)
        return

    while True:
        try:
            run_once(folder, cfg, ideas_dir, template)
        except KeyboardInterrupt:
            print("\nidea-engine 停止")
            raise
        except Exception as e:
            print(f"[error] 本轮异常: {e}", file=sys.stderr)
        time.sleep(current_interval(cfg))


if __name__ == "__main__":
    main()
