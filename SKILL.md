# feishu-task-card-pusher

Push markdown reports to Feishu as interactive cards. Built for daily AI digest cron jobs.

## When to use

When you have a markdown report on disk and want to send it to a Feishu chat as a single interactive card. Common cases:

- Daily / weekly AI news digest pushed from a scheduled job
- Toolchain update summary (Claude Code / Codex / MCP)
- Arxiv paper weekly recap
- Code review summary or lint report

## Constraints (Feishu hard limits)

- Card <= 30,000 bytes (target 28,000 to leave headroom)
- Card <= 50 elements
- Use `tag: lark_md` blocks for markdown; `tag: collapsible_panel` for foldable sections
- One message per card; multi-message threads are NOT this skill's job

## Quick start

See [README.md](README.md) — full setup walkthrough including how to obtain `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, and a `chat_id`.

CLI:

```bash
python scripts/feishu_task_card.py path/to/report.md oc_xxx --title "Daily Digest 2026-08-23"
```

## Workflow

1. Read the markdown report from disk
2. Parse `## ` sections and map them to 10 canonical section types via aliases (zh + en)
3. Drop metadata sections (`sources`, `indexing_log`, `failure_log`, `notes`, `references`)
4. Build a card with collapsible panels (top_items always expanded)
5. If card exceeds 28 KB or 50 elements, drop lowest-priority sections first
6. POST to Feishu `im/v1/messages` with `msg_type: interactive`
7. Print the resulting `message_id` to stdout

## Sections recognized

| canonical | aliases (zh + en) | priority (higher = kept first) |
|---|---|---|
| summary | 当日摘要 / 今日摘要 / summary | 10 |
| top_items | 要闻 / Top N / Top 5 / 详细内容 / top items | 6 |
| trends | 趋势分析 / trends | 7 |
| risks | 风险提示 / risks | 5 |
| actions | 行动建议 / actions | 8 |
| history | 历史对比 / history | 2 |
| metrics | 跟踪指标 / metrics | 3 |
| cross_table | 跨条目总结表 / 总结表 / cross-table | 4 |
| tomorrow | 明日关注 / tomorrow | 9 |
| keywords | 今日关键词 / keywords | 1 |

Unknown sections are appended as flat markdown divs at the end.

## References

- [README.md](README.md) — full setup
- [references/cron-prompt-template.md](references/cron-prompt-template.md) — wire into a scheduled job
- [references/feishu-openapi-traps.md](references/feishu-openapi-traps.md) — what to avoid
- [references/version-history.md](references/version-history.md) — why this exists
