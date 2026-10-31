# Extending Hermes: pre_tool_call plugins (tool-interception guardrails)

Verified live pattern (production guardrail plugin). Docs: `website/docs/user-guide/features/plugins.md` and `features/hooks.md` in the agent repo.

## When to use

You need code to run BEFORE every execution of a specific tool (e.g. validate `delegate_task` spawns against a policy, block dangerous calls) — with the ability to BLOCK the call and return the reason to the model. Not for passive logging (gateway/shell hooks cover that) — pre_tool_call is the only layer that can enforce.

## Layout

```
~/.hermes/plugins/<name>/
├── plugin.yaml      # name, description, version
└── __init__.py      # register(ctx) — wires hooks to handlers
```

```python
def register(ctx):
    ctx.register_hook("pre_tool_call", my_guard)

def my_guard(tool_name: str, args: dict, task_id: str = "", **kwargs):
    if tool_name != "delegate_task":
        return  # no directive = call proceeds
    ok, reason = validate(args)
    if not ok:
        return {"action": "block", "message": reason}  # returned to the model as the tool error
    # returning None = proceed
```

Return contract: `{"action": "block", "message": str}` blocks (message = the tool error the model sees); `{"action": "approve", ...}` escalates to the human-approval gate; `{"action": "modify", "args": {...}}` shallow-merges into tool args. Precedence across plugins: block > approve > modify > none.

## Durable platform facts

- **Plugins survive agent updates.** Plugins live in `~/.hermes/plugins/`; agent updates rewrite `~/.hermes/hermes-agent/` — separate trees. Only real risk: hook API changes in a new agent version → pin the install source commit and re-verify after upgrades.
- **General plugins are opt-in**: discovered but inert until the plugin name is in `plugins.enabled` in `~/.hermes/config.yaml`.
- **Install from a git repo** (your own repo can be the source of truth): `hermes plugins install <owner>/<repo> --ref <full-commit-pin>`.
- **Processes pick up plugins at start.** A plugin installed after a running gateway/CLI session started is NOT active in it — restart the gateway/session to arm it. Verify with a cheap real call before trusting enforcement.
- **Fail-closed for pre_tool_call**: a callback that raises or exceeds the hook timeout blocks the tool call (with a message naming the callback) instead of letting it through. Belt-and-suspenders: wrap your own body in try/except returning block.
- **Gateway event hooks** (`~/.hermes/hooks/<name>/` with HOOK.yaml + handler.py) are a different, trusted-by-placement system without the opt-in gate — wrong choice for enforcement you want consciously enabled.

## Pitfalls

- Validate cheap and delegate the rest: have the hook shell out to (or reuse) an existing policy checker instead of reimplementing its logic — two sources of truth drift.
- For spawn-guardrails, prefer a **dry-run** validation mode of the policy checker, not its full mutating run — a guard that reserves resources on behalf of the caller guarantees a conflict with the caller's own later real reservation.
- Parse structured markers from tool `args` (e.g. a required first line of the `goal` string) with a tolerant-but-explicit format: unknown shapes → block with a machine-readable reason code in strict mode, log-and-pass in permissive mode until the format stabilizes.
- Shell hooks (config.yaml `hooks:` block) can also implement pre_tool_call, but they receive payloads as text — for structured args parsing and testable units prefer a Python plugin.
