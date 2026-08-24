#!/usr/bin/env python3
"""mind — 思维服务（潜意识 + 判别层 合并为一个进程）。

一个进程内跑完整条「想 → 判 → 蒸馏」链路：
    1. 潜意识（engine.run_once）冒想法
    2. 判别层（discriminator.scan_once）判断 SKIP / PASS
    3. 蒸馏（discriminator.distill_once）压缩 / 遗忘老想法

执行层（hermes.py）是另一个独立服务，负责把 PASS 的想法落地成行动。

用法:
    python3 mind.py /path/to/folder
    python3 mind.py /path/to/folder --once
    python3 mind.py /path/to/folder --interval 30
"""
import argparse
import sys
import time
from pathlib import Path

import common
from common import console, recover_stuck
from engine import IDEAS_DIR_NAME, load_config, run_once
from discriminator import scan_once, distill_once, load_persona


def main() -> None:
    ap = argparse.ArgumentParser(description="mind 思维服务（潜意识 + 判别层）")
    ap.add_argument("folder")
    ap.add_argument("--interval", type=int, default=None, help="覆盖 tick 间隔（秒）")
    ap.add_argument("--once", action="store_true", help="只跑一轮后退出（调试）")
    ap.add_argument("--verbose", action="store_true", help="显示细节")
    args = ap.parse_args()

    common.VERBOSE = args.verbose

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        console.print(f"[red][error] 不是文件夹: {folder}[/red]")
        sys.exit(1)

    here = Path(__file__).resolve().parent
    cfg = load_config(here / "config.yaml")
    if args.interval:
        cfg["interval"] = args.interval

    ideas_dir = folder / IDEAS_DIR_NAME
    persona = load_persona(folder)
    think_tpl = (here / "prompts" / "think.md").read_text(encoding="utf-8")
    judge_tpl = (here / "prompts" / "judge.md").read_text(encoding="utf-8")
    distill_tpl = (here / "prompts" / "distill.md").read_text(encoding="utf-8")

    console.print(f"[bold]mind 启动[/bold]: 潜意识冒想法 + 判别 + 蒸馏 → {ideas_dir}")

    stuck = recover_stuck(ideas_dir)
    if stuck:
        console.print(f"[dim][恢复] {stuck} 条卡在 processing 的想法已重置为 new[/dim]")

    def tick() -> None:
        run_once(folder, cfg, ideas_dir, think_tpl)                 # 1. 潜意识冒想法
        scan_once(folder, cfg, ideas_dir, persona, judge_tpl)       # 2. 判别 SKIP / PASS
        distill_once(cfg, ideas_dir, distill_tpl,                   # 3. 蒸馏 / 遗忘
                     cfg["distill_max"], cfg["distill_age"], 2)

    if args.once:
        tick()
        return

    while True:
        try:
            tick()
        except KeyboardInterrupt:
            console.print("\n[bold]mind 停止[/bold]")
            raise
        except Exception as e:
            console.print(f"[red][error] {e}[/red]")
        time.sleep(cfg["interval"])


if __name__ == "__main__":
    main()
