import os
from pathlib import Path

import pytest

from app.evals.models import (
    EvalAssertionReport,
    EvalCaseReport,
    EvalRunReport,
    SuiteName,
)
from app.evals import report_store
from app.evals.report_store import (
    EvalReportPersistenceError,
    write_full_suite_report,
)


def full_suite_report(
    *,
    input_text: str = "完全合成的报告采集测试。",
    suite: SuiteName = "pas-core-v0.1",
) -> EvalRunReport:
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
        suite=suite,
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
    assert failure.value.reason_code == "report_publish_failed"
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
    assert failure.value.reason_code == "report_validation_failed"
    assert not list(tmp_path.iterdir())


def test_exact_long_root_uses_short_temporary_name_and_round_trips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_directory_length = 121
    padding = max(1, target_directory_length - len(str(tmp_path.resolve())) - 1)
    output_dir = tmp_path / ("x" * padding)
    observed_created_paths: list[Path] = []
    real_open = report_store.os.open

    def observe_open(path: str | Path, flags: int, mode: int = 0o777) -> int:
        if flags & os.O_CREAT:
            observed_created_paths.append(Path(path))
        return real_open(path, flags, mode)

    monkeypatch.setattr(report_store.os, "open", observe_open)

    archived_path = write_full_suite_report(
        full_suite_report(suite="pas-dialogue-v0.1"),
        output_dir,
    )

    assert len(observed_created_paths) == 1
    temporary_path = observed_created_paths[0]
    legacy_temporary_path = output_dir / (
        f".{archived_path.name}.{'0' * 32}.tmp"
    )
    assert len(str(output_dir.resolve())) >= target_directory_length
    assert len(str(archived_path.resolve())) < 260
    assert len(str(legacy_temporary_path.resolve())) >= 260
    assert len(str(temporary_path.resolve())) < 260
    assert temporary_path.name.startswith(".pas-eval-")
    assert temporary_path.name.endswith(".tmp")
    assert archived_path.name not in temporary_path.name
    assert EvalRunReport.model_validate_json(
        archived_path.read_text(encoding="utf-8")
    ).suite == "pas-dialogue-v0.1"


def test_temporary_open_failure_has_fixed_reason_and_preserves_old_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_path = write_full_suite_report(full_suite_report(), tmp_path)
    old_payload = old_path.read_bytes()

    def fail_open(*_args: object, **_kwargs: object) -> int:
        raise OSError("private temporary path")

    monkeypatch.setattr(report_store.os, "open", fail_open)

    with pytest.raises(EvalReportPersistenceError) as failure:
        write_full_suite_report(full_suite_report(), tmp_path)

    assert failure.value.reason_code == "temporary_file_open_failed"
    assert "private" not in str(failure.value)
    assert old_path.read_bytes() == old_payload
    assert list(tmp_path.glob("*.json")) == [old_path]
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize(
    ("write_result", "expected_reason"),
    [
        ("raise", "temporary_file_write_failed"),
        ("short", "temporary_file_write_failed"),
    ],
)
def test_temporary_write_failure_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_result: str,
    expected_reason: str,
) -> None:
    old_path = write_full_suite_report(full_suite_report(), tmp_path)
    old_payload = old_path.read_bytes()
    real_fdopen = report_store.os.fdopen

    class ControlledHandle:
        def __init__(self, descriptor: int) -> None:
            self._handle = real_fdopen(descriptor, "wb")

        def __enter__(self) -> "ControlledHandle":
            return self

        def __exit__(self, *_args: object) -> None:
            self._handle.close()

        def write(self, payload: bytes) -> int:
            if write_result == "raise":
                raise OSError("private write failure")
            return max(len(payload) - 1, 0)

        def flush(self) -> None:
            self._handle.flush()

        def fileno(self) -> int:
            return self._handle.fileno()

    def controlled_fdopen(descriptor: int, _mode: str) -> ControlledHandle:
        return ControlledHandle(descriptor)

    monkeypatch.setattr(report_store.os, "fdopen", controlled_fdopen)

    with pytest.raises(EvalReportPersistenceError) as failure:
        write_full_suite_report(full_suite_report(), tmp_path)

    assert failure.value.reason_code == expected_reason
    assert old_path.read_bytes() == old_payload
    assert list(tmp_path.glob("*.json")) == [old_path]
    assert not list(tmp_path.glob(".*.tmp"))


def test_temporary_sync_failure_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_path = write_full_suite_report(full_suite_report(), tmp_path)
    old_payload = old_path.read_bytes()

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("private sync failure")

    monkeypatch.setattr(report_store.os, "fsync", fail_fsync)

    with pytest.raises(EvalReportPersistenceError) as failure:
        write_full_suite_report(full_suite_report(), tmp_path)

    assert failure.value.reason_code == "temporary_file_sync_failed"
    assert old_path.read_bytes() == old_payload
    assert list(tmp_path.glob("*.json")) == [old_path]
    assert not list(tmp_path.glob(".*.tmp"))


def test_directory_sync_close_failure_does_not_revoke_published_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_open = report_store.os.open
    fake_directory_descriptor = 987_654_321
    opened_directories: list[Path] = []
    closed_descriptors: list[int] = []

    def controlled_open(path: str | Path, flags: int, mode: int = 0o777) -> int:
        if flags & os.O_CREAT:
            return real_open(path, flags, mode)
        opened_directories.append(Path(path))
        return fake_directory_descriptor

    def fail_close(descriptor: int) -> None:
        closed_descriptors.append(descriptor)
        raise OSError("directory close is unsupported")

    monkeypatch.setattr(report_store.os, "open", controlled_open)
    monkeypatch.setattr(report_store.os, "close", fail_close)

    archived_path = write_full_suite_report(full_suite_report(), tmp_path)

    assert opened_directories == [tmp_path]
    assert closed_descriptors == [fake_directory_descriptor]
    assert archived_path.exists()
    assert EvalRunReport.model_validate_json(
        archived_path.read_text(encoding="utf-8")
    ) == full_suite_report()


def test_unknown_reason_code_is_reduced_to_fixed_fallback() -> None:
    failure = EvalReportPersistenceError("private path and storage details")

    assert failure.reason_code == "report_persistence_failed"
    assert "private" not in str(failure)
