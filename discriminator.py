#!/usr/bin/env python3
"""discriminator — 判别层（第二层）。

只做两件事，不执行：
1. 过滤：判断每条新想法是 SKIP 还是 PASS（PASS 交给执行层）。
2. 蒸馏：老想法逐渐压缩、遗忘（遗忘 = 上下文压缩到 0，不是删除）。

用法:
    python3 discriminator.py /path/to/folder
    python3 discriminator.py /path/to/folder --once
    python3 discriminator.py /path/to/folder --idea "..."   # 快速判一条
"""
import argparse
import sys
import time
from pathlib import Path

from rich.console import Console

from common import (
    rewrite_idea, recover_stuck, build_prompt, console,
    VERBOSE, show_idea, show_verdict,
)
from engine import (
    IDEAS_DIR_NAME, parse_idea_md, list_ideas,
    generate, load_config, _parse_ts,
)


def load_persona(folder: Path) -> str:
    p = folder / "AGENTS.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def judge_one(cfg: dict, persona: str, template: str, idea: dict) -> tuple[str, str]:
    prompt = build_prompt(
        template, persona=persona or "(无)",
        idea=idea.get("idea", ""), seed=idea.get("seed", ""),
        parent_kind=idea.get("parent_kind", ""), parent=idea.get("parent", ""),
    )
    out, _, _ = generate(prompt, cfg)
    out = out.strip()
    if out[:5].upper().startswith("PASS"):
        return "passed", out
    return "skipped", out


def scan_once(folder: Path, cfg: dict, ideas_dir: Path, persona: str, judge_tpl: str) -> int:
    new_files = []
    for p in sorted(ideas_dir.glob("*.md")):
        idea = parse_idea_md(p.read_text(encoding="utf-8"))
        if idea.get("status") in (None, "", "new"):
            new_files.append((p, idea))

    if not new_files:
        return 0

    for p, idea in new_files[:-1]:
        rewrite_idea(p, {"status": "dropped", "verdict": "执行期间堆积的旧想法，丢弃"})

    p, idea = new_files[-1]
    dropped = len(new_files) - 1
    if dropped:
        console.print(f"[dim]~ 丢弃 {dropped} 条堆积的旧想法[/dim]")

    show_idea(idea)
    console.print("[bold cyan]▸ 判别中…[/bold cyan]")
    status, verdict = judge_one(cfg, persona, judge_tpl, idea)
    rewrite_idea(p, {"status": status, "verdict": verdict[:200]})
    show_verdict(status, verdict)
    return 1


def distill_once(cfg: dict, ideas_dir: Path, distill_tpl: str, max_level: int,
                 age_threshold: int, batch: int) -> int:
    now = time.time()
    done = 0
    for p in sorted(ideas_dir.glob("*.md")):
        if done >= batch:
            break
        idea = parse_idea_md(p.read_text(encoding="utf-8"))
        if idea.get("status") not in ("skipped", "passed", "done"):
            continue
        distill = int(idea.get("distill", "0") or 0)
        if distill >= max_level:
            continue
        ts = _parse_ts(idea.get("ts", ""))
        age = now - (ts if ts is not None else now)
        if age < age_threshold:
            continue

        prompt = build_prompt(distill_tpl, idea=idea.get("idea", ""))
        new_text, _, _ = generate(prompt, cfg)
        new_text = new_text.strip()
        distill += 1

        if distill >= max_level:
            rewrite_idea(p, {"status": "forgotten", "distill": distill}, body="")
            console.print(f"[dim]~ 遗忘: {idea.get('idea', '')[:40]}...[/dim]")
        else:
            keep = new_text or idea.get("idea", "")
            rewrite_idea(p, {"distill": distill}, body=keep)
            console.print(f"[dim]~ 蒸馏#{distill}: {keep[:40]}[/dim]")
        done += 1
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description="discriminator 判别层")
    ap.add_argument("folder")
    ap.add_argument("--interval", type=int, default=10, help="扫描间隔（秒）")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--idea", default=None, help="快速判断一条想法")
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
    persona = load_persona(folder)
    judge_tpl = (here / "prompts" / "judge.md").read_text(encoding="utf-8")
    distill_tpl = (here / "prompts" / "distill.md").read_text(encoding="utf-8")

    if args.idea is not None:
        idea = {"idea": args.idea, "method": "-", "seed": "-",
                "parent_kind": "", "parent": ""}
        show_idea(idea)
        console.print("[bold cyan]▸ 判别中…[/bold cyan]")
        status, verdict = judge_one(cfg, persona, judge_tpl, idea)
        show_verdict(status, verdict)
        return

    ideas_dir = folder / IDEAS_DIR_NAME
    console.print(f"[bold]discriminator 启动[/bold]: 监视 {ideas_dir}")

    stuck = recover_stuck(ideas_dir)
    if stuck:
        console.print(f"[dim][恢复] {stuck} 条卡在 processing 的想法已重置为 new[/dim]")

    if args.once:
        scan_once(folder, cfg, ideas_dir, persona, judge_tpl)
        distill_once(cfg, ideas_dir, distill_tpl, cfg["distill_max"],
                     cfg["distill_age"], 2)
        return

    while True:
        try:
            scan_once(folder, cfg, ideas_dir, persona, judge_tpl)
            distill_once(cfg, ideas_dir, distill_tpl, cfg["distill_max"],
                         cfg["distill_age"], 2)
        except KeyboardInterrupt:
            console.print("\n[bold]discriminator 停止[/bold]")
            raise
        except Exception as e:
            console.print(f"[red][error] {e}[/red]")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
