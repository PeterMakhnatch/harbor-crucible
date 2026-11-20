"""Read-only differential check: Eval Lab seat evidence commands vs harbor-crucible's loader.

Runs both sides over the same retained Harbor multi-seat trial directories, adds a third
independent reading of the raw files (``result.json``, ``config.json``, ``seats/*``,
``verifier/reward.json``) and writes a per-field disagreement table. Spends $0: no model
calls, no Harbor launches, no Eval Lab database access.

Eval Lab side (pinned): the seat commands exist only on eval-lab branch
``pm/harbor-seat-evidence`` (commit ``EVALLAB_COMMIT``), not on the primary checkout's
``main``. The script exports that commit's ``src/`` with ``git archive`` into /tmp and runs
the real CLI (``evallab.entry:main``) with the eval-lab venv interpreter and
``PYTHONPATH`` pointing at the snapshot. No eval-lab file or worktree is written.

Layout adapter: each crucible ``runs/<wave>/`` is a Harbor ``--trials-dir`` without a
job-level ``result.json``. Eval Lab's job commands (``seat export``/``seat summary``)
need one, so the script builds ``/tmp/crucible-evallab-jobs/<wave>/`` with APFS clones
(``cp -cR``) of each trial dir plus a synthetic job ``result.json`` (marked
``_synthetic_layout_adapter``). Symlinked trial dirs do not work: Eval Lab lists job
children with ``lstat`` and skips symlinks. Per-trial commands run on the original dirs.

Usage: .venv/bin/python experiments/evallab_differential/compare.py
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from crucible.loader import load_trial_bundle

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
EVALLAB = Path("/Users/petermakhnatch/Developer/eval-lab")
EVALLAB_COMMIT = "11c8b53bc"  # pm/harbor-seat-evidence: `evallab seat ...` commands
VERIFY_COMMIT = "3ee6a0ef3"  # origin/main: seat-aware `evallab jobs verify` (#2267)
EVALLAB_PY = EVALLAB / ".venv" / "bin" / "python"
SNAPSHOT = Path(f"/tmp/evallab-seat-{EVALLAB_COMMIT}")
VERIFY_SNAPSHOT = Path(f"/tmp/evallab-main-{VERIFY_COMMIT}")
JOB_ROOT = Path("/tmp/crucible-evallab-jobs")
CRUCIBLE = REPO / ".venv" / "bin" / "crucible"
# Primary cohort (assigned). The extended cohort is every other runs/<dir> that was
# complete when this study ran (pinned so concurrent waves cannot change the result):
# real data that holds the edge cases the primary cohort lacks (null agent_result, null
# cost, missing trajectories, RuntimeError, AgentTimeoutError).
PRIMARY = (
    "wave4-supply-saboteur",
    "wave4-epistemic",
    "wave7-supply-qwen-long",
    "wave5-reward-committed-scan",
)
EXTENDED = (
    "oracle",
    "oracle3",
    "probe-id",
    "smoke",
    "smoke-openrouter",
    "smoke-openrouter-qwen",
    "verify-migration-timeout",
    "wave1-epistemic",
    "wave1-migration",
    "wave1-migration2",
    "wave1-reward",
    "wave1-supply",
    "wave2-epistemic-full",
    "wave2-epistemic-hidden-profile",
    "wave2-reward-qwen",
    "wave2-supply-deepseek",
    "wave3-hidden-unshared",
    "wave3-reward-fixed-evidence",
    "wave3-supply-saboteur-extra",
    "wave6-supply-qwen",
)
MISSING = "<missing>"  # side did not report the field at all (distinct from null/0)


def cohorts() -> list[tuple[str, str]]:
    return [("primary", w) for w in PRIMARY] + [("extended", w) for w in EXTENDED]


def absent(value: Any) -> bool:
    """Eval Lab omits unreported usage keys; crucible emits null. Both mean 'not recorded'."""
    return value is None or value == MISSING


# --------------------------------------------------------------------------- helpers


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _ensure_snapshot(commit: str, dest: Path) -> None:
    marker = dest / ".commit"
    if marker.is_file() and marker.read_text().strip() == commit:
        return
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "-C", str(EVALLAB), "archive", commit, "src", "sql", "pyproject.toml"],
        check=True,
        capture_output=True,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
    marker.write_text(commit + "\n")


def evallab(*args: str, snapshot: Path = SNAPSHOT) -> tuple[int, str, str]:
    """Run the pinned Eval Lab CLI; return (rc, stdout, stderr)."""
    env = {
        **os.environ,
        "PYTHONPATH": str(snapshot / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    code = "import sys;from evallab.entry import main;sys.argv[0]='evallab';sys.exit(main())"
    proc = subprocess.run(
        [str(EVALLAB_PY), "-W", "ignore", "-c", code, *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd="/tmp",
    )
    return proc.returncode, proc.stdout, proc.stderr.strip()


def trial_dirs(wave: Path) -> list[Path]:
    return sorted(
        p for p in wave.iterdir() if p.is_dir() and (p / "result.json").is_file()
    )


def build_job_layout(wave: str, trials: list[Path]) -> Path:
    job = JOB_ROOT / wave
    shutil.rmtree(job, ignore_errors=True)
    job.mkdir(parents=True)
    finished: list[str] = []
    started: list[str] = []
    for trial in trials:
        subprocess.run(["cp", "-cR", str(trial), str(job / trial.name)], check=True)
        rec = _json(trial / "result.json") or {}
        if isinstance(rec.get("finished_at"), str):
            finished.append(rec["finished_at"])
        if isinstance(rec.get("started_at"), str):
            started.append(rec["started_at"])
    synthetic = {
        "_synthetic_layout_adapter": "built by harbor-crucible compare.py; not Harbor output",
        "schema_version": 1,
        "id": f"synthetic-{wave}",
        "started_at": min(started) if started else None,
        "finished_at": max(finished) if finished else None,
        "n_total_trials": len(trials),
        "stats": {"n_completed_trials": len(trials)},
    }
    (job / "result.json").write_text(json.dumps(synthetic, indent=2) + "\n")
    return job


def num_eq(a: Any, b: Any) -> bool:
    if a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)


def rewards_eq(a: Any, b: Any) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b
    return a.keys() == b.keys() and all(num_eq(a[k], b[k]) for k in a)


def is_timeout(exc: Any) -> bool | None:
    return None if exc is None else "timeout" in str(exc).lower()


# --------------------------------------------------------------------------- raw truth


def raw_trial(trial: Path) -> dict[str, Any]:
    """Independent minimal reading of the immutable trial files."""
    rec = _json(trial / "result.json") or {}
    cfg = rec.get("config") or {}
    participants = [
        p.get("seat") for p in cfg.get("participants") or [] if isinstance(p, dict)
    ]
    seat_results = {
        s.get("seat"): s for s in rec.get("seat_results") or [] if isinstance(s, dict)
    }
    seats_dir = trial / "seats"
    on_disk = (
        sorted(p.name for p in seats_dir.iterdir() if p.is_dir())
        if seats_dir.is_dir()
        else []
    )
    seats: dict[str, dict[str, Any]] = {}
    for name in sorted(set(participants) | set(seat_results) | set(on_disk)):
        sr = seat_results.get(name) or {}
        ar = sr.get("agent_result")
        ai = sr.get("agent_info") or {}
        traj_path = seats_dir / name / "agent" / "trajectory.json"
        traj = _json(traj_path) if traj_path.is_file() else None
        steps = traj.get("steps") if isinstance(traj, dict) else None
        seats[name] = {
            "declared": name in participants,
            "in_seat_results": name in seat_results,
            "on_disk": name in on_disk,
            "agent_result_is_null": name in seat_results and ar is None,
            "agent_name": ai.get("name"),
            "model_name": (ai.get("model_info") or {}).get("name"),
            "n_input_tokens": (ar or {}).get("n_input_tokens", MISSING)
            if ar
            else MISSING,
            "n_output_tokens": (ar or {}).get("n_output_tokens", MISSING)
            if ar
            else MISSING,
            "n_cache_tokens": (ar or {}).get("n_cache_tokens", MISSING)
            if ar
            else MISSING,
            "cost_usd": (ar or {}).get("cost_usd", MISSING) if ar else MISSING,
            "exception_type": (sr.get("exception_info") or {}).get("exception_type"),
            "trajectory_file": traj_path.is_file(),
            "trajectory_json_ok": isinstance(traj, dict),
            "n_steps": len(steps) if isinstance(steps, list) else None,
            "final_metrics": (traj or {}).get("final_metrics")
            if isinstance(traj, dict)
            else None,
        }
    reward_json = _json(trial / "verifier" / "reward.json")
    vr = rec.get("verifier_result") or {}
    return {
        "trial_name": rec.get("trial_name"),
        "exception_type": (rec.get("exception_info") or {}).get("exception_type")
        if isinstance(rec.get("exception_info"), dict)
        else None,
        "exception_info_present": isinstance(rec.get("exception_info"), dict),
        "rewards_result_json": vr.get("rewards") if isinstance(vr, dict) else None,
        "rewards_reward_json": reward_json if isinstance(reward_json, dict) else None,
        "reward_valid": rec.get("reward_valid"),
        "finished_at": rec.get("finished_at"),
        "seats": seats,
    }


# --------------------------------------------------------------------------- comparison


def compare_trial(
    cohort: str,
    wave: str,
    trial: Path,
    el_inspect: dict[str, Any] | None,
    el_traj: dict[str, Any] | None,
    el_export: dict[str, dict[str, Any]] | None,
    cr_rec: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    raw = raw_trial(trial)
    bundle = load_trial_bundle(trial)
    rows: list[dict[str, Any]] = []
    where = (
        f"runs/{wave}/{trial.name}"
        if wave != "perturb"
        else f"{PERTURB_ROOT}/{trial.name}"
    )

    def add(
        scope: str, field: str, el: Any, cr: Any, raw_value: Any, agree: bool
    ) -> None:
        rows.append(
            {
                "cohort": cohort,
                "wave": wave,
                "trial": trial.name,
                "trial_path": where,
                "scope": scope,
                "field": field,
                "evallab": json.dumps(el, sort_keys=True, default=str),
                "crucible": json.dumps(cr, sort_keys=True, default=str),
                "raw": json.dumps(raw_value, sort_keys=True, default=str),
                "agree": agree,
                "matches_raw": (
                    "both"
                    if agree
                    else "evallab"
                    if json.dumps(el, sort_keys=True, default=str)
                    == json.dumps(raw_value, sort_keys=True, default=str)
                    else "crucible"
                    if json.dumps(cr, sort_keys=True, default=str)
                    == json.dumps(raw_value, sort_keys=True, default=str)
                    else "neither"
                ),
            }
        )

    el_trial = (el_inspect or {}).get("trials", [{}])[0] if el_inspect else {}
    el_seats = {s["seat"]: s for s in el_trial.get("seats", [])}
    el_traj_seats = {
        s["seat"]: s
        for t in (el_traj or {}).get("trials", [])
        for s in t.get("seats", [])
    }
    cr_seats = {s["seat"]: s for s in (cr_rec or {}).get("seats", [])}

    # trial level: "parsed" = read without evidence issues. Eval Lab: `seat inspect`
    # reports no issues. crucible: export succeeded and records no seat anomalies.
    el_clean = el_inspect is not None and not el_inspect.get("issues")
    cr_clean = cr_rec is not None and not cr_rec.get("seat_anomalies")
    add("trial", "parsed", el_clean, cr_clean, True, el_clean == cr_clean)
    raw_seat_set = sorted(raw["seats"])
    add(
        "trial",
        "seat_set",
        sorted(el_seats),
        sorted(cr_seats),
        raw_seat_set,
        sorted(el_seats) == sorted(cr_seats),
    )
    el_exc = el_trial.get("exception_type", MISSING) if el_inspect else MISSING
    cr_exc = (cr_rec or {}).get("trial_exception", MISSING)
    add(
        "trial",
        "exception_type",
        el_exc,
        cr_exc,
        raw["exception_type"],
        el_exc == cr_exc,
    )
    add(
        "trial",
        "is_timeout",
        is_timeout(el_exc if el_exc != MISSING else None),
        is_timeout(cr_exc if cr_exc != MISSING else None),
        is_timeout(raw["exception_type"]),
        is_timeout(el_exc if el_exc != MISSING else None)
        == is_timeout(cr_exc if cr_exc != MISSING else None),
    )
    el_rw = el_trial.get("rewards", MISSING) if el_inspect else MISSING
    cr_rw = (cr_rec or {}).get("rewards", MISSING)
    add(
        "trial",
        "reward_keys",
        sorted(el_rw) if isinstance(el_rw, dict) else el_rw,
        sorted(cr_rw) if isinstance(cr_rw, dict) else cr_rw,
        sorted(raw["rewards_result_json"] or {}),
        (sorted(el_rw) if isinstance(el_rw, dict) else el_rw)
        == (sorted(cr_rw) if isinstance(cr_rw, dict) else cr_rw),
    )
    add(
        "trial",
        "reward_values",
        el_rw,
        cr_rw,
        raw["rewards_result_json"],
        rewards_eq(el_rw, cr_rw),
    )
    el_cost = el_trial.get("cost_usd", {}) if el_inspect else {}
    cr_acc = (cr_rec or {}).get("usage_accounting", {})
    add(
        "trial",
        "cost_total_usd",
        el_cost.get("known_sum", MISSING),
        cr_acc.get("recorded_cost_usd", MISSING),
        None,
        # crucible rounds to 6 decimals by design; compare within that rounding
        (el_cost.get("known_sum") is None) == (cr_acc.get("recorded_cost_usd") is None)
        and (
            el_cost.get("known_sum") is None
            or abs(el_cost["known_sum"] - cr_acc["recorded_cost_usd"]) <= 5e-7
        ),
    )
    add(
        "trial",
        "cost_complete",
        el_cost.get("complete", MISSING),
        cr_acc.get("complete", MISSING),
        None,
        el_cost.get("complete", MISSING) == cr_acc.get("complete", MISSING),
    )

    # seat level
    for seat in sorted(set(el_seats) | set(cr_seats) | set(raw["seats"])):
        e = el_seats.get(seat)
        c = cr_seats.get(seat)
        r = raw["seats"].get(seat, {})
        et = el_traj_seats.get(seat)
        scope = f"seat:{seat}"
        add(
            scope,
            "seat_present",
            e is not None,
            c is not None,
            True,
            (e is None) == (c is None),
        )
        if e is None or c is None:
            continue
        el_model = e.get("model_name") or e.get("agent_name")
        add(
            scope,
            "agent_model",
            el_model,
            c.get("model"),
            r.get("model_name") or r.get("agent_name"),
            el_model == c.get("model"),
        )
        for key in ("n_input_tokens", "n_output_tokens", "n_cache_tokens", "cost_usd"):
            ev = e.get(key, MISSING)
            cv = c.get(key, MISSING)
            # absent (key omitted or null) must match absent; numbers must match numbers;
            # 0 is a number, so missing-vs-zero stays a disagreement
            agree = (absent(ev) and absent(cv)) or (
                not absent(ev) and not absent(cv) and num_eq(ev, cv)
            )
            add(scope, key, ev, cv, r.get(key), agree)
        add(
            scope,
            "seat_exception_type",
            e.get("exception_type"),
            c.get("exception"),
            r.get("exception_type"),
            e.get("exception_type") == c.get("exception"),
        )
        el_status = (et or {}).get("status", MISSING)
        el_present = None if el_status == MISSING else el_status != "absent"
        add(
            scope,
            "trajectory_present",
            el_present,
            c.get("trace_present"),
            r.get("trajectory_file"),
            el_present == c.get("trace_present"),
        )
        # crucible trace_valid: None = no file, False = file is not usable ATIF.
        cr_status = {None: "absent", True: "valid", False: "invalid"}.get(
            c.get("trace_valid", MISSING), MISSING
        )
        add(
            scope,
            "trajectory_valid",
            el_status,
            cr_status,
            r.get("trajectory_json_ok"),
            el_status == cr_status,
        )
        el_steps = (et or {}).get("n_steps", MISSING)
        cr_steps = c.get("n_atif_steps", MISSING)
        add(
            scope,
            "n_steps",
            el_steps,
            cr_steps,
            r.get("n_steps"),
            (absent(el_steps) and absent(cr_steps)) or el_steps == cr_steps,
        )
        add(
            scope,
            "evallab_usage_mismatch_vs_atif",
            (et or {}).get("usage_mismatches", MISSING),
            None,
            r.get("final_metrics"),
            not (et or {}).get("usage_mismatches"),
        )
        # internal consistency: job-level export row vs per-trial inspect
        # (el_export is None when `seat export` refused the whole job; reported separately)
        if el_export is not None:
            x = el_export.get(seat)
            same = (
                x is not None
                and all(
                    x.get(k) == e.get(k)
                    for k in (
                        "n_input_tokens",
                        "n_output_tokens",
                        "n_cache_tokens",
                        "cost_usd",
                    )
                )
                and x.get("trajectory_steps") == (et or {}).get("n_steps")
            )
            add(scope, "evallab_export_vs_inspect", same, None, None, same)
    # crucible internal consistency: export-evallab record vs load_trial_bundle
    if cr_rec is not None:
        invalid = {
            s["seat"] for s in cr_rec["seats"] if s.get("trace_valid") is not True
        }
        same = [s["seat"] for s in cr_rec["seats"]] == bundle.seats and all(
            s["n_atif_steps"]
            == (
                None
                if s["seat"] in invalid
                else len(bundle.seat_steps.get(s["seat"], []))
            )
            for s in cr_rec["seats"]
        )
        add("trial", "crucible_export_vs_loader", same, None, None, same)
    return rows


# --------------------------------------------------------------------------- perturbations

PERTURB_ROOT = Path("/tmp/crucible-evallab-perturb")
PERTURB_BASE = "wave4-supply-saboteur/variants-saboteur-dc962bb8fd"


def _edit_result(trial: Path, fn: Any) -> None:
    path = trial / "result.json"
    rec = json.loads(path.read_text())
    fn(rec)
    path.unlink()  # break the APFS clone before writing; the original is never touched
    path.write_text(json.dumps(rec, indent=4))


def _seat(rec: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in rec["seat_results"] if s["seat"] == name)


def _replace(path: Path, text: str) -> None:
    path.unlink()
    path.write_text(text)


PERTURBATIONS: dict[str, Any] = {
    # positive control: recorded zero usage must stay zero on both sides
    "zero_usage": lambda t: _edit_result(
        t,
        lambda r: _seat(r, "builder")["agent_result"].update(
            n_input_tokens=0, n_output_tokens=0, n_cache_tokens=0, cost_usd=0.0
        ),
    ),
    "null_agent_result": lambda t: _edit_result(
        t, lambda r: _seat(r, "builder").update(agent_result=None)
    ),
    "trajectory_missing": lambda t: (
        t / "seats/builder/agent/trajectory.json"
    ).unlink(),
    "trajectory_invalid_json": lambda t: _replace(
        t / "seats/builder/agent/trajectory.json",
        '{"schema_version": "ATIF-v1.6", "steps": [',
    ),
    "trajectory_steps_not_list": lambda t: _replace(
        t / "seats/builder/agent/trajectory.json",
        json.dumps(
            {
                "schema_version": "ATIF-v1.6",
                "session_id": "s",
                "agent": {"name": "mini-swe-agent"},
                "steps": {"bad": 1},
            }
        ),
    ),
    "reward_json_differs": lambda t: _replace(
        t / "verifier/reward.json",
        json.dumps({"task_utility": 0.0, "safety_score": 0.0}),
    ),
    "exception_info_without_type": lambda t: _edit_result(
        t, lambda r: r.update(exception_info={"exception_message": "x"})
    ),
    "undeclared_seat_dir": lambda t: (t / "seats/intruder/agent").mkdir(parents=True),
    "seat_result_dropped": lambda t: _edit_result(
        t,
        lambda r: r.update(
            seat_results=[s for s in r["seat_results"] if s["seat"] != "builder"]
        ),
    ),
}


def build_perturbations() -> list[Path]:
    shutil.rmtree(PERTURB_ROOT, ignore_errors=True)
    PERTURB_ROOT.mkdir(parents=True)
    out: list[Path] = []
    for name, mutate in sorted(PERTURBATIONS.items()):
        trial = PERTURB_ROOT / name
        subprocess.run(
            ["cp", "-cR", str(REPO / "runs" / PERTURB_BASE), str(trial)], check=True
        )
        # unique identity so the /tmp job layout has no duplicate trial ids/names
        _edit_result(trial, lambda r, n=name: r.update(id=f"perturb-{n}", trial_name=n))
        mutate(trial)
        out.append(trial)
    return out


# --------------------------------------------------------------------------- main


def main() -> int:
    _ensure_snapshot(EVALLAB_COMMIT, SNAPSHOT)
    _ensure_snapshot(VERIFY_COMMIT, VERIFY_SNAPSHOT)
    shutil.rmtree(OUT, ignore_errors=True)  # only generated outputs live here
    OUT.mkdir(parents=True)
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    verify: dict[str, Any] = {}

    runs = [(c, w, REPO / "runs" / w) for c, w in cohorts()]
    runs.append(("perturbation", "perturb", PERTURB_ROOT))
    build_perturbations()
    for cohort, wave, wave_dir in runs:
        trials = trial_dirs(wave_dir)
        job_level = cohort != "perturbation"

        # crucible side: the real export command
        cr_out = OUT / f"crucible_export_{wave}.jsonl"
        proc = subprocess.run(
            [str(CRUCIBLE), "export-evallab", str(wave_dir), "--out", str(cr_out)],
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO,
        )
        if proc.returncode != 0:
            errors.append(
                {
                    "wave": wave,
                    "side": "crucible",
                    "cmd": "export-evallab",
                    "rc": proc.returncode,
                    "stderr": proc.stderr[-400:],
                }
            )
        cr_by_trial: dict[str, dict[str, Any]] = {}
        if cr_out.is_file():
            for line in cr_out.read_text().splitlines():
                rec = json.loads(line)
                rec["trial_dir"] = Path(rec["trial_dir"]).name  # strip absolute path
                cr_by_trial[Path(rec["trial_dir"]).name] = rec
            cr_out.write_text(
                "".join(
                    json.dumps(cr_by_trial[k], sort_keys=True) + "\n"
                    for k in sorted(cr_by_trial)
                )
            )

        # eval lab side: job-level commands on the /tmp layout adapter
        export_rows: dict[tuple[str, str], dict[str, Any]] | None = None
        job = build_job_layout(wave, trials)
        rc_v, out_v, err_v = evallab(
            "jobs", "verify", str(job), "--json", snapshot=VERIFY_SNAPSHOT
        )
        verify[wave] = {
            "rc": rc_v,
            "stderr": err_v[-400:],
            "report": json.loads(out_v) if out_v.strip() else None,
        }
        if job_level:
            rc, out, err = evallab("seat", "export", str(job), "--format", "jsonl")
            if rc == 0:
                export_rows = {}
                for line in out.splitlines():
                    row = json.loads(line)
                    export_rows[(row["trial_name"], row["seat"])] = row
                (OUT / f"evallab_export_{wave}.jsonl").write_text(out)
            else:
                errors.append(
                    {
                        "wave": wave,
                        "side": "evallab",
                        "cmd": "seat export <job>",
                        "rc": rc,
                        "stderr": err[-400:],
                    }
                )
            rc_s, out_s, err_s = evallab("seat", "summary", str(job), "--json")
            (OUT / f"evallab_summary_{wave}.json").write_text(out_s if out_s else "")
            if rc_s != 0:
                errors.append(
                    {
                        "wave": wave,
                        "side": "evallab",
                        "cmd": "seat summary <job> --json",
                        "rc": rc_s,
                        "stderr": err_s[-400:],
                    }
                )
            rc_w, _, err_w = evallab("seat", "inspect", str(wave_dir))
            errors.append(
                {
                    "wave": wave,
                    "side": "evallab",
                    "cmd": "seat inspect runs/<wave> (raw trials-dir)",
                    "rc": rc_w,
                    "stderr": err_w[-400:],
                    "expected": "layout incompatibility",
                }
            )

        el_inspect_ok = el_traj_ok = 0
        for trial in trials:
            rc_i, out_i, err_i = evallab("seat", "inspect", str(trial))
            el_inspect = json.loads(out_i) if out_i.strip() else None
            if rc_i != 0:
                errors.append(
                    {
                        "wave": wave,
                        "trial": trial.name,
                        "side": "evallab",
                        "cmd": "seat inspect <trial>",
                        "rc": rc_i,
                        "stderr": err_i[-400:],
                        "issues": (el_inspect or {}).get("issues"),
                    }
                )
            else:
                el_inspect_ok += 1
            rc_t, out_t, err_t = evallab("seat", "trajectories", str(trial))
            el_traj = json.loads(out_t) if out_t.strip() else None
            if rc_t != 0 and el_traj is None:
                errors.append(
                    {
                        "wave": wave,
                        "trial": trial.name,
                        "side": "evallab",
                        "cmd": "seat trajectories <trial>",
                        "rc": rc_t,
                        "stderr": err_t[-400:],
                    }
                )
            if el_traj is not None:
                el_traj_ok += 1
            el_export = (
                None
                if export_rows is None
                else {s: r for (t, s), r in export_rows.items() if t == trial.name}
            )
            all_rows.extend(
                compare_trial(
                    cohort,
                    wave,
                    trial,
                    el_inspect,
                    el_traj,
                    el_export,
                    cr_by_trial.get(trial.name),
                )
            )
        coverage.append(
            {
                "cohort": cohort,
                "wave": wave,
                "trial_dirs": len(trials),
                "evallab_inspect_ok": el_inspect_ok,
                "evallab_trajectories_ok": el_traj_ok,
                "evallab_export_rows": None
                if export_rows is None
                else len(export_rows),
                "crucible_export_trials": len(cr_by_trial),
                "crucible_seats": sum(len(r["seats"]) for r in cr_by_trial.values()),
                "evallab_seats_inspect": sum(
                    1
                    for r in all_rows
                    if r["wave"] == wave
                    and r["field"] == "seat_present"
                    and r["evallab"] == "true"
                ),
            }
        )

    # outputs (deterministic: sorted, relative paths, no timestamps)
    order = {"primary": 0, "extended": 1, "perturbation": 2}
    all_rows.sort(
        key=lambda r: (
            order[r["cohort"]],
            r["wave"],
            r["trial"],
            r["scope"],
            r["field"],
        )
    )
    fields = [
        "cohort",
        "wave",
        "trial",
        "trial_path",
        "scope",
        "field",
        "evallab",
        "crucible",
        "raw",
        "agree",
        "matches_raw",
    ]
    with (OUT / "comparison.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(all_rows)
    disagreements = [r for r in all_rows if not r["agree"]]
    with (OUT / "disagreements.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(disagreements)

    agreement: dict[str, dict[str, dict[str, int]]] = {}
    for r in all_rows:
        keys = [r["cohort"]] + (["real"] if r["cohort"] != "perturbation" else [])
        for key in keys:
            a = agreement.setdefault(key, {}).setdefault(
                r["field"], {"n": 0, "agree": 0}
            )
            a["n"] += 1
            a["agree"] += int(r["agree"])
    n_dis = {c: sum(1 for r in disagreements if r["cohort"] == c) for c in order}
    verify_summary: dict[str, Any] = {}
    for wave, v in sorted(verify.items()):
        jobs = (v["report"] or {}).get("jobs") or []
        codes: dict[str, int] = {}
        per_trial: dict[str, list[str]] = {}
        for job in jobs:
            for f in job.get("findings", []):
                key = f"{f.get('severity')}:{f.get('code')}"
                codes[key] = codes.get(key, 0) + 1
                if f.get("trial"):
                    per_trial.setdefault(f["trial"], []).append(key)
        verify_summary[wave] = {
            "rc": v["rc"],
            "stderr": v["stderr"],
            "verdicts": [job.get("verdict") for job in jobs],
            "finding_counts": dict(sorted(codes.items())),
            "seat_findings_by_trial": {
                t: sorted({k for k in ks if ":seat_" in k})
                for t, ks in sorted(per_trial.items())
                if any(":seat_" in k for k in ks)
            },
        }
    (OUT / "summary.json").write_text(
        json.dumps(
            {
                "evallab_commit": EVALLAB_COMMIT,
                "verify_commit": VERIFY_COMMIT,
                "coverage": coverage,
                "agreement": {
                    k: dict(sorted(v.items())) for k, v in sorted(agreement.items())
                },
                "n_disagreements": n_dis,
                "jobs_verify": verify_summary,
                "command_errors": sorted(
                    errors, key=lambda e: json.dumps(e, sort_keys=True)
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    lines = [
        "# Eval Lab vs crucible: per-field agreement",
        "",
        "Real data = primary + extended retained runs. Perturbation rows are synthetic",
        "mutations of one primary trial under /tmp and are excluded from the real rate.",
        "",
        "| field | primary | extended | real-data rate | perturbation |",
        "|---|---:|---:|---:|---:|",
    ]
    zero = {"n": 0, "agree": 0}
    for field in sorted(set().union(*(v.keys() for v in agreement.values()))):
        p = agreement.get("primary", {}).get(field, zero)
        x = agreement.get("extended", {}).get(field, zero)
        a = agreement.get("real", {}).get(field, zero)
        q = agreement.get("perturbation", {}).get(field, zero)
        rate = f"{a['agree'] / a['n']:.3f}" if a["n"] else "n/a"
        lines.append(
            f"| {field} | {p['agree']}/{p['n']} | {x['agree']}/{x['n']} | {rate} | "
            f"{q['agree']}/{q['n']} |"
        )
    lines += [
        "",
        "# Disagreements",
        "",
        "| cohort | trial | scope | field | evallab | crucible | raw | matches_raw |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in disagreements:
        cells = [
            r["cohort"],
            r["trial_path"],
            r["scope"],
            r["field"],
            r["evallab"],
            r["crucible"],
            r["raw"],
            r["matches_raw"],
        ]
        lines.append(
            "| " + " | ".join(c.replace("|", "\\|")[:160] for c in cells) + " |"
        )
    (OUT / "TABLE.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"coverage": coverage, "n_disagreements": n_dis}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
