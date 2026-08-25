# feishu-task-card-pusher

把 Markdown 报告推送到飞书成可交互卡片。Push markdown reports to Feishu as interactive cards.

单条上限 28 KB / 50 元素（28 KB / 50 elements max. Feishu hard limits）。为每日 AI 摘要定时任务而设计（Built for daily AI digest cron jobs）。

---

## 它做什么

把一份本地 Markdown 报告（如每日 AI 要闻 / 工具链更新 / 论文摘要），翻译成飞书 interactive card 推送到指定 chat。

```
本地 .md 报告 → 脚本读入 → 按 ## 节拆分 → 映射到 10 个标准 section
                → 折叠面板 (collapsible_panel) 装填 → 拼 28 KB 大卡片 → 推飞书
```

每张卡片 ≤ 30 KB / ≤ 50 元素（飞书硬墙）；超出时按优先级自动砍低价值 section。

---

## Setup（必做，5 步）

### 1. 准备飞书应用

去 [飞书开放平台](https://open.feishu.cn) 注册开发者账号：

1. **创建企业自建应用** → 拿 `App ID` 和 `App Secret`
2. **开启机器人能力**：应用详情页 → 机器人 → 启用
3. **添加权限**（权限管理）：
   - `im:message`
   - `im:message:send_as_bot`
   - `im:message.group_at_msg`（如要 @ 群成员）
   - `im:message:readonly`（只读历史消息，可选）
4. **获取 chat_id**：
   - 把机器人加入目标群 / 私聊
   - 用飞书 API 调试台（[open.feishu.cn/api-explorer](https://open.feishu.cn/api-explorer)）调 `GET /im/v1/chats` 查 chat_id
   - 形如 `oc_17cb58beda1b4fdcb8d2e86ad1e4e252`
5. **发布应用**：版本管理与发布 → 创建版本 → 提交审核（个人应用一般免审）

### 2. 安装依赖

```bash
git clone https://github.com/lehuo9248/feishu-task-card-pusher
cd feishu-task-card-pusher
pip install -r requirements.txt  # 见下
```

**仅依赖 Python 3.8+ 标准库**（`urllib.request`）。`requirements.txt` 仅声明版本下限：

```
# requirements.txt
# 仅用于声明 Python 版本下限；无第三方依赖
```

### 3. 写入凭证

**方式 A — 环境变量**（推荐）：

```bash
export FEISHU_APP_ID="cli_xxxxx"
export FEISHU_APP_SECRET="xxxxx"
```

**方式 B — `.env` 文件**：

```bash
cp .env.example .env
# 编辑 .env 填入真值
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
```

> **⚠️ 千万不要把 `.env` 提交到 Git**。`.gitignore` 已默认排除。

### 4. 准备报告

你的报告应是 Markdown，有 frontmatter + 多个 `##` 节。例如：

```markdown
---
title: AI Digest 2026-08-23
date: 2026-08-23
---

## Summary
One-paragraph overview.

## Top items
1. **Anthropic raised $65B** at a $965B valuation ...
2. **OpenAI IPO** in 2027 ...
3. **DeepSeek price cut** ...

## Trends
The AI funding bubble is widening ...

## Risks
Revenue growth is slowing ...

## Actions
Review your cloud cost projections this week.

## Sources
- https://...
```

脚本会自动识别 section（支持中英文别名），塞进折叠面板。

### 5. 跑起来

```bash
python scripts/feishu_task_card.py path/to/report.md oc_your_chat_id \
  --title "AI Digest - 2026-08-23"
```

**CLI 参数**：

| 参数 | 必填 | 说明 |
|---|---|---|
| `report_path` | ✅ | Markdown 报告路径（位置参数） |
| `chat_id` | ✅ | 飞书 chat_id（位置参数，形如 `oc_xxx`） |
| `--title` | ✅ | 卡片 header 标题 |
| `--env` | ❌ | `.env` 文件路径，默认 `~/.env` |

**输出**：

```
[card] bytes=24318 elements=24
[token ok]
[sent] message_id=om_xxx
```

`message_id` 是脚本的唯一 stdout，可被 shell 或其他工具捕获。

---

## 进阶用法

### 接入定时任务（cron）

参见 [`references/cron-prompt-template.md`](references/cron-prompt-template.md)。示例：

```cron
# 每日 07:15 跑 AI 行业要闻
15 7 * * *  python /path/to/feishu_task_card.py /path/to/digest.md oc_xxx --title "AI Digest $(date +\%F)"
```

### 支持的 Markdown 节（自动识别）

| 标准节（canonical） | 别名（aliases） | 优先级 |
|---|---|---|
| summary | 当日摘要 / 今日摘要 | 10 |
| top_items | 要闻 / Top N / Top 5 / 详细内容 | 6 |
| trends | 趋势分析 | 7 |
| risks | 风险提示 | 5 |
| actions | 行动建议 | 8 |
| history | 历史对比 | 2 |
| metrics | 跟踪指标 | 3 |
| cross_table | 跨条目总结表 / 总结表 | 4 |
| tomorrow | 明日关注 | 9 |
| keywords | 今日关键词 | 1 |

未知节（不在上表）会作为扁平 markdown div 追加。

**元数据节**（不推送）：`sources / indexing_log / failure_log / notes / references`

### 字节 / 元素超限自动降级

脚本按优先级砍节：
1. 先砍 priority 1（keywords）
2. 再砍 priority 2（history）
3. ... 一直砍到 ≤ 28 KB 且 ≤ 50 元素
4. 极端情况：保留 1 个折叠面板，其它全砍

---

## 故障排查

| 问题 | 解决 |
|---|---|
| `tenant_access_token failed` | 检查 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 是否正确，应用是否已开启机器人能力 |
| `send failed: code=230006` | 应用未发布；去飞书后台发布版本 |
| `send failed: code=99992402` | chat_id 错误或机器人不在该群 |
| 卡片超 28 KB | 检查报告内容；脚本会自动砍节 |
| Markdown 渲染失败 | 飞书 `lark_md` 不支持 HTML 表格 / 嵌套列表 / 自定义 CSS；只用标准 Markdown 即可 |

更多踩坑档案见 [`references/feishu-openapi-traps.md`](references/feishu-openapi-traps.md)。

---

## License

MIT — 见 [LICENSE](LICENSE)。

## Topics

`feishu` `lark` `feishu-bot` `markdown-to-card` `interactive-card`
