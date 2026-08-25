# Version history & design rationale

## Why this exists

Daily AI digest cron jobs are a recurring need: produce a markdown report, push it to Feishu, done. But:

- Feishu single-message limit is **4 KB for `text`** — too small for any real digest.
- `post` messages support markdown via `tag: md` but the field name is a footgun.
- `interactive` cards support up to **30 KB** with collapsible panels — the only practical option.

This skill bundles the interactive-card path with a section-aware markdown parser, so any cron job can produce a markdown file and call one CLI to ship it.

## Evolution

| Version | What it did | Problem |
|---|---|---|
| v1 | `msg_type: text`, single message | 4 KB hard limit, content always truncated |
| v2 | `msg_type: text` + `reply_in_thread: true` via reply endpoint | markdown source leaked in plaintext |
| v3 | `msg_type: post` + `tag: md` (correct tag name) | multi-message thread — visually noisy in chat |
| v4–v12 | various fixes (multipart upload, `tag: file` failures, etc.) | interactive cards rejected with 230099 |
| v13 | `msg_type: interactive` + collapsible panels, ~28 KB target | worked but embedded 4-task-specific business logic |
| **v14** | **this skill** | stripped private paths, credentials, and 4-task white-list; open-sourced |

## Design decisions in this version

1. **`interactive` cards**, not `post` threads — single message per digest, easier to scan on mobile.
2. **`lark_md` blocks**, not raw markdown — Feishu handles escaping properly.
3. **`collapsible_panel`** per section — top_items always expanded (high signal), others collapsed.
4. **Progressive degradation** — if card exceeds 28 KB, drop lowest-priority sections first; user always sees the high-priority content.
5. **English section aliases** alongside Chinese — so the same skill serves multilingual reports without changes.
6. **No dependencies** — uses Python 3.8+ stdlib only (`urllib.request`). Easy to drop into any cron.

## What's NOT in this version (kept private on purpose)

- The original 4-task white-list (`AI行业要闻 / Agent工具链 / 技术教程与论文 / 月度Lint`) — your reports may have any section names.
- Obsidian vault parsing — this skill reads any `.md` file, not vault-specific structure.
- Multi-task batch sending — out of scope; one report per invocation.
- Cached token reuse — `get_token()` is called per invocation; if you batch-push hundreds of messages, add a cache.
