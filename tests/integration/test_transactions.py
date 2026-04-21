"""Unit-of-work: add / update / delete / commit / rollback / refresh.

Against a live instance we verify the *observable* contract of the unit of
work: staging has no server-side effects, commit populates server fields
on the local object, rollback discards pending work, refresh overwrites in
place, and a failed commit raises :class:`CommitError` with ``committed``
and ``pending`` populated.
"""

from __future__ import annotations

import pytest

from ragnerock import (
    ChunkType,
    CommitError,
    Document,
    NotFoundError,
    Operator,
    ValidationError,
)


def _fake_pdf(tmp_path, name: str) -> str:
    p = tmp_path / f"{name}.pdf"
    p.write_bytes(b"%PDF-1.4\n% fake\n%%EOF\n")
    return str(p)


class TestStagingIsLocalOnly:
    """Staged writes must not hit the server until commit."""

    def test_add_does_not_populate_id(self, session, unique_name, tmp_path):
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        assert doc.id is None, "id must not be set before commit"
        # And the resource is not discoverable.
        assert session.get(Document, name=unique_name) is None

        # Clean up the pending op so we don't leave state in the session.
        session.rollback()

    def test_delete_before_commit_does_not_remove_server_resource(
        self, session, unique_name, tmp_path
    ):
        """Staging delete on a persisted resource is local until commit."""
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        session.commit()
        try:
            # Stage a delete but don't commit.
            session.delete(doc)
            # Resource should still be visible via a fresh lookup.
            fetched = session.get(Document, id=doc.id)
            assert fetched is not None
            # Drop the staged delete.
            session.rollback()
        finally:
            # After rollback doc is still present on the server — clean it up.
            session.delete(doc)
            session.commit()


class TestCommitPopulatesServerFields:
    def test_server_fields_populated(self, session, unique_name, tmp_path):
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        session.commit()
        try:
            assert doc.id is not None
            assert doc.storage_path is not None
            assert doc.created_at is not None
        finally:
            session.delete(doc)
            session.commit()

    def test_commit_on_empty_queue_is_noop(self, session):
        session.commit()
        session.commit()  # still fine


class TestCommitOrder:
    """Ordering is observed via end-state: an add + update + delete in one commit
    should all land as atomic-looking operations when read back."""

    def test_mixed_add_update_delete_in_one_commit(
        self, session, unique_name, tmp_path
    ):
        to_create = Document(
            file_path=_fake_pdf(tmp_path, f"{unique_name}-a"),
            name=f"{unique_name}-a",
        )
        to_update_original = Document(
            file_path=_fake_pdf(tmp_path, f"{unique_name}-b"),
            name=f"{unique_name}-b",
        )
        to_delete_original = Document(
            file_path=_fake_pdf(tmp_path, f"{unique_name}-c"),
            name=f"{unique_name}-c",
        )
        # Seed the "update" and "delete" targets.
        session.add(to_update_original)
        session.add(to_delete_original)
        session.commit()

        # Stage a mixed commit.
        session.add(to_create)
        to_update_original.name = f"{unique_name}-b-renamed"
        session.update(to_update_original)
        session.delete(to_delete_original)
        session.commit()

        try:
            # Add happened.
            assert session.get(Document, id=to_create.id) is not None
            # Update happened.
            session.refresh(to_update_original)
            assert to_update_original.name == f"{unique_name}-b-renamed"
            # Delete happened.
            assert session.get(Document, id=to_delete_original.id) is None
        finally:
            session.delete(to_create)
            session.delete(to_update_original)
            session.commit()


class TestCommitFailure:
    def test_failure_populates_committed_and_pending(
        self, session, unique_name, tmp_path
    ):
        """A partial commit failure raises CommitError with committed/pending lists."""
        ok = Document(
            file_path=_fake_pdf(tmp_path, f"{unique_name}-ok"),
            name=f"{unique_name}-ok",
        )
        session.add(ok)
        session.commit()

        # Set up a failing update by deleting this document from another angle.
        to_delete = Document(
            file_path=_fake_pdf(tmp_path, f"{unique_name}-doomed"),
            name=f"{unique_name}-doomed",
        )
        session.add(to_delete)
        session.commit()
        doomed_id = to_delete.id
        session.delete(to_delete)
        session.commit()

        # Now queue: 1 successful add + 1 update of the deleted resource + 1 never-attempted add.
        success = Document(
            file_path=_fake_pdf(tmp_path, f"{unique_name}-success"),
            name=f"{unique_name}-success",
        )
        bad = Document(id=doomed_id, name=f"{unique_name}-update")
        session._bind(bad)
        unattempted = Document(
            file_path=_fake_pdf(tmp_path, f"{unique_name}-z"),
            name=f"{unique_name}-z",
        )

        session.add(success)
        session.update(bad)
        session.add(unattempted)

        with pytest.raises(CommitError) as exc_info:
            session.commit()

        err = exc_info.value
        assert success in err.committed
        assert bad in err.pending
        assert unattempted in err.pending
        assert isinstance(err.cause, NotFoundError)

        # Clean up successful writes.
        session.rollback()
        session.delete(success)
        session.delete(ok)
        session.commit()


class TestRollback:
    def test_rollback_discards_pending_writes(self, session, unique_name, tmp_path):
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        session.rollback()
        session.commit()  # no-op
        assert session.get(Document, name=unique_name) is None

    def test_rollback_empty_queue_is_fine(self, session):
        session.rollback()  # shouldn't raise


class TestRefresh:
    def test_refresh_overwrites_fields_in_place(self, session, unique_name, tmp_path):
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        session.commit()
        try:
            # Mutate the local copy; refresh should clobber it.
            doc.name = "local-only-change"
            session.refresh(doc)
            assert doc.name == unique_name
        finally:
            session.delete(doc)
            session.commit()

    def test_refresh_without_id_raises(self, session, unique_name, tmp_path):
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name))  # no id
        with pytest.raises(ValidationError):
            session.refresh(doc)


class TestStagingSemantics:
    def test_delete_after_add_is_local_only(self, session, unique_name, tmp_path):
        """Deleting a still-pending add drops the staged op entirely."""
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        session.delete(doc)
        session.commit()
        # Nothing was created.
        assert session.get(Document, name=unique_name) is None

    def test_double_add_is_noop(self, session, unique_name, tmp_path):
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        session.add(doc)  # must not raise; must not duplicate
        session.rollback()

    def test_update_requires_persisted_resource(self, session, unique_name, tmp_path):
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name))  # no id
        with pytest.raises(ValidationError):
            session.update(doc)

    def test_add_persisted_resource_raises(self, session, unique_name, tmp_path):
        """Adding an already-persisted resource is a user error."""
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        session.commit()
        try:
            with pytest.raises(ValidationError):
                session.add(doc)  # already has an id
        finally:
            session.delete(doc)
            session.commit()


class TestMixedTypeCommit:
    def test_add_operator_and_document_together(self, session, unique_name, tmp_path):
        op = Operator(
            name=unique_name,
            description="mixed-type test",
            jsonschema={"type": "object"},
            generation_prompt="p",
            chunk_type=ChunkType.DOCUMENT,
        )
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(op)
        session.add(doc)
        session.commit()

        try:
            assert op.id is not None
            assert doc.id is not None
        finally:
            session.delete(doc)
            session.commit()
            session.delete(op)
            session.commit()


class TestRunRequiresCommitted:
    """``session.run()`` refuses uncommitted resources — no autoflush."""

    def test_run_with_uncommitted_doc_raises(self, session, unique_name):
        from ragnerock import Workflow

        wf = Workflow(id="00000000-0000-0000-0000-000000000701", name=unique_name)
        doc = Document(file_path="./x.pdf")  # no id
        with pytest.raises(ValidationError):
            session.run(wf, documents=[doc])

    def test_run_with_uncommitted_workflow_raises(self, session, unique_name):
        from ragnerock import Workflow

        wf = Workflow(name=unique_name)  # no id
        doc = Document(id="00000000-0000-0000-0000-000000000101")
        with pytest.raises(ValidationError):
            session.run(wf, documents=[doc])
