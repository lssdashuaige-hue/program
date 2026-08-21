"""Crash-safe local archival for complete synthetic evaluation reports."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path
from uuid import uuid4

from app.evals.models import EvalRunReport, contains_obvious_secret


class EvalReportPersistenceError(RuntimeError):
    """A complete evaluation report could not be safely archived."""


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
        os.close(descriptor)


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
        directory.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        unique_suffix = uuid4().hex
        final_path = directory / (
            f"pas-full-suite-{validated.suite}-{timestamp}-"
            f"{payload_digest[:16]}-{unique_suffix}.json"
        )
        temporary_path = directory / f".{final_path.name}.{uuid4().hex}.tmp"

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        descriptor = os.open(temporary_path, flags, 0o600)
        try:
            handle = os.fdopen(descriptor, "wb")
        except BaseException:
            os.close(descriptor)
            raise
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            raise

        # The destination name is unique, so previous reports are never replaced.
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
            raise EvalReportPersistenceError(
                "The complete evaluation report could not be safely archived."
            ) from None
        raise
