# Issue tracker: GitHub specs, local tickets

Large, cross-cutting specs live in GitHub Issues in `huyxdang/three-good-boys`. Implementation tickets live as local Markdown files. Do not create a GitHub issue for each implementation ticket.

## Large specs

- Use `gh` from this repository. Before publishing, verify the target with `gh repo view --json nameWithOwner,visibility`.
- Create with `gh issue create --repo huyxdang/three-good-boys --title "..." --body-file <file>`.
- Read with `gh issue view <number> --repo huyxdang/three-good-boys --json number,title,body,labels,comments`.
- List with `gh issue list --repo huyxdang/three-good-boys --state all --json number,title,state,url` before creating a matching spec.
- Keep public specs free of restricted data, competition code, submission contents, credentials, and private execution traces.
- Update an existing matching spec instead of creating a duplicate. Implementation ticket completion does not automatically close the umbrella spec.
- Use the role strings in [triage-labels.md](triage-labels.md). Applying or creating labels requires repository permissions; record a permission failure rather than inventing a successful label change.

## Local tickets

- Store one ticket per file: `.scratch/<feature>/issues/<NN>-<slug>.md`.
- Number tickets in dependency order. Include What to build, Blocked by, Status, Owner, Progress, acceptance criteria, and Verification.
- Link the parent GitHub spec when one exists; local work does not wait for permission to publish a spec.
- Use the roles in [triage-labels.md](triage-labels.md) for Status.
- Record Progress as `not-started`, `in-progress`, `blocked`, or `done`. Status is a triage role, not a completion field.
- Claim by setting Owner and Progress before implementation. Use the same name in your personal context file.
- Start only when every listed blocker has Progress `done`. No blockers means the ticket can start immediately.
- On completion, record commands, environment, observed results, and evidence locations under Verification, then set Progress to `done`.
- Append discussion under Comments. Keep restricted evidence outside public commits; link its authorized local location instead of copying it.

## Skill routing

- "Publish tickets": create local ticket files, not GitHub issues.
- "Publish a spec": create or update the large GitHub spec.
- "Fetch a ticket": read its local file; fetch a GitHub issue only when explicitly given a GitHub spec reference.
- Ticket files are authoritative for ownership, blockers, and completion. Personal context files link tickets; they do not duplicate the backlog.

## Wayfinding

- An effort index at `.scratch/<feature>/README.md` links its parent spec and individual tickets. Do not turn the index into a second status board.
- Work the frontier: tickets that are not done, have no unfinished blockers, and have no owner. Optional experiments do not gate release unless explicitly made dependencies.
- Claim and resolve through the ticket fields above; record concise decisions and evidence in the ticket before updating your own context file.

## Pull requests as a triage surface

**PRs as a request surface: no.**
