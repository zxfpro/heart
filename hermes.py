#!/usr/bin/env python3
"""hermes — 执行层（第三层，Hermes agent）。

处理判别层 PASS 的想法：主动探索、行动，并把结果落回事实。

用法:
    python3 hermes.py /path/to/folder
    python3 hermes.py /path/to/folder --once
    python3 hermes.py /path/to/folder --idea "..."  # 直接执行一条
"""
import argparse
import sys
import time
from pathlib import Path

from common import (
    rewrite_idea, build_prompt, console, VERBOSE,
    show_idea, show_verdict, run_opencode,
)
from engine import IDEAS_DIR_NAME, parse_idea_md


def act_one(folder: Path, path: Path, idea: dict, template: str) -> tuple[str, str]:
    rewrite_idea(path, {"status": "processing"})
    prompt = build_prompt(
        template,
        idea=idea.get("idea", ""),
        verdict=idea.get("verdict", ""),
        seed=idea.get("seed", ""),
        facts_dir=str(folder),
    )
    out = run_opencode(folder, prompt)
    rewrite_idea(path, {"status": "done", "verdict": out[:300]})
    return "done", out


def scan_once(folder: Path, ideas_dir: Path, template: str) -> int:
    for p in sorted(ideas_dir.glob("*.md")):
        idea = parse_idea_md(p.read_text(encoding="utf-8"))
        if idea.get("status") == "passed":
            show_idea(idea)
            console.print("[bold cyan]▸ Hermes 执行中…[/bold cyan]")
            status, verdict = act_one(folder, p, idea, template)
            show_verdict(status, verdict)
            return 1
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="hermes 执行层")
    ap.add_argument("folder")
    ap.add_argument("--interval", type=int, default=5, help="扫描间隔（秒）")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--idea", default=None, help="直接执行一条想法")
    ap.add_argument("--verbose", action="store_true", help="显示细节")
    args = ap.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        console.print(f"[red][error] 不是文件夹: {folder}[/red]")
        sys.exit(1)

    here = Path(__file__).resolve().parent
    template = (here / "prompts" / "act.md").read_text(encoding="utf-8")

    if args.idea is not None:
        idea = {"idea": args.idea, "method": "-", "seed": "-", "verdict": ""}
        show_idea(idea)
        console.print("[bold cyan]▸ Hermes 执行中…[/bold cyan]")
        prompt = build_prompt(template, idea=args.idea, verdict="", seed="-",
                              facts_dir=str(folder))
        out = run_opencode(folder, prompt)
        show_verdict("done", out)
        return

    ideas_dir = folder / IDEAS_DIR_NAME
    console.print(f"[bold]hermes 启动[/bold]: 监视 {ideas_dir} 的 passed 想法")

    if args.once:
        scan_once(folder, ideas_dir, template)
        return

    while True:
        try:
            scan_once(folder, ideas_dir, template)
        except KeyboardInterrupt:
            console.print("\n[bold]hermes 停止[/bold]")
            raise
        except Exception as e:
            console.print(f"[red][error] {e}[/red]")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
