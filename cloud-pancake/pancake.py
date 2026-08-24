#!/usr/bin/env python3
"""cloud-pancake — 每周随机闹钟，到点给自己发一条没头没脑的可爱消息。

让自己成为自己小确幸的源头。

机制（由 launchd 每小时唤起一次，本身带门控，所以不会打扰）：
  - 仅在 08:00–22:00 的安静窗口外不发。
  - 当天已发过就跳过（一天最多一条）。
  - 离上次发送越久，本次触发概率越高（≈ 一周一朵，偶有偏移，正是"随机"）。
  - 触发即用 macOS 原生通知弹出，并更新状态文件。

用法:
    python3 pancake.py              # 正常跑（门控决定发不发）
    python3 pancake.py --fire      # 立刻发一条（调试 / 演示）
    python3 pancake.py --state     # 查看状态

安装为常驻"每周随机闹钟"：
    cp com.cloud-pancake.plist ~/Library/LaunchAgents/
    # 改 plist 里 pancake.py 的绝对路径后：
    launchctl load ~/Library/LaunchAgents/com.cloud-pancake.plist
卸载：
    launchctl unload ~/Library/LaunchAgents/com.cloud-pancake.plist
    rm ~/Library/LaunchAgents/com.cloud-pancake.plist

状态与日志：~/Library/Application Support/cloud-pancake/
"""
import argparse
import json
import random
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

SELF = Path(__file__).resolve()
STATE_DIR = Path.home() / "Library" / "Application Support" / "cloud-pancake"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "pancake.log"

TITLE = "☁️ 云朵煎饼"
SUBTITLE = "给你的小确幸"
SOUND = "glass"  # gentle macOS sound

# 没头没脑的可爱消息。增删随意，保持"无来由地甜"即可。
MESSAGES = [
    "今天的云像你早上没吃到的煎饼",
    "刚才的风是来还你去年丢的那只袜子的",
    "你桌上那支笔刚才偷偷深呼吸了一次",
    "我替今天的太阳请了一会假，它想看你发会儿呆",
    "那杯水在杯子里等了你三分钟，别让它失望",
    "你昨天忘记的那个想法，现在长成了一朵小蘑菇",
    "楼下的猫说它把第八条命留给你了",
    "今天的电梯专门为你多停了半秒",
    "你呼吸的时候，窗帘跟着你数了一拍",
    "有片树叶在窗外排了两小时队，只为跟你打个招呼",
    "我把「想你」折成小纸船放进你的水杯了",
    "你今天的影子比昨天胖了一点点，是被太阳夸的",
    "刚才有只蚊子临走前跟你说辛苦了",
    "你口袋里的钥匙在偷偷合唱",
    "今天的月亮是熟透的那种，你记得抬头",
    "有朵云在偷偷学你笑的样子",
    "你鞋带刚才打了个结，是想多陪你走一段",
    "地铁刚刚对你眨了一下眼，你没看见就算了",
    "你的影子在地面上偷偷给自己鼓了个掌",
    "今天的雨只下给你听的那一半",
]


def log(msg: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(d: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def notify(body: str) -> None:
    body_esc = body.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'display notification "{body_esc}" '
        f'with title "{TITLE}" subtitle "{SUBTITLE}" sound name "{SOUND}"'
    )
    subprocess.run(["osascript", "-e", script],
                   capture_output=True, text=True, timeout=15)
    # 附一句轻声念白（可爱消息值得被听见）；失败就静默
    subprocess.run(["say", "-r", "175", body],
                   capture_output=True, text=True, timeout=30)


def fire() -> str:
    msg = random.choice(MESSAGES)
    notify(msg)
    today = date.today().isoformat()
    st = load_state()
    st["last_sent"] = today
    st["last_msg"] = msg
    st["count"] = st.get("count", 0) + 1
    save_state(st)
    log(f"sent: {msg}")
    return msg


def should_fire() -> tuple[bool, str]:
    now = datetime.now()
    if not (8 <= now.hour <= 22):
        return False, f"quiet hours ({now.hour}:xx), skip"
    st = load_state()
    last = st.get("last_sent")
    if last == date.today().isoformat():
        return False, "already sent today, skip"
    try:
        days = (date.today() - date.fromisoformat(last)).days if last else 999
    except Exception:
        days = 999
    if days >= 8:
        p = 0.5            # 欠得太久，尽快补一朵
    elif days >= 6:
        p = 0.15
    else:
        p = 0.02           # 刚发过，安静几天
    roll = random.random()
    fire_it = roll < p
    return fire_it, f"days={days} p={p} roll={roll:.3f} -> {'FIRE' if fire_it else 'skip'}"


def main() -> None:
    ap = argparse.ArgumentParser(description="cloud-pancake 每周随机闹钟")
    ap.add_argument("--fire", action="store_true", help="立刻发一条，不管门控")
    ap.add_argument("--state", action="store_true", help="查看状态")
    args = ap.parse_args()

    if args.state:
        print(json.dumps(load_state(), ensure_ascii=False, indent=2)
              or "(no state yet)")
        return

    if args.fire:
        msg = fire()
        print(f"sent: {msg}")
        return

    ok, reason = should_fire()
    log(reason)
    if ok:
        msg = fire()
        print(f"sent: {msg}")
    else:
        print(reason)


if __name__ == "__main__":
    main()
