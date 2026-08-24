#!/usr/bin/env python3
"""common — idea-engine 三层架构的共享工具。"""
import re
import subprocess
import threading
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
