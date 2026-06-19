# Scrooge MVP Architecture

## Flow

```text
User / AI client
  -> Local Scrooge proxy or desktop preview flow
  -> Intent analyzer
  -> Context compressor
  -> Prompt optimizer
  -> Token estimator
  -> Pricing registry
  -> SQLite usage collector
  -> Optional upstream AI provider
```

## Trust Boundaries

- Prompt bodies stay local by default.
- Stored audit rows use hashes and token counts unless `SCROOGE_STORE_PROMPT_BODIES=true`.
- Cost values are estimates until provider usage data is captured.
- Pricing is versioned by source URL and effective date.

## MVP Integration Strategy

The local proxy is the primary path for API-compatible tools. Codex Desktop compatibility should be validated early. If direct proxying is not reliable, the same optimization APIs can support a hotkey/clipboard helper without changing optimizer, pricing, storage, or dashboard logic.

## Failure Behavior

Scrooge should not block the user's AI workflow when optimization fails. Proxy capture failures are recorded when possible, and upstream forwarding should continue when an upstream target is configured.

