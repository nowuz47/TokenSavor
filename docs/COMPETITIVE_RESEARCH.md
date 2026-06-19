# Competitive Research: Token Efficiency Tools

Date: 2026-06-20

## Observed Market Direction

- Headroom focuses on pre-LLM compression for tool outputs, logs, files, and RAG chunks. It exposes library, proxy, and MCP-style integration points and claims large reductions on noisy agent context.
- RTK focuses on CLI command-output compression before shell results enter coding-agent context. Its strongest fit is high-noise commands such as test runners, git output, search results, docker, and build logs.
- Reported drawbacks in the ecosystem are mostly about trust: silent compression can hide data the agent needed, and aggressive summarization can increase follow-up questions or output tokens.

## Scrooge Differentiation

Scrooge should not compete by being the most aggressive compressor first. For internal enterprise adoption, it should compete by being the most auditable optimizer:

- default preview before send
- explicit estimated/sent/measured states
- pricing-version and tokenizer-version audit trails
- protected blocks that are kept verbatim
- deterministic compression rules with named reasons
- category-level quality floors, not only average savings

## Applied Improvements

The MVP now includes command-output routing inspired by CLI compression tools:

- test-runner output summary with failing tests, assertion lines, and file references preserved
- git status summary with branch, change counts, and representative files
- search output summary with matched-file counts and representative matches
- protected block markers for requirements that must not be compressed:
  - `SCROOGE_KEEP_START` / `SCROOGE_KEEP_END`
  - `<scrooge-keep>` / `</scrooge-keep>`
  - `<!-- scrooge-keep:start -->` / `<!-- scrooge-keep:end -->`

## Next Moves

- Add command-output compression coverage to the dashboard as a distinct savings category.
- Add holdout-based measurement for output-token side effects before claiming total-cost reduction.
- Add shell integration only after preview/audit behavior is stable enough for internal use.
