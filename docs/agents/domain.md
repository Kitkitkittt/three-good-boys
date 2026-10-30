# Domain docs

## Before exploring

- Read the root `GLOSSARY.md` when present.
- Read relevant decisions under `docs/adr/` when present.
- If absent, proceed silently without flagging the absence or creating empty documentation. Domain modeling creates these documents when terms or decisions resolve.

## Layout

Single-context: one root `GLOSSARY.md` and one `docs/adr/` directory. Team progress under `context/` is not a separate domain context. No glossary or ADR is required merely to start a ticket.

## Consumer rules

- Use glossary terms consistently in issue titles, tickets, code, tests, and documentation. When a term is missing, reconsider the terminology or note the gap for domain modeling.
- Surface conflicts with an ADR explicitly before changing its decision; name the ADR and the reason for reopening it.
- Treat current organizer documentation and the official SDK as authoritative over handoff proposals. Resolve disagreements before pinning an implementation contract.
- Distinguish observed results, reported historical results, and proposals. A valid submission format does not establish task accuracy or target-hardware compliance.
- Read the shared context entry point for source locations and privacy rules; personal progress logs are not domain specifications.
