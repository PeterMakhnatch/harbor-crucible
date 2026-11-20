# PR #37 adversarial review — `fix(environments): let Docker worlds use the image command`

Repo: PeterMakhnatch/harbor-multiagent, head `955c2733` (branch `crucible/seat-world-image-cmd`), base `main` @ `6aeb609e`. OPEN, not draft. 120+/2-, 7 files.
Claim: `[environment] use_image_command=true` clears Harbor's `sh -c sleep infinity` keepalive on `main` (Docker/Podman) via a `command: null` overlay inserted before task compose, so the image `CMD` runs; explicit Compose `command:` still wins; default off = unchanged.
Method: `gh pr view/diff`, live code on `main`, PR head in /tmp worktree (removed). Tests run: PR's 6 new cases + `TestDockerComposePaths` = 15 passed; seat config/trial suites = 38 passed. No daemon/build/model spend; probes are `compose config`-level only, same as the PR's own test.

## Verdict
The Docker-Compose-V2 happy path works and default-off is safe. The breakage is around the claim's edges: the flag silently does nothing everywhere except local Docker/Podman, Podman itself is unproven, and the seat-task story (the PR's stated motivation) has a healthcheck/startup hole the new docs walk authors into.

## Ranked findings

### P1 — Silent no-op on all cloud/DinD providers (and older Harbor): world never starts, trial fails late
- `src/harbor/environments/docker/docker.py:464` (PR) is the only consumer of `task_env_config.use_image_command`. The field lives on the global `EnvironmentConfig` (`src/harbor/models/task/config.py`, PR ~+442), accepted by every provider.
- 21 environment files import the same keepalive-bearing `COMPOSE_BUILD_PATH`/`COMPOSE_PREBUILT_PATH` (daytona, gke, modal, ec2, beam, islo, langsmith, novita, runta, sbx, vercel, sail, blaxel, boxd, cwsandbox, hyperbrowser, kernel_docker, superserve, tensorlake, …); `src/harbor/environments/docker/__init__.py` even documents them as "shared … by both local Docker and Daytona DinD". None gets the overlay, no warning, no error.
- Probe (PR head): unknown `[environment]` keys are silently accepted (`EXTRA FIELD: silently accepted`), so even pre-PR Harbor runs such a task with the keepalive instead of failing fast.
- Failure mode: seat world never starts; on Docker-local the same task works, on cloud seats idle against a sleeping `main` until agent/verifier timeout. The PR body discloses "does not alter cloud providers," but disclosure ≠ behavior: a task.toml flag that is silently ignored is the worst of the three options (implement / error / ignore). Fix direction: warn or raise in non-Docker/Podman environments when the flag is set, or add the overlay to the DinD sharers.

### P1/P2 — Podman parity is claimed, never tested; `command: null` reset is dialect-specific
- Claims: config description and `docs-mintlify/tasks/configuration.mdx` (PR) both say "On Docker and Podman".
- Mechanism is `docker-compose-image-command.yaml:3` → `command: null`. The Compose spec's canonical reset is the `!reset` tag; null-clearing is compose-go (Docker Compose V2) merge behavior. podman-compose 1.x merges in Python and Harbor already special-cases it (relative-context anchor: task compose is prepended as the first `-f` file, `docker.py:447-451`), so the effective order becomes task → build → null → task again — a shape no test renders.
- The new test proves Docker only: fixture probes `docker compose version` and the test instantiates `DockerEnvironment` (`tests/unit/environments/test_docker.py`, PR ~2234-2310). No podman runtime variant, and Harbor checks no minimum Compose version anywhere in the Docker environment.
- Local status: podman not installed here, so this is **unverified**, not confirmed-broken. But as shipped, "Podman" in user docs rests on zero evidence; one podman-compose `config` rendering in CI (the runtime VM already installs podman, `pytest.yml:123`) would settle it.

### P2 — Seat startup ordering: new docs omit the healthcheck that seat `service_healthy` depends on
- Canonical seat pattern, `examples/tasks/hello-seats/environment/docker-compose.yaml`: seats `depends_on: main: condition: service_healthy`, and `main` gets its healthcheck from the same Compose block that sets `command: ["python3", "/world/world.py"]`.
- PR's new docs section ("The main container", `docs-mintlify/tasks/multi-agent.mdx`) tells authors to move the world into the image `CMD` and set the flag — with no mention of healthchecks. An author who deletes the whole `main` Compose block (command + healthcheck) and whose world image has no `HEALTHCHECK` hits: Docker `up --detach --wait` (`src/harbor/environments/docker/runtime.py:39-40`) erroring/blocking on a health-gated service with no healthcheck, or, on Podman (`supports_compose_wait=False`, runtime.py:77/117/128), seats starting before the world accepts connections.
- The PR test's seat service (`player: image: ubuntu:22.04`) has no `depends_on`, no healthcheck, and no assertion — it cannot catch any of this.

### P2 — Scope is `main` only; title/seat framing oversell, and the test's seat is confounded decoration
- The overlay clears only `services.main.command` (`docker-compose-image-command.yaml:1-3`). Seat services gain nothing (they already ran their image `CMD` — Harbor never set their command) and a world hosted in a non-`main` service gains nothing. "Let Docker worlds use the image command" reads broader than "let `main` use its image CMD"; only the multi-agent docs section title ("The main container") is accurate.
- Test smell: `[agents.player]` + the `player` service are added **only** in the `use_image_command=True` branch of the parametrize fixture, so flag-on vs flag-off cases differ in two variables, and nothing asserts anything about the seat. Per-service (seat) image resolution, seat Dockerfile build contexts (`build: ./pla
... [truncated 1857 chars]