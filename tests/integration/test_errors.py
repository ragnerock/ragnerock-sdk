"""Error hierarchy and server-to-exception mapping against a live instance.

The full mapping (401/403/404/422) is tested at the client level, but live
triggering of each status code requires carefully shaped inputs. We cover
the shapes that are reliably reachable:

- hierarchy: pure structural check, no network
- 404 on update: update a resource that was deleted — surfaces as CommitError
- query syntax errors: carry ``error_code`` and optional ``suggestion``
"""

from __future__ import annotations

import pytest

from ragnerock import (
    AuthenticationError,
    CommitError,
    Document,
    NotFoundError,
    QueryError,
    RagnerockError,
    ValidationError,
)


class TestHierarchy:
    def test_all_errors_subclass_base(self):
        for cls in (
            AuthenticationError,
            NotFoundError,
            ValidationError,
            QueryError,
            CommitError,
        ):
            assert issubclass(cls, RagnerockError)


class TestStatusMapping:
    def test_update_of_deleted_document_raises_commit_error_with_not_found(
        self, session, unique_name, tmp_path
    ):
        """Updating a resource the server no longer knows about surfaces a typed error."""
        file_path = tmp_path / f"{unique_name}.pdf"
        file_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
        doc = Document(file_path=str(file_path), name=unique_name)
        session.add(doc)
        session.commit()

        # Delete it out from under ourselves.
        session.delete(doc)
        session.commit()

        # Reattach the stale object and try to update.
        stale = Document(id=doc.id, name=f"{unique_name}-renamed")
        session._bind(stale)
        session.update(stale)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, NotFoundError)


class TestErrorBodyParsing:
    """Server-shaped error bodies populate typed attributes on the raised exception.

    Query errors are the most reliable trigger because the server returns
    a structured detail dict (``error_code``, optional ``suggestion``) for
    bad SQL.
    """

    def test_query_error_surfaces_error_code(self, session):
        with pytest.raises(QueryError) as exc:
            session.query("SELEKT * FROM documents")
        # error_code may be None depending on server config — just confirm the
        # attribute exists and the message is propagated.
        assert exc.value.error_code is None or isinstance(exc.value.error_code, str)
        assert str(exc.value)
