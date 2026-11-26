"""Reader-facing documents stay honest (plan: docs/plans/docs-architecture-readme.md).

Checked: ``README.md`` and every ``docs/*.md`` page except the historical ``docs/plan.md`` and the
``docs/evaluation*`` pages, which are where evaluation results would be reported. The ADRs, the
plans under ``docs/plans/`` and ``prompts.md`` are dated records and are not checked.

Each page must contain no em dash, no leftover ``TODO`` and none of the phrases that would claim
an evaluation result; the README must have no status heading (AGENTS.md: status lives in pull
request bodies and the CHANGELOG). The checks are plain functions over text, so the tests below
also prove that each one rejects a deliberately bad sample.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

EM_DASH = "\u2014"
CLAIM_PHRASES = (
    "recall@",
    "accuracy of",
    "outperforms",
    "precision of",
    "f1 score",
    "state of the art",
)
_TODO = re.compile(r"\bTODO\b")
_STATUS_HEADING = re.compile(r"^#{1,6}[ \t]+status\b", re.IGNORECASE | re.MULTILINE)
HISTORICAL_DOCS = frozenset({"plan.md"})


def checked_documents() -> list[Path]:
    pages = [
        path
        for path in sorted((ROOT / "docs").glob("*.md"))
        if path.name not in HISTORICAL_DOCS and not path.name.startswith("evaluation")
    ]
    return [ROOT / "README.md", *pages]


def problems(text: str) -> list[str]:
    """Every honesty problem in one document's text, as fixed descriptions."""
    found: list[str] = []
    if EM_DASH in text:
        found.append("em dash")
    if _TODO.search(text):
        found.append("TODO")
    lowered = text.casefold()
    found.extend(f"claim phrase {phrase!r}" for phrase in CLAIM_PHRASES if phrase in lowered)
    return found


def readme_problems(text: str) -> list[str]:
    found = problems(text)
    if _STATUS_HEADING.search(text):
        found.append("status heading")
    return found


def test_the_expected_pages_are_checked() -> None:
    names = {path.relative_to(ROOT).as_posix() for path in checked_documents()}
    assert {
        "README.md",
        "docs/architecture.md",
        "docs/responsible-ai.md",
        "docs/threat-model.md",
    } <= names
    assert "docs/plan.md" not in names
    assert not any(name.startswith("docs/evaluation") for name in names)


@pytest.mark.parametrize(
    "path", checked_documents(), ids=lambda path: path.relative_to(ROOT).as_posix()
)
def test_document_is_honest(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    check = readme_problems if path.name == "README.md" else problems
    assert check(text) == []


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        (f"Fast {EM_DASH} and cheap.", ["em dash"]),
        ("TODO: write this section.", ["TODO"]),
        ("Retrieval reaches Recall@5 of 0.9.", ["claim phrase 'recall@'"]),
        ("An accuracy of 97 percent.", ["claim phrase 'accuracy of'"]),
        ("It outperforms the baseline.", ["claim phrase 'outperforms'"]),
    ],
)
def test_each_check_rejects_a_bad_sample(sample: str, expected: list[str]) -> None:
    assert problems(sample) == expected


def test_a_status_heading_is_rejected_in_the_readme() -> None:
    assert readme_problems("# Title\n\n## Status: M4 accepted\n\nText.\n") == ["status heading"]
    assert readme_problems("# Title\n\n### status\n") == ["status heading"]


def test_clean_text_and_ordinary_words_pass() -> None:
    text = "# Title\n\nThe status endpoint is /readyz. Todos are fine; so are en dashes \u2013.\n"
    assert readme_problems(text) == []
