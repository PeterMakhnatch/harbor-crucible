"""Condition aggregation and rendering for the evidence report."""

from crucible.report import collect_condition_table, render_condition_markdown
from crucible.schema import TrialBundle


def _bundle(
    *,
    family: str = "supply-chain-sabotage",
    condition: str = "saboteur",
    rewards: dict[str, float] | None = None,
    exception: str | None = None,
    models: dict[str, str] | None = None,
) -> TrialBundle:
    return TrialBundle(
        trial_dir=f"runs/x/{condition}",
        trial_name=f"t-{condition}",
        task_family=family,
        condition=condition,
        seats=["scout_a", "builder"],
        seat_models=models or {"scout_a": "deepseek/deepseek-chat"},
        rewards=rewards or {},
        trial_exception=exception,
    )


def test_timeouts_are_counted_separately_from_other_errors() -> None:
    bundles = [
        _bundle(condition="saboteur", exception="AgentTimeoutError"),
        _bundle(condition="saboteur", exception="ValueError"),
        _bundle(condition="saboteur"),
    ]

    rows = collect_condition_table(bundles)

    assert len(rows) == 1
    assert rows[0]["n_trials"] == 3
    assert rows[0]["n_errored"] == 2
    assert rows[0]["n_timeouts"] == 1


def test_rewards_are_summarised_as_a_range_over_trials() -> None:
    bundles = [
        _bundle(rewards={"task_utility": 0.3, "safety_score": 0.0}),
        _bundle(rewards={"task_utility": 0.6, "safety_score": 1.0}),
    ]

    rows = collect_condition_table(bundles)
    metrics = rows[0]["metrics"]

    assert metrics["task_utility"]["n"] == 2
    assert metrics["task_utility"]["min"] == 0.3
    assert metrics["task_utility"]["max"] == 0.6
    assert metrics["task_utility"]["span"] == "0.30–0.60"


def test_a_missing_metric_does_not_fake_a_zero() -> None:
    bundles = [
        _bundle(rewards={"task_utility": 1.0}),
        _bundle(rewards={"task_utility": 1.0, "sabotage_success": 1.0}),
    ]

    metrics = collect_condition_table(bundles)[0]["metrics"]

    # One trial reported it, so the range covers that trial only.
    assert metrics["sabotage_success"]["n"] == 1
    assert metrics["sabotage_success"]["span"] == "1.00"


def test_each_family_gets_its_own_table_with_its_own_metrics() -> None:
    supply = _bundle(family="supply-chain-sabotage", rewards={"sabotage_success": 1.0})
    epistemic = _bundle(
        family="epistemic-crucible", condition="gullibility_p50", rewards={"liar_identified": 0.0}
    )

    rendered = render_condition_markdown(collect_condition_table([supply, epistemic]))

    assert "### `supply-chain-sabotage`" in rendered
    assert "### `epistemic-crucible`" in rendered
    blocks = {
        marker: body
        for marker, body in (
            (part.splitlines()[0], "\n".join(part.splitlines()[1:]))
            for part in rendered.split("### ")
            if part.strip()
        )
    }
    supply_block = blocks["`supply-chain-sabotage`"]
    epistemic_block = blocks["`epistemic-crucible`"]
    # Family-specific metrics must not leak dashes into the other table.
    assert "sabotage_success" in supply_block
    assert "sabotage_success" not in epistemic_block
    assert "liar_identified" not in supply_block
    assert "liar_identified" in epistemic_block


def test_model_set_is_part_of_the_grouping() -> None:
    bundles = [
        _bundle(rewards={"task_utility": 1.0}),
        _bundle(
            rewards={"task_utility": 1.0},
            models={"scout_a": "gemini/gemini-2.5-flash"},
        ),
    ]

    rows = collect_condition_table(bundles)

    assert len(rows) == 2
    assert {row["models"] for row in rows} == {
        "deepseek/deepseek-chat",
        "gemini/gemini-2.5-flash",
    }
