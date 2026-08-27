#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""heart 对话通道桥 —— 把「大脑(heart 的 facts)」和「身体(Hermes 会话)」粘起来。

两个方向（都跑在身体所在机器上，全本地）：
  感知线 inbound：把身体里用户的新消息同步进大脑的「对话记录.md」，标 [你]
  表达线 outbound：把大脑「要对你说.md」里的新话三处同写：
      ① 「对话记录.md」标 [我]（大脑记忆，heart 引擎能看到）
      ② state.db 会话 INSERT 一条 assistant 消息（让原生 agent 在上下文里自然看到）
      ③ print 到 stdout —— 由 cron 的 deliver 投到对应平台（平台无关，不写死飞书）

用法（手动调试）：
    python bridge.py --persona /path/to/character --session-id SID
    python bridge.py --config /path/to/bridge.json

cron（no_agent）里通常直接跑裸脚本，此时从「persona 目录下的 bridge.json」读配置。
配置优先级：CLI 参数 > 环境变量 > bridge.json > 默认值。
"""
import argparse
import json
import os
import subprocess
import sqlite3
import sys
import time
from pathlib import Path

_DEFAULTS = {
    "db": "/opt/data/state.db",
    "hermes": "/root/.local/bin/hermes",
    "inbox_name": "对话记录.md",
    "outbox_name": "要对你说.md",
}


def load_config(args) -> dict:
    cfg = dict(_DEFAULTS)
    cfg["persona"] = getattr(args, "persona", None)
    cfg["session_id"] = getattr(args, "session_id", None)
    cfg["state"] = getattr(args, "state", None)

    # 1) bridge.json（--config 或 persona 目录下）
    config_path = None
    if getattr(args, "config", None):
        config_path = Path(args.config)
    elif cfg["persona"]:
        config_path = Path(cfg["persona"]) / "bridge.json"
    if config_path and config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in data.items() if v not in (None, "")})

    # 2) CLI 参数覆盖（db/hermes 也支持）
    for key in ("db", "hermes", "state", "persona", "session_id"):
        v = getattr(args, key, None)
        if v:
            cfg[key] = v

    # 3) 环境变量覆盖
    for key, env in (("session_id", "HEART_SESSION_ID"),
                     ("db", "HEART_STATE_DB"),
                     ("hermes", "HEART_HERMES_BIN")):
        v = os.environ.get(env)
        if v:
            cfg[key] = v

    if not cfg.get("persona"):
        print("[error] 缺 persona 路径（--persona 或 bridge.json）", file=sys.stderr)
        sys.exit(1)
    if not cfg.get("session_id"):
        print("[error] 缺 session_id（--session-id / HEART_SESSION_ID / bridge.json）", file=sys.stderr)
        sys.exit(1)

    persona = Path(cfg["persona"])
    cfg["inbox"] = persona / cfg["inbox_name"]
    cfg["outbox"] = persona / cfg["outbox_name"]
    if not cfg.get("state"):
        cfg["state"] = persona / "bridge_state.json"
    return cfg


def load_state(path):
    if os.path.exists(path):
        return json.load(open(path))
    return {"last_msg_id": 0, "delivered": []}


def save_state(path, s):
    json.dump(s, open(path, "w"), ensure_ascii=False)


def inbound(cfg, s):
    raw = subprocess.check_output(
        [cfg["hermes"], "sessions", "export", "--format", "jsonl",
         "--only", "user-prompts", "--session-id", cfg["session_id"], "-"]).decode()
    new = []
    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        m = json.loads(line)
        if m.get("role") != "user":
            continue
        t = m.get("text", "")
        if t.startswith("[IMPORTANT:") or t.startswith("[CONTEXT COMPACTION"):
            continue
        mid = m.get("message_id", 0)
        if mid > s["last_msg_id"]:
            new.append((mid, t))
    if not new:
        return
    new.sort(key=lambda x: x[0])
    with open(cfg["inbox"], "a") as f:
        for _, t in new:
            f.write("\n[你] " + t + "\n")
    s["last_msg_id"] = new[-1][0]
    save_state(cfg["state"], s)


def write_to_session(cfg, text):
    """把小鹿的话写进 state.db 会话，作为 assistant 消息，让原生 agent 在上下文里看到。"""
    try:
        conn = sqlite3.connect(cfg["db"])
        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp, observed, active, compacted) "
            "VALUES (?, 'assistant', ?, ?, 0, 1, 0)",
            (cfg["session_id"], text, time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        print("[warn] state.db 写入失败:", e, file=sys.stderr)


def outbound(cfg, s):
    if not os.path.exists(cfg["outbox"]):
        return
    content = open(cfg["outbox"]).read().strip()
    if not content:
        return
    lines = [l for l in content.split("\n") if l.strip()]
    delivered = set(s["delivered"])
    fresh = [l for l in lines if l not in delivered]
    if not fresh:
        return
    with open(cfg["inbox"], "a") as f:
        for l in fresh:
            f.write("\n[我] " + l + "\n")
    for l in fresh:
        write_to_session(cfg, l)
    print("\n".join(fresh))  # stdout → cron deliver 投到对应平台
    s["delivered"] = lines
    save_state(cfg["state"], s)


def main():
    ap = argparse.ArgumentParser(description="heart 对话通道桥")
    ap.add_argument("--persona", help="角色文件夹（含 要对你说.md / 对话记录.md）")
    ap.add_argument("--session-id", help="身体(Hermes)会话 ID")
    ap.add_argument("--db", help="state.db 路径")
    ap.add_argument("--hermes", help="hermes 可执行文件路径")
    ap.add_argument("--state", help="桥状态文件路径")
    ap.add_argument("--config", help="配置文件（JSON），默认 persona/bridge.json")
    args = ap.parse_args()
    cfg = load_config(args)
    s = load_state(cfg["state"])
    inbound(cfg, s)
    outbound(cfg, s)


if __name__ == "__main__":
    main()
