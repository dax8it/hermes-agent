---
sidebar_position: 13
title: "Lean Continuation"
description: "Use /lean to start fresh with compact continuity instead of replaying a whole transcript"
---

# Lean Continuation

`/lean` starts a fresh Hermes session and seeds the first turn with a compact handoff prompt. It carries the previous session id forward, asks the agent to avoid full transcript replay, and tells it to recover only the facts needed for the next step.

Use it when a session is getting noisy, expensive, or close to compaction, but you still want continuity.

```text
/lean
/lean RFP response work
/lean SOW drafting and research analysis
```

## What It Does

`/lean` is a small harness pattern:

1. Capture the current session id.
2. Start a new session.
3. Send a concise handoff prompt as the next agent turn.
4. Ask the agent to recover targeted continuity only.

That keeps the new context focused on what changed, current decisions, validation results, and the next action.

## Why It Helps

More context is not always better context. Long sessions can accumulate stale branches, debug output, repeated summaries, and tool schemas. A lean continuation gives the agent a clean working window while preserving the continuity anchors that matter.

The command is useful with or without a memory provider. With no memory provider, it tells the agent to use session search or ask for missing essentials. With Total Recall installed, it can request a targeted rehydrate instead of dumping a whole old transcript back into context.

## Configure the Handoff

Add a `lean_handoff` block to the profile config you want to customize:

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

Set `total_recall.mode: off` if you do not use Total Recall and want the prompt to stay provider-neutral.

## Use With Total Recall

Total Recall is optional. Install it when you want a local continuity layer that can search, verify, and rehydrate cited context across sessions.

From PyPI:

```bash
pip install total-recall-core
total-recall hermes install --profile <profile> --activate --format text
hermes -p <profile> memory status
total-recall hermes doctor
```

From a checkout:

```bash
git clone https://github.com/dax8it/total-recall.git
cd total-recall
./scripts/install_hermes_plugin.sh --profile <profile> --activate --format text
```

After Total Recall is installed, `/lean` asks the agent to use targeted recall such as:

```text
total_recall_rehydrate focused on: active work, decisions, current state, validation results, blockers, and next action
```

The important part is the scope: recover the smallest useful continuity packet, not the full old transcript.

## Port the Pattern to Another Harness

If you are adapting this outside Hermes, keep the shape simple:

```python
old_session_id = current_session.id
new_session = start_new_session()
seed_next_turn(
    f"""
    Continue the previous work.

    Previous session id: {old_session_id}
    Use a concise handoff only. Do not load the full prior transcript unless asked.
    Recover only: what changed, current decisions, validation results, blockers, and next action.
    If a memory provider is available, run targeted recall for those items.
    """
)
```

Make the focus, recall query, known state, next action, and memory-provider behavior configurable per profile. That lets an orchestrator profile stay broad while specialist profiles carry narrower continuity rules.

