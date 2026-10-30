# 0002: Schema-constrained decoding as a grounding lever

**Status:** accepted

## Context

Tool calls are validated against per-sample JSON schemas, and invalid proposals are rejected by the
simulator. Schema- or grammar-constrained generation changes decoding rather than weights. Reducing
schema-invalid output is a hypothesis to benchmark, not an observed result. Constrained decoding does
not guarantee the right tool choice, identifiers, clarification or ordering: a schema-valid call can
still be semantically wrong.

## Decision

Schema- or grammar-constrained decoding for tool calls is a grounding/compiler-side lever and sits first
in the Phase 4 order, ahead of prompt corrections, lookup broadening and clarification policy. It
changes decoding, not weights. Benchmark it as a single change against the frozen cases and retain it
only for a measured improvement without regression. Schema validation remains mandatory even when
decoding is constrained; constrained generation must not hide semantic errors. If the chosen engine
lacks a usable JSON Schema subset, drop this lever rather than claiming it works.

## Consequences

- Any reduction in tool-call format failures or invalid states remains to be measured; there is no
  assumed syntax gain or semantic correctness guarantee.
- Correctness still depends on validator behavior and semantic decisions; constrained decoding is a
  candidate improvement on top of validation, never a substitute for it.
