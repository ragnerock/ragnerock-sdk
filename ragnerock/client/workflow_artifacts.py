"""Workflow artifact endpoints (``/api/workflow-artifacts/...``)."""

from __future__ import annotations

import io
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section
from ragnerock.timestamps import UtcDatetime

if TYPE_CHECKING:
    import pandas as pd


class ArtifactFormat(StrEnum):
    """The file formats an artifact output writes."""

    CSV = "csv"
    """A table, one row per output, with a byte-order mark."""

    XLSX = "xlsx"
    """A table as an Excel workbook, one sheet per source agent."""

    JSON = "json"
    """A table as JSON records."""

    DOCX = "docx"
    """A written report as a Word document."""

    MARKDOWN = "markdown"
    """A written report as Markdown."""


class WorkflowArtifactInfo(_ApiModel):
    """A file a workflow's artifact output produced for one run.

    Attributes:
        id (UUID): The artifact.
        workflow_id (UUID | None): The workflow that produced it.
        sink_id (UUID | None): The output that produced it.
        run_id (UUID | None): The run it was built for.
        job_id (UUID | None): That run's job.
        file_name (str | None): The file's name.
        format (str | None): An :class:`ArtifactFormat` value.
        row_count (int): Rows in a table artifact.
        items_failed (int): Items that failed in the run; non-zero means the
            file was built from an incomplete run.
    """

    id: UUID
    project_id: UUID | None = None
    workflow_id: UUID | None = None
    workflow_name: str | None = None
    sink_id: UUID | None = None
    sink_name: str | None = None
    run_id: UUID | None = None
    job_id: UUID | None = None
    document_id: UUID | None = None
    document_name: str | None = None
    file_name: str | None = None
    format: str | None = None
    media_type: str | None = None
    size_bytes: int = 0
    row_count: int = 0
    items_failed: int = 0
    cells_truncated: int = 0
    sha256: str | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None


class WorkflowArtifactList(_ApiModel):
    """One page of a project's workflow artifacts, newest first.

    Attributes:
        artifacts (list[WorkflowArtifactInfo]): The page.
        next_cursor (str | None): Pass back as ``cursor`` for the next page;
            ``None`` on the last page.
    """

    artifacts: list[WorkflowArtifactInfo] = []
    next_cursor: str | None = None


class _WorkflowArtifactsSection(_Section):
    """Files produced by workflow artifact outputs, one per run."""

    def list(
        self,
        project_id: UUID,
        *,
        workflow_id: UUID | None = None,
        sink_id: UUID | None = None,
        run_id: UUID | None = None,
        created_after: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> WorkflowArtifactList:
        """List a project's workflow artifacts, newest first.

        Calls ``GET /api/projects/{project_id}/workflow-artifacts``.

        Args:
            project_id (UUID): The project.
            workflow_id (UUID | None): Only this workflow's artifacts.
            sink_id (UUID | None): Only this output's artifacts.
            run_id (UUID | None): Only this run's artifacts.
            created_after (datetime | None): Only artifacts created after this.
            cursor (str | None): The previous page's ``next_cursor``.
            limit (int): Page size, at most 200.

        Returns:
            WorkflowArtifactList: One page, with the cursor for the next.
        """
        response = self._parent._request(
            "GET",
            f"/api/projects/{project_id}/workflow-artifacts",
            params={
                "limit": limit,
                "workflow_id": _str_or_none(workflow_id),
                "sink_id": _str_or_none(sink_id),
                "run_id": _str_or_none(run_id),
                "cursor": cursor,
                "created_after": (
                    created_after.isoformat() if created_after is not None else None
                ),
            },
        )
        return WorkflowArtifactList.model_validate(response.json())

    def get(self, artifact_id: UUID) -> WorkflowArtifactInfo:
        """Fetch one workflow artifact's metadata.

        Calls ``GET /api/workflow-artifacts/{artifact_id}``.

        Args:
            artifact_id (UUID): The artifact.

        Returns:
            WorkflowArtifactInfo: The artifact.

        Raises:
            NotFoundError: If the artifact does not exist.
        """
        response = self._parent._request(
            "GET", f"/api/workflow-artifacts/{artifact_id}"
        )
        return WorkflowArtifactInfo.model_validate(response.json())

    def download(self, artifact_id: UUID, path: str | Path) -> Path:
        """Download an artifact's file to disk.

        Calls ``GET /api/workflow-artifacts/{artifact_id}/content``. The body
        is streamed straight to ``path``, so large files are never held in
        memory.

        Args:
            artifact_id (UUID): The artifact.
            path (str | Path): Where to write the file. Overwritten if it
                exists.

        Returns:
            Path: The written file.

        Raises:
            NotFoundError: If the artifact does not exist.
        """
        target = Path(path)
        with self._parent._stream(
            "GET", f"/api/workflow-artifacts/{artifact_id}/content"
        ) as response:
            with target.open("wb") as file:
                for chunk in response.iter_bytes():
                    file.write(chunk)
        return target

    def delete(self, artifact_id: UUID) -> None:
        """Delete an artifact and its file.

        Calls ``DELETE /api/workflow-artifacts/{artifact_id}``.

        Args:
            artifact_id (UUID): The artifact.
        """
        self._parent._request("DELETE", f"/api/workflow-artifacts/{artifact_id}")

    def to_dataframe(self, artifact_id: UUID) -> pd.DataFrame:
        """Load a table artifact's rows into a pandas DataFrame.

        Calls ``GET /api/workflow-artifacts/{artifact_id}/content``, after
        fetching the artifact with :meth:`get` to learn its format. Requires
        the ``pandas`` extra; an XLSX artifact also needs ``openpyxl``. A JSON
        artifact's records are flattened: provenance columns first, then the
        output's fields.

        Args:
            artifact_id (UUID): The artifact.

        Returns:
            pd.DataFrame: One row per output.

        Raises:
            ImportError: If pandas is not installed.
            ValueError: If the artifact is a report (Word or Markdown) rather
                than a table.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for to_dataframe(). "
                "Install it with: pip install 'ragnerock[pandas]'"
            ) from e
        info = self.get(artifact_id)
        if info.format not in (
            ArtifactFormat.CSV,
            ArtifactFormat.XLSX,
            ArtifactFormat.JSON,
        ):
            raise ValueError(f"Unsupported artifact format: {info.format}")
        response = self._parent._request(
            "GET", f"/api/workflow-artifacts/{artifact_id}/content"
        )
        if info.format == ArtifactFormat.CSV:
            return pd.read_csv(io.BytesIO(response.content), encoding="utf-8-sig")
        if info.format == ArtifactFormat.XLSX:
            return pd.read_excel(io.BytesIO(response.content))
        records = json.loads(response.content)["records"]
        return pd.DataFrame(
            [
                {
                    **{k: v for k, v in record.items() if k != "output"},
                    **record["output"],
                }
                for record in records
            ]
        )


def _str_or_none(value: UUID | None) -> str | None:
    """Stringify an optional id for a query string.

    Args:
        value (UUID | None): The id, or ``None``.

    Returns:
        str | None: ``str(value)``, or ``None`` to omit the parameter.
    """
    return None if value is None else str(value)
