#!/usr/bin/env python3
"""hermes — 执行层（第三层，可插拔「身体」）。

处理判别层 PASS 的想法：通过配置选择的执行后端（hermes / opencode / 未来其它平台）
去探索、行动，并把执行回报写回事实层。

heart 的「想」（潜意识+判别）与「记忆」（facts/.ideas）独立于任何执行后端；
本层只是「身体/途径」，可替换。类比：大脑通过身体去执行，身体做完后回报充实记忆。

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
    show_idea, show_verdict, run_executor, write_fact,
)
from engine import IDEAS_DIR_NAME, parse_idea_md, load_config


def act_one(folder: Path, path: Path, idea: dict, template: str, cfg: dict) -> tuple[str, str]:
    rewrite_idea(path, {"status": "processing"})
    prompt = build_prompt(
        template,
        idea=idea.get("idea", ""),
        verdict=idea.get("verdict", ""),
        seed=idea.get("seed", ""),
        facts_dir=str(folder),
    )
    out = run_executor(folder, prompt, cfg)   # 可插拔「身体」：hermes / opencode
    write_fact(folder, out)                    # 执行回报写回事实层（感官反馈）
    rewrite_idea(path, {"status": "done", "verdict": out[:300]})
    return "done", out


def scan_once(folder: Path, ideas_dir: Path, template: str, cfg: dict) -> int:
    for p in sorted(ideas_dir.glob("*.md")):
        idea = parse_idea_md(p.read_text(encoding="utf-8"))
        if idea.get("status") == "passed":
            show_idea(idea)
            console.print("[bold cyan]▸ Hermes 执行中…[/bold cyan]")
            status, verdict = act_one(folder, p, idea, template, cfg)
            show_verdict(status, verdict)
            return 1
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="hermes 执行层（可插拔身体）")
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
    cfg = load_config(here / "config.yaml")
    template = (here / "prompts" / "act.md").read_text(encoding="utf-8")

    if args.idea is not None:
        idea = {"idea": args.idea, "method": "-", "seed": "-", "verdict": ""}
        show_idea(idea)
        console.print("[bold cyan]▸ Hermes 执行中…[/bold cyan]")
        prompt = build_prompt(template, idea=args.idea, verdict="", seed="-",
                              facts_dir=str(folder))
        out = run_executor(folder, prompt, cfg)
        write_fact(folder, out)
        show_verdict("done", out)
        return

    ideas_dir = folder / IDEAS_DIR_NAME
    console.print(f"[bold]hermes 启动[/bold]: 监视 {ideas_dir} 的 passed 想法")

    if args.once:
        scan_once(folder, ideas_dir, template, cfg)
        return

    while True:
        try:
            scan_once(folder, ideas_dir, template, cfg)
        except KeyboardInterrupt:
            console.print("\n[bold]hermes 停止[/bold]")
            raise
        except Exception as e:
            console.print(f"[red][error] {e}[/red]")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
