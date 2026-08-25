"""
feishu_task_card.py - push a markdown report to Feishu as an interactive card.

Usage:
    python feishu_task_card.py <report_md_path> <chat_id> <title>

Required env vars (or .env):
    FEISHU_APP_ID
    FEISHU_APP_SECRET

Card constraints (Feishu hard limits):
    - <= 30,000 bytes (~28,000 to leave headroom)
    - <= 50 elements
    - Markdown via `tag: lark_md` blocks
    - Collapsible sections via `tag: collapsible_panel`

See README.md for setup, references/cron-prompt-template.md for
how to wire this into a scheduled job.
"""
import os
import sys
import json
import argparse
import re
import time
from collections import OrderedDict


# ---------- 1. Credentials ----------

def load_env(env_path=None):
    """Load a flat .env file. Returns dict. Never echoes values."""
    env = {}
    path = env_path or os.path.expanduser("~/.env")
    if not os.path.isfile(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def get_token(app_id, app_secret):
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib_request(
        "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=data,
    )
    with req.open(timeout=15) as r:
        resp = json.loads(r.read().decode("utf-8"))
    if resp.get("code") != 0:
        raise RuntimeError(f"tenant_access_token failed: {resp}")
    return resp["tenant_access_token"]


def urllib_request(method, url, data=None):
    import urllib.request
    headers = {"Content-Type": "application/json; charset=utf-8"}
    body = data if data is None else (data if isinstance(data, bytes) else data.encode("utf-8"))
    return urllib.request.Request(url, data=body, headers=headers, method=method)


# ---------- 2. Markdown section parser ----------

DEFAULT_SECTIONS = [
    # (canonical_key, display_title, color_template, priority 1-9 lower=trim first)
    ("summary",       "📋 Summary",        "blue",   10),
    ("top_items",     "📰 Top items",      "blue",   6),
    ("trends",        "🔍 Trends",         "purple", 7),
    ("risks",         "⚠️ Risks",          "red",    5),
    ("actions",       "🎯 Actions",         "green",  8),
    ("history",       "📅 History",         "blue",   2),
    ("metrics",       "📈 Metrics",         "orange", 3),
    ("cross_table",   "📊 Cross-table",     "blue",   4),
    ("tomorrow",      "🌅 Tomorrow",        "orange", 9),
    ("keywords",      "🔑 Keywords",        "blue",   1),
]
METADATA_SECTIONS = {"sources", "indexing_log", "failure_log", "notes", "references"}

ALIASES = {
    "summary":     ["summary", "当日摘要", "今日摘要"],
    "top_items":   ["top items", "要闻", "top n", "top 5", "详细内容"],
    "trends":      ["trends", "趋势分析", "趋势"],
    "risks":       ["risks", "风险提示", "风险"],
    "actions":     ["actions", "行动建议", "建议"],
    "history":     ["history", "历史对比", "对比"],
    "metrics":     ["metrics", "跟踪指标", "指标"],
    "cross_table": ["cross-table", "cross_table", "跨条目总结表", "总结表", "总表"],
    "tomorrow":    ["tomorrow", "明日关注", "明日"],
    "keywords":    ["keywords", "今日关键词", "关键词"],
}


def parse_sections(md_text):
    """Split markdown by ## headers, map to canonical keys via ALIASES.
    Returns OrderedDict { canonical_key: text }. Drops YAML frontmatter.
    Sections not matching any alias go to '_other'.
    """
    sections = OrderedDict()
    lines = md_text.splitlines()

    # skip frontmatter
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1:]
                break

    current_key = "_preamble"
    current_buf = []

    def flush(key, buf):
        text = "\n".join(buf).strip()
        if not text:
            return
        if key == "_preamble":
            # pre-## text becomes summary if non-empty
            sections["summary"] = sections.get("summary", "") + ("\n" if "summary" in sections else "") + text
        elif key in METADATA_SECTIONS:
            sections[f"_metadata_{key}"] = text
        else:
            sections[key] = sections.get(key, "") + ("\n" if key in sections else "") + text

    for line in lines:
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            flush(current_key, current_buf)
            current_buf = []
            raw = re.sub(r"^\d+\.\s*", "", m.group(1).strip())
            if raw in METADATA_SECTIONS:
                current_key = raw
            else:
                match = None
                raw_lower = raw.lower()
                for canon, aliases in ALIASES.items():
                    if raw_lower in [a.lower() for a in aliases] or any(a.lower() in raw_lower for a in aliases):
                        match = canon
                        break
                current_key = match or f"_other_{raw}"
        else:
            current_buf.append(line)
    flush(current_key, current_buf)

    # de-dup summary
    if "summary" in sections and len(sections["summary"].strip()) == 0:
        del sections["summary"]
    return sections


# ---------- 3. Card builders ----------

MAX_ELEMENTS = 50
MAX_BYTES = 30000
TARGET_BYTES = 28000
HEADER_TEMPLATE = "blue"
API = "https://open.feishu.cn/open-apis/im/v1/messages"


def make_collapsible(title, color, md_text, expanded=False):
    return {
        "tag": "collapsible_panel",
        "expanded": expanded,
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": color,
        },
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": md_text}}],
    }


def make_card(elements, header_title):
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": HEADER_TEMPLATE,
            "title": {"tag": "plain_text", "content": header_title},
        },
        "elements": elements,
    }


def card_bytes(card):
    return len(json.dumps(card, ensure_ascii=False).encode("utf-8"))


def count_elements(node):
    if isinstance(node, dict):
        c = 1 if node.get("tag") else 0
        for v in node.values():
            if isinstance(v, list):
                c += sum(count_elements(x) for x in v)
        return c
    if isinstance(node, list):
        return sum(count_elements(x) for x in node)
    return 0


def build_card(sections, header_title):
    """Translate parsed sections into an interactive card with
    progressive degradation: drop low-priority sections first until
    the card fits the byte/element limits.
    """
    # priority-ordered list of canonical keys
    canon_by_priority = sorted(
        [(k, c) for k, _, _, c in DEFAULT_SECTIONS],
        key=lambda kv: -kv[1],  # high priority first
    )

    elements = []
    notes_log = []

    # top_items panel always expanded (priority 6)
    if "top_items" in sections:
        elements.append(make_collapsible("📰 Top items", "blue", sections["top_items"], expanded=True))
    elif "_other_top_items" in sections:
        elements.append(make_collapsible("📰 Top items", "blue", sections["_other_top_items"], expanded=True))

    # add other sections in priority order
    for canon, _priority in canon_by_priority:
        if canon == "top_items":
            continue  # already added
        if canon in sections and sections[canon].strip():
            color = next((c for k, _, c, _ in DEFAULT_SECTIONS if k == canon), "blue")
            title = next((t for k, t, _, _ in DEFAULT_SECTIONS if k == canon), canon)
            elements.append(make_collapsible(title, color, sections[canon], expanded=False))

    # add unknown sections as flat markdown divs
    for k, v in sections.items():
        if k.startswith("_other_") and v.strip():
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": v}})

    # byte check + trim
    card = make_card(elements, header_title)
    b = card_bytes(card)
    e = count_elements(card)
    while (b > TARGET_BYTES or e > MAX_ELEMENTS) and len(elements) > 1:
        # drop last element (lowest priority first because we built priority-first)
        dropped = elements.pop()
        notes_log.append(f"dropped 1 element (priority tail) to fit; was: {dropped.get('tag','?')}")
        card = make_card(elements, header_title)
        b = card_bytes(card)
        e = count_elements(card)

    # last-resort: trim the expanded top_items content
    if b > TARGET_BYTES and elements:
        for el in elements:
            if el.get("tag") == "collapsible_panel":
                inner = el.get("elements", [])
                while inner and b > TARGET_BYTES:
                    inner.pop()
                    card = make_card(elements, header_title)
                    b = card_bytes(card)
                    notes_log.append("trimmed 1 div from top_items")
                break

    return card, notes_log


# ---------- 4. Send ----------

def send_card(card, chat_id, token):
    payload = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    req = urllib_request(
        "POST",
        f"{API}?receive_id_type=chat_id",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read().decode("utf-8"))
    if resp.get("code") != 0:
        raise RuntimeError(f"send failed: {resp}")
    return resp["data"]["message_id"]


# ---------- 5. Main ----------

def main():
    p = argparse.ArgumentParser(description="Push a markdown report to Feishu as an interactive card.")
    p.add_argument("report_path", help="Path to the markdown report")
    p.add_argument("chat_id", help="Feishu chat_id (oc_xxx)")
    p.add_argument("--title", required=True, help="Card header title (e.g. 'Daily AI Digest - 2026-08-23')")
    p.add_argument("--env", default=None, help="Path to .env with FEISHU_APP_ID/SECRET")
    args = p.parse_args()

    env = load_env(args.env)
    app_id = env.get("FEISHU_APP_ID")
    app_secret = env.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        sys.exit("FEISHU_APP_ID / FEISHU_APP_SECRET missing (set in .env or env vars)")

    md = open(args.report_path, "r", encoding="utf-8").read()
    sections = parse_sections(md)
    card, notes = build_card(sections, args.title)

    b = card_bytes(card)
    e = count_elements(card)
    print(f"[card] bytes={b} elements={e}", file=sys.stderr)
    for n in notes:
        print(f"[trim] {n}", file=sys.stderr)

    token = get_token(app_id, app_secret)
    # immediately drop the secret from memory
    del app_id, app_secret
    print("[token ok]", file=sys.stderr)

    msg_id = send_card(card, args.chat_id, token)
    del token
    print(f"[sent] message_id={msg_id}", file=sys.stderr)
    print(msg_id)


if __name__ == "__main__":
    main()
