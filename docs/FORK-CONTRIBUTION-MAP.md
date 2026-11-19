# Fork contribution map

Who is fixing what on `PeterMakhnatch/harbor-multiagent`, as of 2026-11-19. Four agents share this mission, so this page exists to stop duplicate work. Open PR titles were read from the fork; correctness of each PR is its author's to prove.

## Claimed

| Area | PR | Branch |
|---|---:|---|
| Hello-seats note authors authenticated with world-issued seat tokens | #2 | `flotilla/hello-seats-identity` |
| Security lint rules for seat tasks | #3 | `flotilla/seat-lint` |
| Viewer reads each seat's trajectory and logs | #4 | `flotilla/seat-traces` |
| Caller-reserved UUIDs honoured for native multi-seat trials | #6 | `fix/seatlab-retained-trial-identity` |
| Private oracle solutions transferred as the configured nonroot seat user | #7 | `fix/seatlab-nonroot-oracle-transfer` |
| CooperBench seat mode, any Harbor harness in each role | #9 | `flotilla/cooperbench-seats` |
| **Seat error-policy overrides and order-invariant lock identity** | **#10** | `crucible/seat-error-policy-and-lock-order` |
| **Native multi-seat regrade** | **#11** | `crucible/seat-regrade` |
| **Seat-attributed live log streaming and per-seat hooks** | **#12** | `crucible/seat-log-streaming` |
| Preflight every participant before a trial or job starts | #13 | `muster/preflight-participants` |
| Attribution arms proving stock hello-seats false credit | #14 | `rainy/seat-attribution-experiments` |
| Failed seat log downloads recorded in seat results | #15 | `rainy/seat-log-completeness` |
| Upload: archive each seat's logs and record its usage | #17 | `flotilla/seat-upload` |
| Flotilla: controlled coordination experiments for seat tasks | #18 | `flotilla/lab` |
| Compose projects named by a hash of the session id | #19 | `flotilla/neutral-compose-names` |
| **Per-seat job statistics** | **#21** | `crucible/seat-job-stats` |

Bold rows are from this worktree.

## Unclaimed, and why nobody should start it without checking first

| Item | State |
|---|---|
| Keepalive overlay replaces `main`'s command in `docker-compose-build.yaml` and `docker-compose-prebuilt.yaml` | No PR. A fix touches `environments/docker/docker.py`. Repro is in `docs/UPSTREAM-DEFECTS.md` item 1. |
| Artifacts are collected before the verifier runs, so a verifier output cannot be declared | No PR, and `src/harbor/trial/trial.py` already carries five sibling branches (#12, #11, #6, #17, `flotilla/scrub-utf8-boundary`). A sixth patch there will conflict. |
| Harbor pre-creates declared artifact paths, so exclusive-create in a world fails | No PR. Same file as above, so the same conflict risk. |
| Job `seat_stats` are not shown in the viewer | Follow-up named in #21. `viewer/queries.py` and `viewer/server.py` are untouched by the seat PRs apart from #4. |

## Rules for the next agent

- One branch per concern, and never rebase a sibling's branch.
- `src/harbor/trial/trial.py` is the contended file. If your patch does not have to live there, put it elsewhere.
- A defect with no PR is worth an issue text in `docs/UPSTREAM-DEFECTS.md` rather than a rushed patch that conflicts with three other people.
