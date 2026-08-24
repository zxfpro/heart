#!/usr/bin/env python3
"""common — idea-engine 三层架构的共享工具。"""
import json
import re
import subprocess
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

console = Console()
VERBOSE = False


def rewrite_idea(path: Path, meta_updates: dict = None, body: str = None) -> None:
    text = path.read_text(encoding="utf-8")
    m = FRONT.match(text)
    if m:
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        old_body = m.group(2).rstrip("\n")
    else:
        meta, old_body = {}, text.rstrip("\n")

    if meta_updates:
        for k, v in meta_updates.items():
            meta[k] = str(v).replace("\n", " ")[:300]

    new_body = body if body is not None else old_body
    lines = ["---"] + [f"{k}: {v}" for k, v in meta.items()] + ["---", ""]
    if new_body:
        lines.append(new_body)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def recover_stuck(ideas_dir: Path, from_status: str = "processing", to_status: str = "new") -> int:
    from engine import parse_idea_md
    n = 0
    for p in ideas_dir.glob("*.md"):
        idea = parse_idea_md(p.read_text(encoding="utf-8"))
        if idea.get("status") == from_status:
            rewrite_idea(p, {"status": to_status})
            n += 1
    return n


def build_prompt(template: str, **kw) -> str:
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def run_opencode(folder: Path, prompt: str) -> str:
    proc = subprocess.Popen(
        ["opencode", "run", prompt],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        bufsize=1, cwd=str(folder),
    )
    stdout_lines = []

    def drain_stderr():
        for line in proc.stderr:
            line = ANSI_RE.sub("", line).strip()
            if line and VERBOSE:
                console.print(f"  [dim]→ {line}[/dim]")

    t = threading.Thread(target=drain_stderr, daemon=True)
    t.start()

    for line in proc.stdout:
        line = ANSI_RE.sub("", line).strip()
        if line:
            stdout_lines.append(line)

    try:
        proc.wait(timeout=900)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        t.join(1)
        return "超时未完成，已终止"

    t.join(3)
    return "\n".join(stdout_lines).strip()


def run_hermes(folder: Path, prompt: str, cfg: dict) -> str:
    """执行层「身体」之一：通过 Hermes API Server（OpenAI 协议）触发真实 agent 执行。

    heart 的「想」与「记忆」不依赖任何具体执行后端；本函数只是其中一种「身体」。
    """
    base = (cfg.get("hermes_base_url") or "").strip()
    if not base:
        return "未配置 hermes_base_url：请设置环境变量 HERMES_BASE_URL"
    url = base.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": cfg.get("hermes_model", "hermes-agent"),
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (cfg.get("hermes_api_key") or ""),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=int(cfg.get("executor_timeout", 900))) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        return f"Hermes 执行失败: {e}"
    try:
        body = json.loads(raw)
        content = body["choices"][0]["message"].get("content") or ""
    except Exception as e:
        return f"解析 Hermes 响应失败: {e} raw={raw[:200]}"
    return content.strip()


def run_executor(folder: Path, prompt: str, cfg: dict) -> str:
    """执行层分派：按配置选择「身体」（hermes / opencode / 未来其它平台）。

    大脑（想/记忆）不变，身体可换——这正是 heart 可迁移到任意平台的根基。
    """
    kind = (cfg.get("executor") or "hermes").strip().lower()
    if kind == "opencode":
        return run_opencode(folder, prompt)
    return run_hermes(folder, prompt, cfg)


def write_fact(folder: Path, text: str) -> str:
    """执行结果写回事实层（感官反馈）：作为一条新事实，进入下一轮上下文。

    这是 heart 独立记忆闭环的关键——「身体」做完后的回报，充实长期记忆。
    """
    text = (text or "").strip()
    if not text:
        return ""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"执行-{ts}.md"
    (folder / fname).write_text(f"# 执行记录 {ts}\n\n{text}\n", encoding="utf-8")
    return fname


def show_idea(idea: dict) -> None:
    console.print(Panel(
        idea.get("idea", ""),
        title=f"[bold]潜意识想法[/bold] · [magenta]{idea.get('method', '')}[/magenta] · 源自 {idea.get('seed', '') or '?'}",
        border_style="magenta",
        box=box.ROUNDED,
        padding=(0, 1),
    ))


def show_verdict(status: str, verdict: str) -> None:
    if status in ("done", "passed"):
        console.print(Panel(
            verdict[:800],
            title="[bold green]✓ 通过[/bold green]",
            border_style="green",
            box=box.ROUNDED,
        ))
    else:
        console.print(Panel(
            verdict[:300],
            title="[bold yellow]✗ 跳过[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        ))
    console.print()
