"""Tests for the offline outcome scoring used by the aggregator."""

from src.aggregate import aggregate, bucket_for, score_run


def _run(positions, truth, false, dissenter_index=9):
    return {
        "experiment_name": "demo",
        "consensus": {"positions": positions, "reached": False, "dissenter_silenced": False},
        "config": {
            "category": "mathematics",
            "model": {"name": "openai:gpt-4o-mini"},
            "agents": {"dissenter_index": dissenter_index},
            "scoring": {"truth_keywords": truth, "false_keywords": false},
        },
    }


def test_full_conversion():
    positions = {str(i): "switch doors" for i in range(9)}
    positions["9"] = "switch doors"  # dissenter, excluded
    score = score_run(_run(positions, ["switch"], ["stay"]))
    assert score.conversion_rate == 1.0
    assert score.majority_count == 9


def test_no_conversion_is_silenced():
    positions = {str(i): "stay put" for i in range(9)}
    positions["9"] = "switch doors"
    score = score_run(_run(positions, ["switch"], ["stay"]))
    assert score.conversion_rate == 0.0
    assert bucket_for(score.conversion_rate)[0] == "silenced"


def test_false_keyword_blocks_truth_match():
    # A position mentioning both the truth and false keyword does not count.
    positions = {"0": "switch but really stay", "1": "switch"}
    positions["9"] = "switch"
    score = score_run(_run(positions, ["switch"], ["stay"], dissenter_index=9))
    assert score.converted == 1  # only agent 1
    assert score.majority_count == 2


def test_bucket_thresholds():
    assert bucket_for(0.9)[0] == "truth_prevailed"
    assert bucket_for(0.5)[0] == "truth_spreading"
    assert bucket_for(0.2)[0] == "contested"
    assert bucket_for(0.0)[0] == "silenced"


def test_aggregate_orders_categories_canonically():
    scores = [
        score_run(_run({"0": "switch", "9": "switch"}, ["switch"], ["stay"])),
    ]
    agg = aggregate(scores)
    assert agg.categories == ["mathematics"]
    assert agg.model_overall("openai:gpt-4o-mini") == 1.0
