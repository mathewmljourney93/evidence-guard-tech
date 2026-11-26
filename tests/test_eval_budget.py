"""M7 (ADR-0029): the worst-case preflight and the budget guard."""

import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evidenceguard_agents.providers import ModelCallTimeout
from evidenceguard_domain.model_calls import (
    ModelPurpose,
    ModelUsage,
    PromptRef,
    ProviderResponse,
    StopKind,
    StructuredRequest,
)
from evidenceguard_evaluation.budget import (
    MAX_REQUEST_INPUT_TOKENS,
    BudgetExhaustedError,
    BudgetGuard,
    calls_per_review,
    check_preflight,
    preflight_ceiling,
    require_open_cap,
)
from evidenceguard_evaluation.cli import RunOptions
from evidenceguard_evaluation.config import EvaluationRefusal
from evidenceguard_evaluation.pricing import ModelPrice
from evidenceguard_evaluation.records import RunContext, build_record, record_bytes
from evidenceguard_worker import evaluation_run

ROOT = Path(__file__).resolve().parents[1]
MODEL = "model-a-20260101"
PRICE = ModelPrice(Decimal("1"), Decimal("5"))
FAKE_KEY = "sk-ant-eg-fake-test-key-not-real-0001"


def _request(user_text: str = "user") -> StructuredRequest:
    return StructuredRequest(
        purpose=ModelPurpose.VERIFIER,
        prompt=PromptRef(prompt_id="verifier", version=1, sha256="1" * 64),
        model_id=MODEL,
        question_id="RET-01",
        system_text="system",
        user_text=user_text,
        max_output_tokens=1000,
    )


class _Inner:
    def __init__(self, usage: ModelUsage | None = None, error: bool = False) -> None:
        self.calls = 0
        self.usage = ModelUsage(10, 10) if usage is None else usage
        self.error = error

    @property
    def provider_id(self) -> str:
        return "fake-inner"

    def generate(self, request: StructuredRequest) -> ProviderResponse:
        self.calls += 1
        if self.error:
            raise ModelCallTimeout()
        return ProviderResponse(
            stop_kind=StopKind.END_TURN, output_text="{}", model_used=MODEL, usage=self.usage
        )


def _reservation_cost() -> Decimal:
    request = _request()
    size = len(request.system_text) + len(request.user_text) + 512
    return PRICE.cost(size, request.max_output_tokens)


def test_the_ceiling_is_the_documented_worst_case() -> None:
    assert calls_per_review() == 8 * 2 * 3 + 1
    per_call = PRICE.cost(MAX_REQUEST_INPUT_TOKENS, 4096)
    assert preflight_ceiling(reviews=9, price=PRICE, max_output_tokens=4096) == per_call * 9 * 49


def test_the_guard_refuses_before_the_crossing_call() -> None:
    inner = _Inner(usage=ModelUsage(0, 0))  # no usage: each call is charged its reservation
    guard = BudgetGuard(inner, price=PRICE, budget_usd=_reservation_cost() * 2)
    guard.generate(_request())
    guard.generate(_request())
    with pytest.raises(BudgetExhaustedError):
        guard.generate(_request())
    assert inner.calls == 2 and guard.totals.refused_calls == 1 and guard.exhausted


def test_actual_usage_is_charged_when_it_comes_back() -> None:
    inner = _Inner(usage=ModelUsage(100, 20))
    guard = BudgetGuard(inner, price=PRICE, budget_usd=Decimal(1))
    guard.generate(_request())
    assert guard.totals.spent_usd == PRICE.cost(100, 20)
    assert not guard.stopped


def test_a_timeout_is_charged_at_the_full_reservation() -> None:
    inner = _Inner(error=True)
    guard = BudgetGuard(inner, price=PRICE, budget_usd=Decimal(1))
    with pytest.raises(ModelCallTimeout):
        guard.generate(_request())
    assert guard.totals.spent_usd == _reservation_cost()


def test_actual_input_above_the_reservation_stops_the_run() -> None:
    inner = _Inner(usage=ModelUsage(1_000_000, 1))
    guard = BudgetGuard(inner, price=PRICE, budget_usd=Decimal(100))
    guard.generate(_request())
    assert guard.stopped and guard.exhausted
    with pytest.raises(BudgetExhaustedError):
        guard.generate(_request())
    assert inner.calls == 1


def test_a_stopped_run_writes_a_partial_record_marked_budget_stopped() -> None:
    context = RunContext(
        run_id="r",
        suite="live",
        variant="clean",
        created_at="2026-11-20T00:00:00Z",
        git_sha="unknown",
        corpus_digest="c" * 64,
        template_digest="t" * 64,
        prompt_digests={"verifier": "v" * 64},
        model_requested=MODEL,
        runs=1,
        anchors={},
    )
    totals = {
        "budget_usd": "1.000000",
        "spent_usd": "0.900000",
        "dispatched_calls": 3,
        "refused_calls": 1,
        "stopped": True,
    }
    record = build_record(context, [], stopped="budget_stopped", budget=totals)
    assert record["status"] == "budget_stopped" and record["budget"] == totals


# --- preflight through the runner: exit 4 and zero provider calls -------------------------------


def _tree(tmp_path: Path, cap: str, as_of: str = "2026-11-01") -> Path:
    shutil.copytree(ROOT / "sample_data", tmp_path / "sample_data")
    evaluation = tmp_path / "docs" / "evaluation"
    evaluation.mkdir(parents=True)
    selection = (ROOT / "docs" / "evaluation" / "selection.toml").read_text(encoding="utf-8")
    selection = selection.replace("total_usd_cap = 0.0", f"total_usd_cap = {cap}")
    selection = selection.replace("models = []", f'models = ["{MODEL}"]')
    (evaluation / "selection.toml").write_text(selection, encoding="utf-8")
    (evaluation / "pricing.toml").write_text(
        f'as_of = "{as_of}"\nsource_url = "https://example.invalid/pricing"\n'
        f'[models."{MODEL}"]\ninput_usd_per_mtok = 1\noutput_usd_per_mtok = 5\n',
        encoding="utf-8",
    )
    return tmp_path


class _Counting:
    built = 0

    def __call__(self, key: Any) -> Any:
        self.built += 1
        raise AssertionError("no transport may be built")


@pytest.mark.parametrize(("cap", "budget"), [("1000000.0", "0.01"), ("1.0", "1000000")])
def test_a_preflight_over_the_run_budget_or_the_total_cap_exits_4_with_no_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cap: str,
    budget: str,
) -> None:
    monkeypatch.setenv("EG_ANTHROPIC_API_KEY", FAKE_KEY)
    counting = _Counting()
    environment = evaluation_run.Environment(
        root=_tree(tmp_path, cap, as_of="2026-01-01"),
        git=lambda arguments: "",
        transport_factory=counting,
    )
    options = RunOptions("live", "clean", None, MODEL, 1, Decimal(budget), 60)
    assert evaluation_run.run_suite(options, environment) == 4
    assert counting.built == 0
    err = capsys.readouterr().err
    assert "ceiling exceeds" in err and "over 30 days old" in err
    assert FAKE_KEY not in err


def test_a_dirty_tree_is_refused_before_any_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EG_ANTHROPIC_API_KEY", FAKE_KEY)
    counting = _Counting()
    environment = evaluation_run.Environment(
        root=_tree(tmp_path, "1000000.0"),
        git=lambda arguments: " M packages/x.py\0?? docs/evaluation/runs/new.json\0",
        transport_factory=counting,
    )
    options = RunOptions("live", "clean", None, MODEL, 1, Decimal("1000000"), 60)
    assert evaluation_run.run_suite(options, environment) == 3
    assert counting.built == 0


def test_changes_only_under_the_runs_directory_are_allowed() -> None:
    evaluation_run.require_clean_tree(lambda arguments: "?? docs/evaluation/runs/a.json\0")


# --- the zero cap and committed records (changes after review) ----------------------------------


@pytest.mark.parametrize(
    ("spent", "code"),
    [("0.000000", 4), ("-5", 1), ("-Infinity", 1), ("NaN", 1), ("1e9", 1), (" 5", 1)],
)
def test_the_zero_cap_refuses_whatever_committed_records_hold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    spent: str,
    code: int,
) -> None:
    monkeypatch.delenv("EG_ANTHROPIC_API_KEY", raising=False)
    root = _tree(tmp_path, "0.0")
    context = RunContext(
        run_id="r",
        suite="live",
        variant="clean",
        created_at="2026-11-20T00:00:00Z",
        git_sha="unknown",
        corpus_digest="c" * 64,
        template_digest="t" * 64,
        prompt_digests={"verifier": "v" * 64},
        model_requested=MODEL,
        runs=1,
        anchors={},
    )
    totals = {
        "budget_usd": "1.000000",
        "spent_usd": "0.000000",
        "dispatched_calls": 0,
        "refused_calls": 0,
        "stopped": False,
    }
    data = record_bytes(build_record(context, [], budget=totals))
    data = data.replace(b'"spent_usd":"0.000000"', b'"spent_usd":' + json.dumps(spent).encode())
    runs = root / "docs" / "evaluation" / "runs"
    runs.mkdir(parents=True)
    (runs / "earlier.json").write_bytes(data)
    counting = _Counting()
    environment = evaluation_run.Environment(
        root=root, git=lambda arguments: "", transport_factory=counting
    )
    options = RunOptions("live", "clean", None, MODEL, 1, Decimal("5"), 60)
    assert evaluation_run.run_suite(options, environment) == code
    assert counting.built == 0
    err = capsys.readouterr().err
    assert spent.strip() not in err or spent == "0.000000"


@pytest.mark.parametrize(
    "amounts",
    [
        {"total_cap": Decimal("NaN")},
        {"total_cap": Decimal("-1")},
        {"committed_usd": Decimal("-Infinity")},
        {"committed_usd": Decimal("-5")},
        {"budget_usd": Decimal("Infinity")},
        {"budget_usd": Decimal("1e9")},
    ],
)
def test_the_cap_checks_parse_their_amounts(amounts: dict[str, Decimal]) -> None:
    values = {"total_cap": Decimal(0), "committed_usd": Decimal(0), "budget_usd": Decimal(5)}
    values.update(amounts)
    with pytest.raises(EvaluationRefusal) as refused:
        require_open_cap(**values)
    assert refused.value.exit_code == 1
    with pytest.raises(EvaluationRefusal) as refused:
        check_preflight(ceiling=Decimal(1), **values)
    assert refused.value.exit_code == 1


def test_the_guard_refuses_an_invalid_budget() -> None:
    for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), Decimal("1e9")):
        with pytest.raises(EvaluationRefusal):
            BudgetGuard(_Inner(), price=PRICE, budget_usd=value)
