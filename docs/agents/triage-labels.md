# Triage labels

| Canonical role | Label / local Status | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Requires evaluation |
| `needs-info` | `needs-info` | Waiting for information |
| `ready-for-agent` | `ready-for-agent` | Specified for agent implementation |
| `ready-for-human` | `ready-for-human` | Requires human action |
| `wontfix` | `wontfix` | Will not be actioned |

Use these strings for GitHub spec labels and local ticket Status. Read Progress and Blocked by separately; `ready-for-agent` does not mean a blocked ticket can start. Completion is recorded as Progress `done`, not as a sixth triage role.

GitHub label creation requires repository write permissions. Local Status values work independently of GitHub label availability.
