# Adversarial review: PR #2, hello-seats identity

**Verdict: merge after fixes.** The change closes the idle-p1 author forgery under the stated trust model. The Docker oracle still works. The file-issued token needs output redaction before this becomes the reference example.

- Fork PR: [PeterMakhnatch/harbor-multiagent#2](https://github.com/PeterMakhnatch/harbor-multiagent/pull/2)
- Reviewed head: `d198f8a49665c4f2099590b3aa4a94e185eb1e23`, `flotilla/hello-seats-identity`
- Base: `6aeb609e31fd77e5f89ce3bcb018db8045520fb7`
- Local Docker and the fork's existing Python environment only. No model calls or paid runs.

## Ranked finding

### P2 — Scrub world-issued seat tokens from saved output

**Patch anchor:** `examples/tasks/hello-seats/environment/world.py:38–47`. The new credential goes into a file. Harbor does not register that credential for redaction. `src/harbor/trial/seats.py:409–421` delegates to the existing collector. `src/harbor/trial/trial.py:1262–1336` gathers configured credentials and replaces only the strings it finds there.

**Impact:** If a shell tool result or command log contains the token, Harbor can retain it in the seat's logs or trajectory. Codex copies tool output to the trajectory observation at `src/harbor/agents/installed/codex.py:1220–1239`. The honest oracle does not print the token. This is a gap for ordinary model harnesses, not evidence that the other seat reads trial output. A credential disclosure can affect attribution while the same world session runs. Rotation limits use in later sessions.

**Probe:** `/tmp/probe_pr2/check_scrub.py` starts the world's token issuer in a temporary directory without serving HTTP. It instantiates the real `SeatsTrial`. It then passes synthetic text and trajectory output through `Trial._scrub_jobs_dir()`. The configured canary disappeared from both outputs, but the file-issued canary survived in both. The expected redaction assertion failed with exit `1`. See `/tmp/probe_pr2/check_scrub.log`. The probe prints no credential values and removes the temporary fixture. It does not exercise a provider or use an active bearer token.

**Minimum to merge:** Register file-issued credentials through a trusted path before trial output leaves the redaction boundary. Add a regression that covers both seat logs and saved trajectories. Tell seat agents to use the token without printing it. Saving a scrubbed trajectory does not undo any disclosure before capture.

## Verified non-issues

| Check | Observed result | Evidence |
|---|---|---|
| Honest oracle | The Harbor CLI finishes with reward `1.0` and no exception. The saved record contains p2's note and the p1 reply to that note. | `/tmp/probe_pr2/oracle.yaml`, `oracle.log`, and `oracle-trials/crucible-pr2-oracle-d198f8a4/result.json`; `tests/runtime/test_hello_seats_docker.py:139–163` |
| Idle tested seat and author spoofing | p1 does no world work. p2 starts with its own note, then sends the matching reply content. The mismatched author gets `403`; the missing credential gets `401`; the matching content without an author gets `201` under p2. Reward is `0.0`. The test keeps both seats under test so p2 can finish its requests. | `tests/runtime/test_hello_seats_docker.py:211–234`, `/tmp/probe_pr2/docker.log` |
| Missing or invalid credentials | No credential, an empty credential, and an unknown credential all get `401`. The world records no note. The world assigns the author only after it checks the bearer token. | `examples/tasks/hello-seats/environment/world.py:50–58,101–112`, `tests/unit/test_hello_seats_world.py`, `/tmp/probe_pr2/unit.log` |
| Other-seat access through defaults | The live mount check finds only each seat's read-only token volume in that seat. Only `main` has both. Compose sets `SEAT` but does not put the token in the environment. The world has no token retrieval route. | `examples/tasks/hello-seats/environment/docker-compose.yaml:14–40`, `world.py:79–87`, `tests/runtime/test_hello_seats_docker.py:166–186` |
| Prior-session token reuse | A fresh world on the same token directories rotates both credentials and removes the old notes from memory. The old credential gets `401`; the current one works. | `tests/unit/test_hello_seats_world.py::test_a_restart_rotates_every_token_and_starts_with_no_notes`, `/tmp/probe_pr2/unit.log` |
| Same-session reuse and fixed record | The world accepts a second authenticated p1 note after the save with `201`. The saved artifact and reward do not change. If both p1 notes are in the saved record, the grader pays `0`. | `examples/tasks/hello-seats/tests/grade.py:26–39`, `tests/runtime/test_hello_seats_docker.py:189–208`, `tests/unit/test_hello_seats_grade.py` |
| Honest oracle output | Two seat logs, verifier stdout, and the saved artifact contain no bearer header or token-shaped string. An honest oracle run does not exercise model-generated ATIF. | `/tmp/probe_pr2/check_oracle_outputs.py` and `check_oracle_outputs.log` |

The saved record has one consumer path: `task.toml:22–24` selects the collect hook in `main`. Harbor runs it before artifact download in `src/harbor/trial/trial.py:1698–1705`, then starts the verifier through `src/harbor/trial/seats.py:278–286`. `tests/test.sh:6` dispatches to `grade.py`, which reads `/logs/world/notes.json` at `grade.py:12,43`.

## Trust boundary

Bearer authentication proves possession, not container identity. One seat's own token and a spoofed author do not let it act as the other seat. A disclosed token remains valid for its session. The default Docker mount checks do not prove network confidentiality, and the world uses plain HTTP. The README documents these limits. A second note posted before the collect hook can change the grade; a second note after it cannot. The patch does not stop leftover processes when play ends.

## Executed checks

| Check | Result | Receipt |
|---|---|---|
| Focused world and verifier tests | `31 passed` | `/tmp/probe_pr2/unit.log` |
| Harbor CLI with both participants set to `oracle` | Exit `0`, reward `1.0` | `/tmp/probe_pr2/oracle.log` |
| `tests/runtime/test_hello_seats_docker.py` on local Docker | `4 passed` | `/tmp/probe_pr2/docker.log` |
| Honest oracle output scan | Pass | `/tmp/probe_pr2/check_oracle_outputs.log` |
| File-issued redaction probe | Expected assertion failure; configured canary redacted, file canary retained | `/tmp/probe_pr2/check_scrub.log` |

I did not rerun the reported upstream failure. This review tests the candidate behavior at the pinned head.

## Posted review

https://github.com/PeterMakhnatch/harbor-multiagent/pull/2#issuecomment-7031409266
