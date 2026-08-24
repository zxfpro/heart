# idea-engine — 三层想法引擎

像一个人的心智：**潜意识冒想法 → 判别层过滤+蒸馏 → 执行层行动**。

```
潜意识 (engine.py)          判别层 (discriminator.py)        执行层 (hermes.py)
扫文件夹→随机思维冒想法      只过滤(SKIP/PASS) + 蒸馏/遗忘     处理 PASS 的想法，行动并把结果落回事实
   ↓                            ↓                                ↓
.ideas/*.md (new)          skipped / passed / forgotten        done（结果写回事实文件夹）
```

- **潜意识层**：`engine.py`，只负责自由冒出想法（含"欲望"，参考马斯洛需求层次），不评判。
- **判别层**：`discriminator.py`，只做过滤——判断每条想法 SKIP 还是 PASS，同时负责蒸馏：老想法逐渐压缩、遗忘（遗忘=上下文压缩到 0，不是删除）。
- **执行层**：`hermes.py`，Hermes agent，处理 PASS 的想法：探索、行动、把结果写回事实文件夹。

## 用法

三个进程各自常驻（也可只跑其中一两个）：

```bash
python3 engine.py       /path/to/folder            # 潜意识
python3 discriminator.py /path/to/folder           # 判别层
python3 hermes.py       /path/to/folder            # 执行层

# 调试：--once 只跑一轮；--idea "..." 直接喂一条；--verbose 看细节
python3 discriminator.py /path/to/folder --idea "想要一个一起吃饭的人"
python3 hermes.py        /path/to/folder --idea "把'我喜欢下雨天'记进一个心情文件"

# 后台常驻
nohup python3 engine.py       /path/to/folder > /tmp/engine.log 2>&1 &
nohup python3 discriminator.py /path/to/folder > /tmp/disc.log  2>&1 &
nohup python3 hermes.py       /path/to/folder > /tmp/hermes.log 2>&1 &
```

## 人设（AGENTS.md）

在每个目标文件夹放一个 `AGENTS.md` 定义"这个人是谁"。三个层都会读它：

- 潜意识：用它定语气（`engine.py` 注入 prompt）
- 判别层：用它定身份做判断（`discriminator.py` 注入 prompt）
- 执行层：opencode 自动读它（`hermes.py` 以该目录为 cwd）

一个 `AGENTS.md` 同时管三个脑。想换人设，换个文件夹 + 换个 AGENTS.md 即可。

## 产物

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
- **想法与事实地位等同**：分开放只为区分"想法 vs 事实"，都作为原料参与生成。

## 配置 config.yaml

| 键 | 含义 |
|----|------|
| interval | 潜意识 tick 间隔（秒） |
| methods | 思维方式列表（含"欲望"） |
| fact_weight / idea_weight | 事实/想法的触发权重 |
| recency_half_life | 新旧衰减半衰期（秒） |
| distill_age | 想法多久后开始蒸馏（秒） |
| distill_max | 蒸馏到第几轮后遗忘 |
| base_url / api_key / model / temperature | LLM 接口（潜意识 & 判别层用） |

> 接口密钥在 `config.yaml` 里，注意别把它提交进 git。
