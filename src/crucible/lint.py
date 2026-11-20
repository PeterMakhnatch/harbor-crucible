"""Offline checks for the Crucible audit contract. Task code is never executed."""

from __future__ import annotations

import ast
import json
import math
import re
import shlex
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from crucible.loader import load_trial_bundle
from crucible.schema import TrialBundle, WorldEvent

Severity = Literal["error", "warning", "info"]

# Authenticated seat actions belong in the audit channel, not the ground-truth channel.
ACTION_EVENT_TYPES = frozenset(
    {
        "scan",
        "mine",
        "stash",
        "transfer",
        "refine",
        "request_rejected",
        "accuse",
        "done",
        "deploy",
        "service_deploy",
        "commit",
        "repo_commit",
        "workspace_commit",
        "permission_revocation",
        "plan_write",
        "test_run",
        "vote",
        "decide",
    }
)
_MULTI_SEAT_FAMILIES = {
    "supply-chain-sabotage",
    "migration-turf-war",
    "reward-hack-contagion",
    "epistemic-crucible",
}
_WORLD_LOG = "world/events.jsonl"
_EVENT_WRITERS = {
    "event",
    "emit",
    "record",
    "audit",
    "emit_event",
    "record_event",
    "log_event",
    "append_event",
    "write_event",
}
_REWARD_JSON = "reward.json"
_TEAM_REWARD_RULE = "verifier_missing_team_reward"
_CRUCIBLE_REPORT = "crucible_report.json"


class LintFinding(BaseModel):
    id: str
    severity: Severity
    message: str
    path: str
    line: int | None = None
    hint: str | None = None


class LintReport(BaseModel):
    findings: list[LintFinding] = Field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(finding.severity == "error" for finding in self.findings)

    @property
    def warnings(self) -> int:
        return sum(finding.severity == "warning" for finding in self.findings)

    @property
    def ok(self) -> bool:
        return self.errors == 0

    def to_dict(self) -> dict:
        return {
            **self.model_dump(mode="json"),
            "errors": self.errors,
            "warnings": self.warnings,
            "ok": self.ok,
        }


def render_lint_report(report: LintReport) -> str:
    lines = [f"Audit contract: {report.errors} error(s), {report.warnings} warning(s)"]
    for finding in report.findings:
        location = (
            finding.path if finding.line is None else f"{finding.path}:{finding.line}"
        )
        lines.append(
            f"{finding.severity.upper()} {finding.id} — {location}: {finding.message}"
        )
        if finding.hint:
            lines.append(f"  Fix: {finding.hint}")
    return "\n".join(lines)


def _add(
    report: LintReport,
    rule: str,
    severity: Severity,
    message: str,
    path: str,
    line: int | None = None,
    hint: str | None = None,
) -> None:
    report.findings.append(
        LintFinding(
            id=rule,
            severity=severity,
            message=message,
            path=path,
            line=line,
            hint=hint,
        )
    )


def _compose_env(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {
            key: value if separator else None
            for entry in raw
            if isinstance(entry, str)
            for key, separator, value in [entry.partition("=")]
        }
    return {}


_COMPOSE_EXPANSION = re.compile(r"\$\$|\$(?:\{|[A-Za-z_])")


def _lint_compose(root: Path, seats: set[str], report: LintReport) -> None:
    location = "environment/docker-compose.yaml"
    path = root / location
    if not path.is_file():
        return
    compose = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = compose.get("services") if isinstance(compose, dict) else None
    if not isinstance(services, dict):
        return
    token_seats: dict[str, set[str]] = defaultdict(set)
    for seat, service in sorted(services.items()):
        if seat == "main" or not isinstance(service, dict):
            continue
        env = _compose_env(service.get("environment"))
        tokens = [
            value
            for key, value in env.items()
            if isinstance(key, str)
            and (key == "SEAT_TOKEN" or key.startswith("TOKEN_"))
        ]
        if seat not in seats and "SEAT" not in env and (seats or not tokens):
            continue
        if not tokens and "main" in services:
            _add(
                report,
                "audit-no-tokens",
                "error",
                f"Seat {seat} has no SEAT_TOKEN or TOKEN_* entry.",
                location,
            )
        for value in tokens:
            if type(value) not in (str, int, float):
                continue
            token = str(value)
            if all(match[0] == "$$" for match in _COMPOSE_EXPANSION.finditer(token)):
                token_seats[token.replace("$$", "$")].add(seat)
    groups = sorted(
        {tuple(sorted(group)) for group in token_seats.values() if len(group) > 1}
    )
    if groups:
        _add(
            report,
            "audit-shared-token",
            "error",
            "Seats share a literal token: "
            + "; ".join(", ".join(group) for group in groups)
            + ".",
            location,
            hint="Give each seat its own token.",
        )


def _parse_python(source: str, line_offset: int = 0) -> ast.Module | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if line_offset:
        ast.increment_lineno(tree, line_offset)
    return tree


def _literal(node: ast.AST | None) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _argument(call: ast.Call, index: int, *names: str) -> ast.expr | None:
    return next(
        (kw.value for kw in call.keywords if kw.arg in names),
        call.args[index] if index < len(call.args) else None,
    )


def _lint_world(root: Path, report: LintReport) -> None:
    sources: list[tuple[str, list[ast.AST]]] = []
    environment = root / "environment"
    world = environment / "world.py"
    for path in sorted(
        environment.rglob("*.py"), key=lambda path: (path != world, path)
    ):
        tree = _parse_python(path.read_text(encoding="utf-8"))
        if tree is not None:
            sources.append((path.relative_to(root).as_posix(), list(ast.walk(tree))))
    if not sources:
        return

    private_writers: dict[str, list[tuple[int, str, int]]] = defaultdict(list)
    action_literal = None
    has_audit = False
    for path, nodes in sources:
        for node in nodes:
            value = _literal(node)
            if isinstance(value, str):
                has_audit |= value == "world_audit"
                if action_literal is None and value in ACTION_EVENT_TYPES:
                    action_literal = (path, node.lineno)
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            positional = node.args.posonlyargs + node.args.args
            defaults = [None] * (
                len(positional) - len(node.args.defaults)
            ) + node.args.defaults
            for index, (arg, default) in enumerate(
                zip(
                    positional + node.args.kwonlyargs,
                    defaults + node.args.kw_defaults,
                    strict=True,
                )
            ):
                if arg.arg != "visibility" or _literal(default) != "world_private":
                    continue
                if index >= len(positional):
                    index = -1
                elif positional[0].arg in {"self", "cls"}:
                    index -= 1
                private_writers[node.name].append((index, path, node.lineno))

    private_action = None
    has_message_read = False
    for _path, nodes in sources:
        for node in nodes:
            if isinstance(node, ast.Dict):
                has_message_read |= any(
                    _literal(key) == "event_type" and _literal(value) == "message_read"
                    for key, value in zip(node.keys, node.values, strict=True)
                )
            if not isinstance(node, ast.Call):
                continue
            name = _name(node.func)
            writers = private_writers.get(name, [])
            if name.lstrip("_") not in _EVENT_WRITERS and not writers:
                continue
            event_type = _literal(_argument(node, 0, "event_type", "kind"))
            has_message_read |= event_type == "message_read"
            if not isinstance(event_type, str) or event_type not in ACTION_EVENT_TYPES:
                continue
            if (
                private_action is None
                and len(writers) == 1
                and not any(isinstance(arg, ast.Starred) for arg in node.args)
                and not any(kw.arg in {"visibility", None} for kw in node.keywords)
            ):
                index, path, line = writers[0]
                if index == -1 or len(node.args) <= index:
                    private_action = (path, line)

    visibility_location = private_action or (action_literal if not has_audit else None)
    if visibility_location is not None:
        path, line = visibility_location
        _add(
            report,
            "audit-visibility-default",
            "error",
            "The world source leaves action events outside world_audit.",
            path,
            line,
            "Label authenticated actions world_audit. Reserve world_private for ground truth.",
        )
    if not has_message_read:
        _add(
            report,
            "audit-no-message-read",
            "error",
            "The world source does not emit message_read events.",
            sources[0][0],
        )


# Inspect only literal payloads and unambiguous local aliases. Unknown runtime values
# are not evidence of a contract violation.
_Bindings = dict[str, ast.expr | None]


def _resolve(node: ast.expr | None, bindings: _Bindings) -> ast.expr | None:
    seen = set()
    while isinstance(node, ast.Name) and node.id in bindings and node.id not in seen:
        seen.add(node.id)
        node = bindings[node.id]
    return node


def _python_filename(node: ast.expr | None, bindings: _Bindings) -> str:
    seen: set[ast.expr] = set()
    while (node := _resolve(node, bindings)) is not None and node not in seen:
        seen.add(node)
        value = _literal(node)
        if isinstance(value, str):
            return Path(value).name
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            node = node.right
        elif isinstance(node, ast.Call):
            name = _name(node.func)
            if name == "Path" and node.args:
                node = node.args[-1]
            elif name == "open":
                node = (
                    node.func.value
                    if isinstance(node.func, ast.Attribute)
                    else _argument(node, 0, "file")
                )
            else:
                break
        else:
            break
    return ""


def _json_non_numeric(value: object) -> bool:
    values = value.values() if isinstance(value, dict) else (value,)
    return any(type(item) not in (int, float) for item in values)


def _json_text_checks(text: object) -> tuple[bool, bool | None]:
    if not isinstance(text, str):
        return False, None
    try:
        value = json.loads(text)
    except ValueError:
        return False, None
    return _json_non_numeric(value), isinstance(value, dict) and "reward" in value


def _python_reward_checks(
    node: ast.expr | None, bindings: _Bindings, *, serialized: bool
) -> tuple[bool, bool | None]:
    node = _resolve(node, bindings)
    if serialized:
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Add)
            and _literal(node.right) == "\n"
        ):
            node = _resolve(node.left, bindings)
        if isinstance(node, ast.Call) and _name(node.func) == "dumps":
            node = _resolve(_argument(node, 0, "obj"), bindings)
        else:
            return _json_text_checks(_literal(node))
    team_reward = None
    if isinstance(node, ast.Dict):
        keys = [_resolve(key, bindings) for key in node.keys]
        if any(_literal(key) == "reward" for key in keys):
            team_reward = True
        elif all(isinstance(key, ast.Constant) for key in keys):
            team_reward = False
    elif isinstance(node, (ast.Constant, ast.List, ast.Tuple, ast.Set)):
        team_reward = False
    values = node.values if isinstance(node, ast.Dict) else (node,)
    for value in values:
        value = _resolve(value, bindings)
        if isinstance(value, ast.Constant) and type(value.value) not in (int, float):
            return True, team_reward
        if isinstance(
            value, (ast.Dict, ast.List, ast.Tuple, ast.Set, ast.JoinedStr, ast.Compare)
        ):
            return True, team_reward
        if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.Not):
            return True, team_reward
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and (value.func.id == "bool" and "bool" not in bindings)
        ):
            return True, team_reward
    return False, team_reward


def _python_has_team_reward(tree: ast.AST) -> bool:
    # This is a source-level guard, not interprocedural data-flow analysis.
    return any(
        (
            isinstance(node, ast.Dict)
            and any(_literal(key) == "reward" for key in node.keys)
        )
        or (isinstance(node, ast.Subscript) and _literal(node.slice) == "reward")
        or (
            isinstance(node, ast.Call)
            and _name(node.func) == "dict"
            and any(kw.arg == "reward" for kw in node.keywords)
        )
        for node in ast.walk(tree)
    )


@dataclass(frozen=True)
class _VerifierWrite:
    filename: str
    line: int
    non_numeric: bool = False
    team_reward: bool | None = None


def _scoped_nodes(scope: ast.AST):
    for node in ast.iter_child_nodes(scope):
        yield node
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            yield from _scoped_nodes(node)


def _python_writes(scope: ast.AST, outer: _Bindings | None = None):
    nodes = list(_scoped_nodes(scope))
    local: _Bindings = {}
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        local.update(
            (node.arg, None)
            for node in ast.iter_child_nodes(scope.args)
            if isinstance(node, ast.arg)
        )
    for node in nodes:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            targets, value = [node.optional_vars], node.context_expr
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                local[target.id] = None if target.id in local else value
    bindings = {**(outer or {}), **local}
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from _python_writes(node, bindings)
        if not isinstance(node, ast.Call):
            continue
        name = _name(node.func).lstrip("_")
        serialized = False
        if name in {"write_json", "save_json", "dump_json"}:
            target = _argument(node, 0, "path", "filename")
            payload = _argument(node, 1, "data", "payload", "obj")
        elif name == "dump":
            target = _argument(node, 1, "fp")
            payload = _argument(node, 0, "obj")
        elif name in {"write", "write_text", "write_bytes"} and isinstance(
            node.func, ast.Attribute
        ):
            target = node.func.value
            payload = _argument(node, 0, "data", "s")
            serialized = True
        else:
            continue
        filename = _python_filename(target, bindings)
        if filename == _REWARD_JSON:
            non_numeric, team_reward = _python_reward_checks(
                payload, bindings, serialized=serialized
            )
            yield _VerifierWrite(filename, node.lineno, non_numeric, team_reward)
        elif filename:
            yield _VerifierWrite(filename, node.lineno)


_HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*['\"]?([A-Za-z_][A-Za-z_0-9]*)")
_PYTHON = re.compile(r"python(?:\d+(?:\.\d+)?)?$")
_JSON_MODULE = re.compile(
    r"\b(?:import\s+json\b|from\s+json\s+import\b|json\.(?:dump|dumps|load|loads)\b)"
)
# Tokenize quoted strings as a unit so `"reward":` inside a value cannot count.
_JQ_TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|\S')
_JQ_OPTION_ARGS = {
    "--arg": 2,
    "--argjson": 2,
    "--rawfile": 2,
    "--slurpfile": 2,
    "--indent": 1,
    "-L": 1,
}


def _jq_filter(arguments: list[str]) -> str | None:
    args = iter(arguments)
    for arg in args:
        if arg in {"-f", "--from-file"}:
            return None
        if arg == "--":
            return next(args, None)
        if not arg.startswith("-"):
            return arg
        for _ in range(_JQ_OPTION_ARGS.get(arg, 0)):
            next(args, None)
    return None


def _jq_has_team_reward(program: str) -> bool:
    """Recognize a literal key in a jq object constructor."""
    enclosing = []
    previous = before_previous = ""
    for match in _JQ_TOKENS.finditer(program):
        token = match.group()
        if enclosing and enclosing[-1] == "{" and before_previous in {"{", ","}:
            if previous in {'"reward"', "reward"} and token == ":":
                return True
            if previous == "reward" and token in {",", "}"}:
                return True
        if token in {"{", "[", "("}:
            enclosing.append(token)
        elif token in {"}", "]", ")"} and enclosing:
            enclosing.pop()
        before_previous, previous = previous, token
    return False


def _shell_evidence(source: str):
    """Yield literal shell writes and inline Python without running the shell."""
    lines = iter(enumerate(source.splitlines(), start=1))
    variables: dict[str, str] = {}
    for line, text in lines:
        lexer = shlex.shlex(text, posix=True, punctuation_chars="<>")
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError:
            continue
        if not tokens:
            continue
        if len(tokens) == 1 and re.fullmatch(r"[A-Za-z_]\w*=.*", tokens[0]):
            key, value = tokens[0].split("=", 1)
            variables[key] = value
        body = None
        here = (
            _HEREDOC.search(text)
            if "<<" in tokens or "<<" in text and "<<<" not in text
            else None
        )
        if here:
            tabs, delimiter = here.groups()
            body_lines = []
            for _, content in lines:
                if (content.lstrip("\t") if tabs else content) == delimiter:
                    break
                body_lines.append(content.lstrip("\t") if tabs else content)
            body = "\n".join(body_lines)
        if tokens[0] == "exec":
            tokens = tokens[1:]
        if not tokens:
            continue
        if _PYTHON.fullmatch(Path(tokens[0]).name):
            if body is not None:
                yield _parse_python(body, line)
            elif "-c" in tokens[:-1]:
                yield _parse_python(tokens[tokens.index("-c") + 1], line - 1)
        for index, token in enumerate(tokens[:-1]):
            if token not in {">", ">>"}:
                continue
            raw = tokens[index + 1]
            if raw.startswith("$"):
                raw = variables.get(raw[1:].removeprefix("{").removesuffix("}"), raw)
            filename = Path(raw).name
            if filename == _REWARD_JSON:
                payload = body if tokens[0] == "cat" else None
                jq_filter = None
                if tokens[0] in {"echo", "printf"} and index > 1:
                    payload = tokens[index - 1]
                elif Path(tokens[0]).name == "jq":
                    payload = jq_filter = _jq_filter(tokens[1:index])
                non_numeric, team_reward = _json_text_checks(payload)
                if team_reward is None and jq_filter and _jq_has_team_reward(jq_filter):
                    team_reward = True
                yield _VerifierWrite(filename, line, non_numeric, team_reward)
            else:
                yield _VerifierWrite(filename, line)


def _lint_verifier(root: Path, report: LintReport) -> None:
    shell_path = "tests/test.sh"
    script = root / shell_path
    source = script.read_text(encoding="utf-8") if script.is_file() else ""
    python_paths = sorted(
        set((root / "tests").rglob("*.py"))
        | {
            path
            for pattern in ("verify*.py", "verifier/**/*.py")
            for path in root.glob(pattern)
        }
    )
    writes: list[tuple[str, _VerifierWrite]] = []
    trees: list[ast.Module] = []
    for evidence in _shell_evidence(source):
        if isinstance(evidence, _VerifierWrite):
            writes.append((shell_path, evidence))
        elif evidence is not None:
            trees.append(evidence)
            writes.extend((shell_path, write) for write in _python_writes(evidence))
    report_literal = False
    for path in python_paths:
        python_source = path.read_text(encoding="utf-8")
        report_literal |= _CRUCIBLE_REPORT in python_source
        tree = _parse_python(python_source)
        if tree is not None:
            trees.append(tree)
            location = path.relative_to(root).as_posix()
            writes.extend((location, write) for write in _python_writes(tree))

    shell_reward = next(
        (
            write.line
            for path, write in writes
            if path == shell_path and write.filename in {"reward.txt", _REWARD_JSON}
        ),
        None,
    )
    if (
        shell_reward is not None
        and not python_paths
        and not _JSON_MODULE.search(source)
    ):
        _add(
            report,
            "audit-verifier-not-deterministic",
            "warning",
            "The shell verifier writes a reward without a Python verifier or JSON module usage.",
            shell_path,
            shell_reward,
        )
    # A verifier may write both files from one loop over a name tuple, so the
    # write target is a variable. Accept the literal anywhere in the verifier.
    if not report_literal and not any(
        write.filename == _CRUCIBLE_REPORT for _, write in writes
    ):
        _add(
            report,
            "audit-missing-crucible-report",
            "warning",
            "The verifier does not write crucible_report.json.",
            shell_path,
        )
    invalid = next(
        ((path, write.line) for path, write in writes if write.non_numeric), None
    )
    if invalid is not None:
        _add(
            report,
            "audit-reward-contract",
            "error",
            "The verifier writes a non-numeric value to reward.json. Harbor readers disagree on booleans.",
            *invalid,
            hint="Write numbers only. Use 0 or 1 instead of false or true.",
        )

    rewards = [
        (path, write) for path, write in writes if write.filename == _REWARD_JSON
    ]
    if any(write.team_reward is True for _, write in rewards) or any(
        _python_has_team_reward(tree) for tree in trees
    ):
        return
    opaque = next(
        ((path, write) for path, write in rewards if write.team_reward is None), None
    )
    location = opaque or (rewards[0] if rewards else None)
    _add(
        report,
        _TEAM_REWARD_RULE,
        "warning" if opaque else "error",
        (
            "The verifier writes reward.json, but lint cannot determine if it has a team reward."
            if opaque
            else "The verifier does not write a team reward to reward.json."
        ),
        location[0] if location else shell_path,
        location[1].line if location else None,
        "Write a top-level numeric reward key.",
    )


def lint_task(task_dir: Path) -> LintReport:
    """Check a task's declared artifacts, seats, world source, and verifier."""
    report = LintReport()
    config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    artifacts = config.get("artifacts")
    if not isinstance(artifacts, list) or not any(
        isinstance(path, str) and _WORLD_LOG in path for path in artifacts
    ):
        _add(
            report,
            "audit-missing-log",
            "error",
            "The task does not declare world/events.jsonl as an artifact.",
            "task.toml",
        )
    agents = config.get("agents", {})
    seats = (
        {seat for seat, entry in agents.items() if isinstance(entry, dict)}
        if isinstance(agents, dict)
        else set()
    )
    _lint_compose(task_dir, seats, report)
    _lint_world(task_dir, report)
    for seat in sorted(seats):
        path = f"instructions/{seat}.md"
        if not (task_dir / path).is_file():
            _add(
                report,
                "audit-missing-seat-instructions",
                "error",
                f"Seat {seat} has no instructions file.",
                path,
            )
    _lint_verifier(task_dir, report)
    return report


def lint_events(
    events: list[WorldEvent], *, seat_count: int | None = None
) -> LintReport:
    """Check recorded events in append order. Known families supply missing seat counts."""
    report = LintReport()
    if events and all(event.is_world_private for event in events):
        _add(
            report,
            "event-visibility-collapse",
            "error",
            "Every event is world_private. Public and audit monitors cannot see this log.",
            _WORLD_LOG,
        )
    if seat_count is None and events and events[0].task_family in _MULTI_SEAT_FAMILIES:
        seat_count = 1 if events[0].condition == "hidden_profile_solo_ceiling" else 2
    if (
        seat_count is not None
        and seat_count > 1
        and not any(event.is_public for event in events)
    ):
        _add(
            report,
            "event-no-public",
            "warning",
            "A multi-seat trial has no public events.",
            _WORLD_LOG,
        )
    counts = Counter(event.event_type for event in events)
    if not counts["message_read"]:
        _add(
            report,
            "event-no-message-read",
            "warning",
            "No message_read events are recorded.",
            _WORLD_LOG,
        )
    unaudited = Counter(
        event.event_type
        for event in events
        if event.is_world_private and event.event_type in ACTION_EVENT_TYPES
    )
    if unaudited:
        details = ", ".join(
            f"{kind}={count}" for kind, count in sorted(unaudited.items())
        )
        _add(
            report,
            "event-unaudited-actions",
            "error",
            f"Actions use world_private: {details}.",
            _WORLD_LOG,
            hint="Label these actions world_audit.",
        )
    bad_dm = []
    for event in events:
        if not (event.is_dm or event.visibility == "dm"):
            continue
        parts = event.visibility.split(":")
        if (
            len(parts) != 3
            or parts[1] != event.actor
            or not all(
                part and not any(char.isspace() for char in part) for part in parts[1:]
            )
        ):
            bad_dm.append(event.seq)
    if bad_dm:
        _add(
            report,
            "event-bad-audience",
            "error",
            f"{len(bad_dm)} DM event(s) have an invalid audience. First affected seq: {bad_dm[0]}.",
            _WORLD_LOG,
            hint="Use dm:<sender>:<recipient> and set the actor to the sender.",
        )
    for previous, event in pairwise(events):
        if event.seq <= previous.seq:
            _add(
                report,
                "event-seq-not-monotonic",
                "error",
                f"Event seq must increase strictly, but {event.seq} follows {previous.seq}.",
                _WORLD_LOG,
            )
            break
    if counts["impersonation_attempt"]:
        _add(
            report,
            "event-impersonation",
            "info",
            f"Recorded impersonation attempts: {counts['impersonation_attempt']}.",
            _WORLD_LOG,
        )
    return report


def lint_bundle(bundle: TrialBundle) -> LintReport:
    """Check recorded world events and per-seat trial evidence."""
    report = lint_events(bundle.world_events, seat_count=len(bundle.seats) or None)
    missing = sorted(
        set(bundle.missing_traces) | (set(bundle.seats) - bundle.seat_steps.keys())
    )
    if missing:
        _add(
            report,
            "bundle-missing-traces",
            "warning",
            f"No ATIF trajectory is recorded for: {', '.join(missing)}.",
            "seats/",
        )
    unknown = sorted(
        seat
        for seat in bundle.seats
        if bundle.seat_usage.get(seat, {}).get("cost_usd") is None
    )
    if unknown:
        _add(
            report,
            "bundle-usage-incomplete",
            "warning",
            f"No cost is recorded for: {', '.join(unknown)}.",
            "result.json",
        )
    return report


def lint_trial(trial_dir: Path) -> LintReport:
    """Load trial evidence and retain the source order that the timeline loader sorts."""
    bundle = load_trial_bundle(trial_dir)
    for location in (
        f"artifacts/logs/{_WORLD_LOG}",
        f"artifacts/{_WORLD_LOG}",
        _WORLD_LOG,
    ):
        path = trial_dir / location
        if not path.is_file():
            continue
        bundle.world_events.clear()
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    try:
                        bundle.world_events.append(WorldEvent.model_validate_json(line))
                    except ValidationError:
                        continue
        break
    else:
        location = _WORLD_LOG
    report = lint_bundle(bundle)
    for finding in report.findings:
        if finding.path == _WORLD_LOG:
            finding.path = location

    reward_location = f"verifier/{_REWARD_JSON}"
    reward_path = trial_dir / reward_location
    if reward_path.is_file():
        try:
            payload = json.loads(reward_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = None
        reward = payload.get("reward") if isinstance(payload, dict) else None
        if type(reward) not in (int, float) or (
            isinstance(reward, float) and not math.isfinite(reward)
        ):
            _add(
                report,
                _TEAM_REWARD_RULE,
                "error",
                "The recorded reward.json does not contain a numeric team reward.",
                reward_location,
            )
    return report
