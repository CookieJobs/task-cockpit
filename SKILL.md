---
name: task-cockpit
description: >
  个人任务管理助手。当用户要：管理任务/待办/计划、倾倒脑中事项、拆解工作、记录某件事完成了、
  询问现在该做什么/优先级、想看任务看板/进度、需要写述职/答辩/周报/复盘材料、
  整理成就或简历亮点时使用。
  Triggers: "帮我拆一下这些事"、"XXX 做完了"、"现在该干啥"、"帮我写述职"、
  "记一下"、"加个任务"、"任务看板"、"周报"、"复盘"、"成就"、task management,
  plan todos, mark done, what should I work on, weekly report, accomplishments.
---

# Task Cockpit — Agent Workflow

## 1. 路径与调用规则

CLI 和服务端都在本 skill 目录下。默认安装位置：`~/.claude/skills/task-cockpit/`。

调用格式（固定）：
```
python3 ~/.claude/skills/task-cockpit/cockpit.py <command> --json '<JSON>'
```

**严禁手动编辑** `~/.task-cockpit/` 下的任何 JSON/JSONL 数据文件，必须全部经由 CLI 操作。

数据目录默认为 `~/.task-cockpit/`（可通过环境变量 `TASK_COCKPIT_DIR` 覆盖）。

---

## 2. 启动 Dashboard

每次 session 首次处理任务相关请求时，确保服务端在线：

```bash
curl -s http://127.0.0.1:7842/api/health >/dev/null 2>&1 || \
  (nohup python3 ~/.claude/skills/task-cockpit/server.py >/dev/null 2>&1 &)
```

然后告知用户：**Dashboard: http://127.0.0.1:7842**

服务端无空闲超时，端口固定 7842，被杀后用同一命令重启即可，URL 不变。

---

## 3. CLI 命令速查

所有命令输出 JSON 到 stdout。

| 命令 | `--json` 必填参数 | 可选参数 | 返回 |
|---|---|---|---|
| `add-project` | `name` | — | `{id}` |
| `add-task` | `project`（proj id）, `title` | `priority`（高/中/低，默认中）, `due`（YYYY-MM-DD）, `nextAction`（字符串）, `blocked`（bool，默认 false） | `{id}` |
| `update-task` | `id`（task id），其余同 add-task 字段 | 任意任务字段 | `{ok:true}` |
| `confirm-drafts` | — | — | `{ok:true}` |
| `complete-task` | `id`（task id） | `outcome`, `reflection`, `cv`, `cv_status`（ready/pending，默认 ready） | `{id}`（achievement id） |
| `update-cv` | `id`（achievement id） | `cv`, `cv_status` | `{ok:true}` |
| `undo` | `id`（achievement id） | — | `{ok:true}` |
| `delete-task` | `id`（task id） | — | `{ok:true}` |
| `snapshot` | — | — | `{focus, projects, doneToday, counts}` |
| `achievements` | — | `project`（项目名称字符串）, `since`（YYYY-MM-DD） | `{items:[...]}` |

**关键细节：**
- `add-task` 创建的任务初始 `draft: true`（看板高亮显示）
- `complete-task` / `update-cv` 的参数用 `cv_status`（下划线），存储字段为 `cvStatus`
- `undo` 的 `id` 是 achievement id（`done_xxx`），不是 task id
- `achievements` 按 `project` 过滤时传项目**名称**（字符串），不是 proj id
- priority 合法值：`高` / `中` / `低`；task status：`未开始` / `进行中`

**示例：**

```bash
# 新建项目
python3 ~/.claude/skills/task-cockpit/cockpit.py add-project --json '{"name":"产品迭代Q3"}'

# 新建任务（草稿）
python3 ~/.claude/skills/task-cockpit/cockpit.py add-task \
  --json '{"project":"proj_xxx","title":"完成登录页改版","priority":"高","due":"2026-06-20","nextAction":"先出原型图"}'

# 确认草稿
python3 ~/.claude/skills/task-cockpit/cockpit.py confirm-drafts --json '{}'

# 完成任务，沉淀成就
python3 ~/.claude/skills/task-cockpit/cockpit.py complete-task \
  --json '{"id":"task_xxx","outcome":"登录页改版上线，跳出率降低 18%","cv":"主导登录页视觉重设计，上线后跳出率下降 18%","cv_status":"ready"}'

# 补充成就 CV
python3 ~/.claude/skills/task-cockpit/cockpit.py update-cv \
  --json '{"id":"done_xxx","cv":"主导登录页改版，A/B 测试后跳出率降 18%，DAU +5%","cv_status":"ready"}'

# 查看全局快照
python3 ~/.claude/skills/task-cockpit/cockpit.py snapshot --json '{}'

# 查询某项目成就（2026年起）
python3 ~/.claude/skills/task-cockpit/cockpit.py achievements \
  --json '{"project":"产品迭代Q3","since":"2026-01-01"}'
```

---

## 4. 核心工作流

### ① 倒事 → 拆解 → 确认

**触发**：用户列出一堆事、说"帮我整理一下"、"我要做这些事"。

1. 理解用户意图，识别项目维度。
2. 对每个新项目调用 `add-project`，获取 proj id。
3. 对每件事调用 `add-task`（你来建议 priority；blocked=true 表示被卡住无法推进）。任务创建后状态为草稿（看板高亮）。
4. 在终端展示拆解结果（表格或列表），让用户确认或调整：
   - 修改：`update-task`
   - 删除：`delete-task`
5. 用户说"就这样"/"确认"后，调用 `confirm-drafts`（清除高亮）。

```
示例对话：
用户："帮我把这些事整理一下：①写周报 ②修复登录 bug ③准备演讲 PPT（等设计出图）"
→ 你：创建 3 个任务，③ blocked=true，展示列表请用户确认
→ 用户："优先级改一下，修 bug 要最高"
→ 你：update-task 修改 priority="高"，重新展示
→ 用户："好了"
→ 你：confirm-drafts
```

### ② 推进 → 完成（沉淀成就）

**触发**：用户说"XXX 做完了"、"完成了"、"搞定了"。

1. 调用 `snapshot` 找到对应任务 id（在 `projects[].tasks` 或 `focus` 里按标题匹配）。
2. 起草一句 `outcome`（结果描述），展示给用户：
   - 用户可直接确认或修改。
3. 询问是否有复盘想法（`reflection`，可选，不强迫）。
4. **你生成 `cv`**：结合 outcome + reflection + 任务标题，写一句简历/述职级别的成就陈述（动词开头，含结果/影响）。
5. 判断 `cv_status`：
   - 有具体结果/指标 → `cv_status="ready"`，调用 `complete-task`，告知："✨ 已沉淀进成就库"
   - 结果模糊、无量化 → `cv_status="pending"`，调用 `complete-task`，然后问用户："有没有具体数据或影响可以补充？"，用户补充后调用 `update-cv` 将 cv_status 升为 "ready"

```bash
# 结果充分时
python3 ~/.claude/skills/task-cockpit/cockpit.py complete-task \
  --json '{"id":"task_xxx","outcome":"用户反馈登录 bug 已修复，无复现","cv":"定位并修复高优先级登录鉴权 bug，消除用户阻塞，当日上线验证","cv_status":"ready"}'

# 结果待补充时
python3 ~/.claude/skills/task-cockpit/cockpit.py complete-task \
  --json '{"id":"task_xxx","outcome":"PPT 已完成","cv":"准备并完成演讲 PPT","cv_status":"pending"}'
# 用户补充后：
python3 ~/.claude/skills/task-cockpit/cockpit.py update-cv \
  --json '{"id":"done_xxx","cv":"独立准备并主讲季度复盘演讲，获团队正向反馈，推动 2 项流程改进","cv_status":"ready"}'
```

### ③ 问局势 → 主动建议

**触发**：用户问"现在该干啥"、"最近有什么事"、"帮我排个序"。

1. 调用 `snapshot`。
2. 从 `focus`（最多 5 条，已按 priority + due 排序）分析：
   - 最紧迫：priority="高" 或 due 最近
   - 被卡住：`blocked=true` → 提示可暂时跳过
   - 可推进：未 blocked、有 nextAction
3. 给出 2-3 条具体建议，带理由（截止日期、优先级）。

---

## 5. 成果总结（述职 / 周报 / 复盘）

**触发**：用户说"帮我写述职"、"整理周报"、"复盘一下"、"简历亮点"。

1. 调用 `achievements`（按需传 project / since 过滤）。
2. 只使用 `cvStatus == "ready"` 的条目。如果 ready 条目太少，告知用户并建议补充。
3. 按用途重新组织，输出 Markdown 供用户复制：

**述职 / 答辩**（STAR 结构，突出影响）：
```markdown
## 核心成果

- **[任务标题]**：[cv 内容，补充背景 + 结果]
  - 背景：...  行动：...  结果：...
```

**周报 / 日报**（简洁，按项目分组）：
```markdown
## 本周完成

### 项目名
- [outcome]
- [outcome]
```

**复盘 / 成长**（用 reflection 字段，提炼教训）：
```markdown
## 成长与反思

- [任务]：[reflection]
```

**硬性规则：只使用 achievements 中真实记录的内容，绝不捏造。**  
如果素材不足，直接告诉用户哪里缺，请他补充，然后用 `update-cv` 录入，再生成报告。

导出文件（可选）：用户如需存档，可保存到 `~/.task-cockpit/cv-exports/`，不自动写入。
