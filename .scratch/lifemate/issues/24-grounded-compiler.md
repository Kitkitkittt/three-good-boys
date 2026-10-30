# 24: Grounded compiler — private evaluation only

**Parent spec:** [LifeMate competition solution #1](https://github.com/huyxdang/three-good-boys/issues/1).

**What to build:** Evaluate the optional compiler-side grounding lever in the authorized private competition workspace, without changing weights or replacing mandatory organizer validation. This public repository records the decision and gates only; it must not distribute the implementation.

**Blocked by:** Authorized private implementation/review and measured evidence from [02](02-labeled-training-evaluation.md) and [05](05-compliant-model-selection.md). Public-repository completion is not a substitute for those gates.

**Status:** ready-for-agent

**Owner:** omp-impl-grounding

**Progress:** blocked

## Scope

- Competition implementation, its catalog helper, tests and synthetic smoke driver remain private. `baseline/` was not modified.
- The optional experiment does not gate submission; [decision-order.md](../../../docs/decision-order.md) still requires measurement before retaining grounding changes or considering post-training.
- No token-level constrained-decoding integration or real-model benchmark is claimed by a validate-and-re-ask test.

## Acceptance criteria

- [x] Remove the competition implementation and its test/smoke driver from the public branch; preserve the source only in the authorized private workspace.
- [ ] Privately review catalog-derived constraints, structured validation, bounded generation attempts and explicit dependency binding against the actual runner contract.
- [ ] Privately exercise deterministic behavior and mandatory organizer validation with approved inputs.
- [ ] Measure the isolated grounding change on the frozen benchmark after tickets 02/05 permit it, recording improvement/regression or rejection without publishing restricted code or traces.

## Verification

The two reviewed GitHub repositories (`huyxdang/three-good-boys` and `Kitkitkittt/three-good-boys`) are public. The compiler described itself as mirroring organizer validation, so it is competition implementation, not sanitized control-plane code. Keeping it public violates `AGENTS.md:23`, `README.md:31` and `context/README.md:51`.

Before removal, the implementation directory and test were preserved in the existing authorized private workspace `/home/dev-01/.local/share/lifemate-integration-20261029/` as `grounding/` and `test_grounding.py`. `stat -c '%a %U %n'` observed the workspace mode/owner as `700 dev-01`. No upload, visibility change or history rewrite occurred.

Exact forward removal command run from the integration repository:

```sh
git rm services/grounding/__init__.py services/grounding/catalog.py services/grounding/compiler.py services/grounding/smoke.py services/test_grounding.py
```

All five paths were removed by Git. The package initializer and catalog helper were removed with the compiler rather than leaving a dangling import or part of the competition layer in the public tree. Historical unit/synthetic smoke results do not establish private integration, token-level constrained generation, benchmark gain or current ticket completion; their detailed implementation-derived output is not retained here.

## Comments

- Integration review reopened this ticket under `context/README.md:26`: `done` requires every acceptance criterion to hold. The implementation is retained only in the authorized private workspace, and the private review/benchmark gates remain unchecked.
- The compiler remains an optional independently evaluated experiment ([06](06-grounded-compiler-experiment.md)); grounded controller changes belong to ticket 04. Follow the accepted grounding ADRs and preserve mandatory organizer validation.
