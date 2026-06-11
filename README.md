# Task Cockpit · 个人任务驾驶舱

一个由 agent 驱动的个人任务管理 skill（Claude Code）。你用自然语言把要做的事倒给 agent，它拆成任务让你审、入库，维护一个只读看板回答"该先干啥"，并在每个任务完成时即时沉淀一条可用的成就陈述，长期累积成你的述职 / 周报 / 复盘素材。

完整设计见 `docs/superpowers/specs/2026-06-11-task-cockpit-design.md`。

## 组成

- `cockpit.py` — 数据层 + CLI（全部业务逻辑，纯标准库）
- `server.py` — 本地看板服务（固定端口 7842，仅监听 127.0.0.1，无闲置超时）
- `dashboard.html` — 只读看板（每 2 秒自动刷新）
- `SKILL.md` — agent 工作流说明

数据存于 `~/.task-cockpit/`（首次使用自动创建）：`projects.json`、`tasks.json`、`achievements.jsonl`、`cv-exports/`。

## 安装

需要 Python 3（标准库即可，无第三方依赖）。将本目录软链接为 skill：

```bash
ln -s "$(pwd)" ~/.claude/skills/task-cockpit
```

之后在 Claude Code 里用自然语言触发，例如："我有几个新任务……""xx 做完了""我现在该干啥""帮我总结这周的成果"。看板地址：http://127.0.0.1:7842 。

## 用法速览

| 你说 | agent 做 |
| --- | --- |
| 倒一堆要做的事 | 拆成项目 + 任务（草稿态，看板高亮），你审核调整后确认入库 |
| "X 做完了" | 拟成果、问复盘，生成成就陈述沉淀入库（素材不足则挂起待补） |
| "我现在该干啥" | 按优先级 + 截止日给出今日聚焦建议 |
| "总结述职 / 周报 / 复盘材料" | 从成就库按用途重组（只用真实记录，不编造） |

## 测试

```bash
python3 -m unittest discover tests -v
```

## 团队分发

日后将本 skill 套入 plugin、自建 git marketplace（如托管于 GitHub），同事 `/plugin marketplace add <仓库地址>` 即可安装。每人数据各自独立存于自己的 `~/.task-cockpit/`。代码中不写死任何个人路径，开箱即用。
