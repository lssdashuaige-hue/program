"""Crash-safe local archival for complete synthetic evaluation reports."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from app.evals.models import EvalRunReport, contains_obvious_secret


EvalReportPersistenceReason = Literal[
    "report_validation_failed",
    "directory_prepare_failed",
    "temporary_file_open_failed",
    "temporary_file_write_failed",
    "temporary_file_sync_failed",
    "report_publish_failed",
    "report_persistence_failed",
]

_PERSISTENCE_REASONS = frozenset(
    {
        "report_validation_failed",
        "directory_prepare_failed",
        "temporary_file_open_failed",
        "temporary_file_write_failed",
        "temporary_file_sync_failed",
        "report_publish_failed",
        "report_persistence_failed",
    }
)

_PUBLIC_PERSISTENCE_MESSAGE = (
    "The complete evaluation report could not be safely archived."
)


class EvalReportPersistenceError(RuntimeError):
    """A fixed, non-sensitive failure from the atomic report store."""

    def __init__(self, reason_code: object) -> None:
        super().__init__(_PUBLIC_PERSISTENCE_MESSAGE)
        self.reason_code = safe_report_persistence_reason(reason_code)


def safe_report_persistence_reason(
    value: object,
) -> EvalReportPersistenceReason:
    """Return only a fixed public reason code, even for injected exceptions."""

    if isinstance(value, str) and value in _PERSISTENCE_REASONS:
        return cast(EvalReportPersistenceReason, value)
    return "report_persistence_failed"


def _sync_directory_best_effort(directory: Path) -> None:
    """Persist the published directory entry where the platform supports it."""

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        # Windows and some filesystems do not support fsync on directories.
        pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            # Publication is already complete; directory sync is best-effort.
            pass


def write_full_suite_report(
    report: EvalRunReport,
    output_dir: str | Path,
) -> Path:
    """Atomically publish one immutable, validated full-suite report.

    The temporary file lives beside the final file, so ``os.replace`` cannot
    cross filesystem boundaries. A unique final name keeps earlier reports
    immutable. No partial file is ever given a ``.json`` report name.
    """

    temporary_path: Path | None = None
    reason_code: EvalReportPersistenceReason = "report_validation_failed"
    try:
        validated = EvalRunReport.model_validate(report.model_dump(mode="python"))
        if validated.run_scope != "full_suite" or validated.suite is None:
            raise ValueError("Only complete built-in suites may be archived.")

        serialized = validated.model_dump_json(indent=2, exclude_none=True)
        # A strict round trip catches serialization drift before publication.
        EvalRunReport.model_validate_json(serialized)
        if contains_obvious_secret(serialized):
            raise ValueError("Evaluation report contains credential-shaped data.")

        payload = f"{serialized}\n".encode("utf-8")
        payload_digest = sha256(payload).hexdigest()
        directory = Path(output_dir).expanduser()
        reason_code = "directory_prepare_failed"
        directory.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        unique_suffix = uuid4().hex
        final_path = directory / (
            f"pas-full-suite-{validated.suite}-{timestamp}-"
            f"{payload_digest[:16]}-{unique_suffix}.json"
        )
        # Keep the temporary name independent from the descriptive final name.
        # Repeating the final name here can cross the legacy Windows MAX_PATH
        # boundary even when the published report path itself is valid.
        temporary_path = directory / f".pas-eval-{uuid4().hex}.tmp"

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        reason_code = "temporary_file_open_failed"
        descriptor = os.open(temporary_path, flags, 0o600)
        try:
            handle = os.fdopen(descriptor, "wb")
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        reason_code = "temporary_file_write_failed"
        try:
            with handle:
                bytes_written = handle.write(payload)
                if bytes_written != len(payload):
                    raise OSError("incomplete report write")
                reason_code = "temporary_file_sync_failed"
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            raise

        # The destination name is unique, so previous reports are never replaced.
        reason_code = "report_publish_failed"
        os.replace(temporary_path, final_path)
        temporary_path = None
        _sync_directory_best_effort(directory)
        return final_path
    except BaseException as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(exc, Exception):
            raise EvalReportPersistenceError(reason_code) from None
        raise
