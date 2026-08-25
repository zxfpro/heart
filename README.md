<div align="center">

# ❤️ Heart

**给模型增加心跳 · Give AI models a heartbeat**

*Unlock subjective initiative (主观能动性) in AI agents.*

</div>

---

## 一句话 / One-liner

现代大模型与 Agent 是「被动响应」的：你给它一个 prompt，它回答，然后停下。它们没有自己的节奏，不会「自己想要去做点什么」。**Heart** 给模型装上一颗持续跳动的「心脏」，让它拥有主观能动性——自发地想做、想关心、想持续、想主动出击。

Modern LLMs and agents are *reactive*: you prompt, they answer, then they stop. They have no rhythm of their own and never "want" to do anything on their own. **Heart** installs a continuously beating "heart" into a model, granting it subjective initiative — the drive to act, to care, to persist, and to reach out on its own.

---

## 为什么是 Heart / Why "Heart"

「主观能动性」是人类区别于被动工具的核心特征：人会因为内在的动机去做事，而不只是在被叫到时才反应。

一个没有心跳的 Agent，永远在等指令；一个有心跳的 Agent，会自己决定「什么时候该跳一下」。

"Subjective initiative" is the core trait that separates humans from passive tools: people act from intrinsic motivation, not only when called upon. An agent without a heartbeat is always waiting for instructions; an agent with a heartbeat decides for itself when it's time to beat.

---

## 核心理念 / Core Idea

Heart 的目标不是让模型「更会回答问题」，而是给它一个**自我维持的内在信号**——心跳。这个信号驱动着：

- **主动性 (Initiative)** — 在没有外部指令时，自己产生下一步行动的冲动。
- **持续性 (Persistence)** — 跨越单个请求，保持长期的目标与记忆的「脉搏」。
- **情感与偏好 (Affect & Preference)** — 让模型拥有「在意什么 / 不在乎什么」的内在倾向。
- **节奏感 (Rhythm)** — 自己决定何时行动、何时休息、何时改变方向。

> 如果把 Agent 比作身体，模型能力是「四肢」，而 Heart 是「心脏」。

---

## 实现：idea-engine — 三层想法引擎，两个服务

Heart 的参考实现叫 **idea-engine**，像一个人的心智一样工作：**潜意识冒想法 → 判别层过滤 + 蒸馏 → 执行层行动**。

逻辑上分三层，部署上合并为**两个服务**：

```
 潜意识 (engine.py) ──┐
 判别层 (discriminator.py) ─┴── mind.py（思维服务，一个进程）──► .ideas/*.md (new → skipped/passed)

 执行层 (hermes.py) ─────────── hermes.py（执行服务，另一个进程）──► done（结果写回事实文件夹）
```

- **潜意识层**（`engine.py`）：只负责自由冒出想法（含「欲望」，参考马斯洛需求层次），不评判。它的 `while True` 定时循环就是「心跳」本身。
- **判别层**（`discriminator.py`）：只做过滤——判断每条想法 SKIP 还是 PASS，同时负责蒸馏：老想法逐渐压缩、遗忘（遗忘 = 上下文压缩到 0，不是删除）。
- **执行层**（`hermes.py`）：处理 PASS 的想法——通过**可插拔的「身体」**去行动（默认 Hermes API Server，也可切回 `opencode`，未来可换任意平台），并把执行回报写回事实层。

> 🧠 **大脑 / 身体分离**：heart 的「想」与「记忆」（`facts/` + `.ideas/`）完全独立于执行后端；执行层只是「身体 / 途径」，可随意替换。类比：大脑通过身体去执行，身体的回报再充实记忆。Hermes 只是当前的一具身体，未来有了脑机接口，就是另一具。

---

## 快速开始 / Quick Start

### 1. 安装

```bash
git clone https://github.com/zxfpro/heart.git
cd heart
python3 -m venv .venv && source .venv/bin/activate   # 建议用 venv
pip install -r requirements.txt                        # 只需 rich；engine.py 仅用标准库
```

### 2. 配置（两个后端，都走环境变量）

heart 有两个后端依赖，分别对应「想」和「做」：

| 后端 | 用途 | 环境变量 | 说明 |
|------|------|----------|------|
| **「想」LLM** | 潜意识冒想法 + 判别层 | `HEART_BASE_URL` / `HEART_API_KEY` | 任意 OpenAI 兼容接口（OpenAI / DeepSeek / vLLM / Ollama…） |
| **「做」执行层** | 处理 PASS 的想法 | `HERMES_BASE_URL` / `HERMES_API_KEY` | Hermes API Server（OpenAI 协议，触发带工具的完整 agent）；或 `executor: opencode` 走 opencode CLI |

**最省事（一键配置）**：直接跑 `install.sh`，交互式填两个端点，自动生成 `.env` 并校验连通性，随后直接拉起服务：

```bash
./install.sh
```

**或手动**：复制 `.env.example` → `.env`，填好值：

```bash
cp .env.example .env
# 编辑 .env，填入 HEART_BASE_URL / HEART_API_KEY / HERMES_BASE_URL / HERMES_API_KEY
```

非交互式（可脚本化）用参数：`./install.sh --persona ./小鹿 --think-url https://api.xxx/v1 --think-key sk-xxx --executor hermes --executor-url http://127.0.0.1:8642 --executor-key xxx`

> ⚠️ `.env` 已被 `.gitignore` 忽略，密钥绝不会被提交。`os.environ` 优先于 `config.yaml`，所以密钥只放 `.env`。

**「做」侧二选一：**
- **Hermes API Server**（默认）：需要一个运行中的 [Hermes](https://github.com/NousResearch/hermes-agent) agent，启用它的 `api_server`（OpenAI 兼容接口）。把 `HERMES_BASE_URL` 指向它、`HERMES_API_KEY` 填它的网关 key。
- **opencode**（备用）：不想搭 Hermes 就装 [opencode](https://opencode.ai) CLI，然后在 `config.yaml` 里设 `executor: opencode`，无需 `HERMES_*` 变量。

### 3. 运行（一条命令，两个服务）

`install.sh` 配置完会直接拉起服务；日常启动用 `start.sh`：

```bash
./start.sh ./my-persona        # 思维服务 + 执行服务一起启动
```

或手动起两个进程：

```bash
python3 mind.py    ./my-persona    # 思维服务：潜意识冒想法 + 判别 + 蒸馏
python3 hermes.py  ./my-persona    # 执行服务：处理 PASS 的想法
```

> `my-persona/` 里放一个 `AGENTS.md`（人设）+ 若干事实 `.md`，heart 就围绕它们思考、行动。
> 调试：`--once` 只跑一轮；`--idea "..."` 直接喂一条想法；`--verbose` 看细节。`engine.py` / `discriminator.py` 仍可单独运行（调试用），`mind.py` 是合并后的推荐入口。

### 人设（AGENTS.md）

在每个目标文件夹放一个 `AGENTS.md` 定义「这个人是谁」。三个层都会读它：

- 潜意识：用它定语气（`engine.py` 注入 prompt）
- 判别层：用它定身份做判断（`discriminator.py` 注入 prompt）
- 执行层：用它定身份去行动（`hermes.py` 把 persona 注入执行 prompt）

一个 `AGENTS.md` 同时管三个脑。想换人设，换个文件夹 + 换个 AGENTS.md 即可。

### 产物（.ideas/）

想法在 `<folder>/.ideas/` 下，每个想法一个 `.md`（frontmatter 存元数据 + 状态）：

```markdown
---
type: idea
method: 比喻
parent_kind: fact
parent: SKILL.md
seed: 结论树 / 实践反向修正
ts: 2026-08-21T10:41:17Z
status: skipped
verdict: SKIP: 只是想想，不需要行动
---

把 axon 比作珊瑚礁：...
```

状态流：`new`（潜意识）→ `skipped` / `passed`（判别层）→ `done`（执行层）；蒸馏时 `distill` 递增，到 `distill_max` 后 `forgotten`（压缩到 0）。

- **树结构**：事实彼此独立是根；想法通过 `parent_kind`+`parent` 挂树。`python3 engine.py /folder --tree` 查看。
- **想法与事实地位等同**：分开放只为区分「想法 vs 事实」，都作为原料参与生成。
- **执行回报 = 新事实**：执行层做完后，其回复会写回 `facts/`（`执行-<时间戳>.md`），作为「感官反馈」进入下一轮上下文。

### 配置 config.yaml

| 键 | 含义 |
|----|------|
| interval | 思维服务 tick 间隔（秒） |
| methods | 思维方式列表（含「欲望」） |
| fact_weight / idea_weight | 事实/想法的触发权重 |
| recency_half_life | 新旧衰减半衰期（秒） |
| distill_age | 想法多久后开始蒸馏（秒） |
| distill_max | 蒸馏到第几轮后遗忘 |
| base_url / api_key / model / temperature | 「想」用 LLM 接口（环境变量 HEART_BASE_URL / HEART_API_KEY） |
| executor | 执行层「身体」：`hermes`（默认）/ `opencode` |
| hermes_base_url / hermes_api_key / hermes_model | Hermes API Server 连接（环境变量 HERMES_BASE_URL / HERMES_API_KEY） |

---

## 项目状态 / Status

🚧 **早期阶段 (Early stage)** — 已有一个可运行的三层引擎原型与示例场景，欢迎试用、反馈与共建。

🚧 **Early stage** — a runnable three-layer engine prototype with example scenarios. Feedback and contributions welcome.

---

## 路线图 / Roadmap

- [x] 三层引擎原型（潜意识 / 判别 / 执行）
- [x] 密钥与环境变量注入（HEART_BASE_URL / HEART_API_KEY）
- [x] 双服务部署（mind 思维服务 + hermes 执行服务）
- [x] 可插拔执行层（对接 Hermes API Server，大脑/身体分离）
- [ ] 主动行动触发器（proactive-action triggers）
- [ ] 长期目标与记忆脉搏（long-term goal & memory pulse）
- [ ] 可插拔的动机 / 情感模块（pluggable motivation & affect modules）
- [ ] 与其他 Agent 框架的适配层（adapters for popular agent frameworks）
- [ ] 文档、示例与评测（docs, examples & evals）

---

## 姊妹项目 / Sister Project

- 💕 **[heart-girlfriend](https://github.com/zxfpro/heart-girlfriend)** — 基于 Heart 的恋爱养成系女友项目：让一颗心跳拥有性格与情感。

---

## 许可证 / License

本项目以 **[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)** 开源——**强 Copyleft**：无论修改、分发，还是以网络服务（SaaS / API）方式运行修改版，都必须以 AGPL-3.0 向用户开源回馈。

Licensed under the **[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)** — strong copyleft: modifying, distributing, or offering a modified version as a network service (SaaS / API) all require you to open-source your changes under AGPL-3.0.

> ℹ️ **姊妹项目许可**：Heart 采用 AGPL-3.0，而 [heart-girlfriend](https://github.com/zxfpro/heart-girlfriend) 采用 MIT。若你的应用**直接包含/链接 Heart 的代码**（构成衍生作品），AGPL 的 Copyleft 可能要求该应用同样以 AGPL-3.0 开源；若仅作为**独立服务**通过 API 调用 Heart，则可保持自身许可不变。商用/闭源集成前建议先厘清二者边界。
