from pathlib import Path

import pytest

from app.evals.models import (
    EvalAssertionReport,
    EvalCaseReport,
    EvalRunReport,
)
from app.evals import report_store
from app.evals.report_store import (
    EvalReportPersistenceError,
    write_full_suite_report,
)


def full_suite_report(*, input_text: str = "完全合成的报告采集测试。") -> EvalRunReport:
    case = EvalCaseReport(
        case_id="atomic_report_probe",
        category="pipeline",
        input=input_text,
        review_completed=False,
        hard_assertions=[
            EvalAssertionReport(
                rule="synthetic_report_probe",
                applicable=True,
                passed=False,
                detail="Synthetic collection fixture.",
            )
        ],
        passed=False,
        latency_ms=1,
        error="internal_error",
    )
    return EvalRunReport(
        suite="pas-core-v0.1",
        run_scope="full_suite",
        total_suite_case_count=1,
        case_count=1,
        passed=False,
        pass_count=0,
        fail_count=1,
        duration_ms=2,
        cases=[case],
    )


def test_complete_report_is_atomically_published_and_round_trips(
    tmp_path: Path,
) -> None:
    report = full_suite_report()

    archived_path = write_full_suite_report(report, tmp_path)

    assert archived_path.parent == tmp_path
    assert archived_path.name.startswith("pas-full-suite-pas-core-v0.1-")
    assert archived_path.suffix == ".json"
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".*.tmp"))
    restored = EvalRunReport.model_validate_json(
        archived_path.read_text(encoding="utf-8")
    )
    assert restored == report


def test_each_successful_archive_preserves_older_reports(tmp_path: Path) -> None:
    report = full_suite_report()
    first_path = write_full_suite_report(report, tmp_path)
    first_payload = first_path.read_bytes()

    second_path = write_full_suite_report(report, tmp_path)

    assert second_path != first_path
    assert first_path.read_bytes() == first_payload
    assert sorted(tmp_path.glob("*.json")) == sorted([first_path, second_path])


def test_write_failure_removes_partial_file_and_preserves_old_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_path = write_full_suite_report(full_suite_report(), tmp_path)
    old_payload = old_path.read_bytes()

    def fail_publish(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(report_store.os, "replace", fail_publish)

    with pytest.raises(EvalReportPersistenceError) as failure:
        write_full_suite_report(full_suite_report(), tmp_path)

    assert str(failure.value) == (
        "The complete evaluation report could not be safely archived."
    )
    assert old_path.read_bytes() == old_payload
    assert list(tmp_path.glob("*.json")) == [old_path]
    assert not list(tmp_path.glob(".*.tmp"))


def test_interruption_never_publishes_or_leaves_a_partial_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt_publish(_source: Path, _destination: Path) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(report_store.os, "replace", interrupt_publish)

    with pytest.raises(KeyboardInterrupt):
        write_full_suite_report(full_suite_report(), tmp_path)

    assert not list(tmp_path.iterdir())


def test_credential_shaped_content_is_rejected_before_disk_write(
    tmp_path: Path,
) -> None:
    secret = "OPENAI_API_KEY=sk-synthetic-report-secret-123456789"
    report = full_suite_report(input_text=secret)

    with pytest.raises(EvalReportPersistenceError) as failure:
        write_full_suite_report(report, tmp_path)

    assert secret not in str(failure.value)
    assert not list(tmp_path.iterdir())
