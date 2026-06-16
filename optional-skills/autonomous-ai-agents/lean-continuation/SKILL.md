---
name: lean-continuation
description: Design, install, or customize a /lean continuation command for Hermes-style agent harnesses. Use when reducing token bloat, restarting long sessions with compact continuity, wiring optional Total Recall rehydrate/search, or adapting the pattern to another local agent stack.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [continuity, token-management, session-handoff, total-recall, slash-command]
    related_skills: [honcho, subagent-driven-development]
---

# Lean Continuation

Use this skill to add or adapt a `/lean` command: a fresh-session restart that preserves compact continuity without replaying the whole old transcript.

## Goal

`/lean` should:

- Capture the previous session id.
- Start a new session.
- Seed the next turn with a compact handoff prompt.
- Tell the agent to recover only the facts needed for the next action.
- Use Total Recall when available, but work without it.

## Recommended Handoff Shape

Use this prompt structure as the default:

```text
Continue {focus}.

Use a concise handoff only. Do not load the full prior transcript unless I explicitly ask.

Continuity rules:
- Previous session id: `{previous_session_id}`
- If Total Recall tools are available, first run a targeted rehydrate focused on: active work, decisions, current state, validation results, blockers, and next action.
- Prefer compact Total Recall/session-search evidence over full resume or full transcript dumps.
- If recall is unavailable, proceed from the known state below and ask only for missing essentials.

Current known state:
- Start from the previous session's durable facts, not the whole transcript.
- Prefer verified continuity, compact recall, and current local state over stale chat history.

Next action:
Verify what changed since the previous session, then continue with the smallest useful next step.
```

If Total Recall is disabled or not installed, replace the Total Recall line with:

```text
- Do not assume Total Recall is installed. Use normal session search or ask for a compact handoff if continuity is missing.
```

## Hermes Implementation Checklist

1. Add a slash command named `lean`, with aliases such as `leannew` and `newlean`.
2. In CLI mode, capture the old session id, call the normal new-session/reset path, then queue the handoff prompt as the next agent seed.
3. In gateway/chat-adapter mode, capture the old session id for the source, run the normal reset handler, then rewrite the event text to the handoff prompt and continue into the agent.
4. Put the handoff text in a small helper module so CLI, Telegram, Discord, and other adapters share the same behavior.
5. Make the handoff configurable per profile.

## Profile Config

Expose these keys:

```yaml
lean_handoff:
  default_focus: the previous project work
  recall_query: active work, decisions, current state, validation results, blockers, and next action
  current_state:
    - Start from durable facts, not the whole transcript.
    - Prefer verified continuity and current local state over stale chat history.
  next_action: Verify what changed, then continue with the smallest useful next step.
  total_recall:
    mode: auto
```

Set `total_recall.mode: off` for a provider-neutral handoff.

## Optional Total Recall Install

Total Recall is optional. If the user wants verified, local continuity across sessions, install it as the Hermes memory provider.

From PyPI:

```bash
pip install total-recall-core
total-recall hermes install --profile <profile> --activate --format text
hermes -p <profile> memory status
total-recall hermes doctor
```

From a local checkout:

```bash
git clone https://github.com/dax8it/total-recall.git
cd total-recall
./scripts/install_hermes_plugin.sh --profile <profile> --activate --format text
```

When available, prefer `total_recall_rehydrate` for session-specific restart context and `total_recall_search` for targeted lookup. Keep queries narrow.

## Verification

After installing or changing `/lean`, verify:

- `/commands` or command registry lists `lean`.
- `/lean` starts a new session and carries the previous session id into the handoff.
- `/lean some focus` uses `some focus` as the continuation focus.
- Telegram or gateway adapters execute the same handoff path.
- If Total Recall is installed, `hermes -p <profile> memory status` passes.
- If Total Recall is not installed, the prompt stays useful and provider-neutral.

## Operating Rule

Never use `/lean` as a reason to dump an entire transcript into the new session. The point is a fresh window with targeted continuity.

