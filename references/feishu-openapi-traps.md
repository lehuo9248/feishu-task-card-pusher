# Feishu OpenAPI traps (踩坑档案)

Hard-won lessons from real cron runs. **Read this before wiring your own.**

---

## 1. `tag: md` not `tag: markdown` (in `post` messages)

`msg_type: post` supports markdown, but the **tag name is `md`**, not `markdown`.

```json
{
  "msg_type": "post",
  "content": "{\"zh_cn\":{\"content\":[[{\"tag\":\"md\",\"text\":\"# Title\n\nbody\"}]]}}"
}
```

`tag: markdown` → returns `code 230001: message_content has wrong tag:{markdown}`. We lost an hour on this.

This skill uses `msg_type: interactive`, which is different — there the tag is `lark_md`.

## 2. `root_id` field is silently ignored (use reply endpoint)

If you `POST /im/v1/messages` with `{ "root_id": "om_xxx" }` in the body, **Feishu stores the message but the UI does not thread it under om_xxx**. It looks like a standalone message.

To put a message in a thread, use the **reply endpoint**:

```
POST /im/v1/messages/{parent_message_id}/reply
Body: { "msg_type": "text", "content": ..., "reply_in_thread": true }
```

The `root_id` field is bookkeeping; the reply endpoint is the real signal.

## 3. Card `tag: file` rejected with 230099

If you upload a `.md` file via `/im/v1/files` (file_type=`stream`) and try to embed it in an interactive card with `tag: file`, you get `code 230099 parse card json err`. The `file` tag is not supported in this position.

Workaround: inline the markdown content in `tag: lark_md` blocks. Use the file upload only for genuinely binary attachments (images, PDFs).

## 4. `card.json` must NOT include `msg_type` inside `content`

```json
// WRONG — double msg_type, Feishu parses content as empty
{
  "msg_type": "interactive",
  "content": "{\"msg_type\":\"interactive\",\"card\":{...}}"
}

// RIGHT — content is just the card
{
  "msg_type": "interactive",
  "content": "{\"card\":{...}}"
}
```

When `content` is a stringified JSON, it must contain ONLY the card, not the outer envelope.

## 5. `header.template` constants

`header.template` accepts: `blue, indigo, wathet, green, turquoise, yellow, orange, red, carmine, violet, purple, grey`. Anything else returns `code 230099`.

## 6. `tenant_access_token` expires in 2 hours

Cache it per run. This skill obtains one fresh token per invocation — that's fine for single-shot pushes. For high-throughput batch sending, implement a token cache with refresh logic.

## 7. Apps must be **published** to send messages

A new app with `im:message` scope configured will return `code 230006` until you go to "Version Management" and create+publish a version. Self-service apps often skip review; corp apps may need admin approval.

## 8. `chat_id` must be lowercase `oc_xxx`

Feishu chat IDs are case-sensitive. Mixing case will get you 99992402 "chat not found".

## 9. QPS limits

`im/v1/messages` is rate-limited at ~50 QPS per app per chat. If you're sending 20 messages in a row, add a `time.sleep(0.2)` between calls (this skill does it). Don't burst 100+ messages or you'll get 429 throttling.

## 10. `lark_md` does not support HTML

You can use `**bold**`, `*italic*`, `[link](url)`, headings, lists, code blocks, tables — but NOT `<table>`, `<div>`, `<span>`, or any HTML tag. Use GFM-style markdown only.
