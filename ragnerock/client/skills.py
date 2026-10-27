"""Skill endpoints (``/api/skills/...``)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ragnerock.client._base import _ApiModel, _body, _Section


class SkillResponse(_ApiModel):
    """A skill: a project-scoped instruction package agents load on demand.

    Attributes:
        id (UUID): The skill's id.
        project_id (UUID | None): Owning project.
        name (str): Display and load name.
        description (str | None): The discovery text agents match tasks against.
        body (str | None): The markdown instructions an agent receives when it
            loads the skill.
        is_available (bool | None): Whether the skill is served to agents.
        operator_count (int | None): How many agents currently enable the skill.
        created_at (datetime | None): Creation time.
        updated_at (datetime | None): Last update time.
    """

    id: UUID
    project_id: UUID | None = None
    name: str
    description: str | None = None
    body: str | None = None
    is_available: bool | None = None
    operator_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SkillList(_ApiModel):
    """Paginated list response for skills."""

    skills: list[SkillResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class SkillDeleteResponse(_ApiModel):
    """Result of a skill deletion.

    Attributes:
        id (UUID): The deleted skill's id.
        operator_count (int): How many agents were unlinked from the skill.
        released_tool_count (int): How many tools the skill owned. They are not
            deleted; they become shared tools of the project.
    """

    id: UUID
    operator_count: int = 0
    released_tool_count: int = 0


class _SkillsSection(_Section):
    """Skills: named instruction packages agents load on demand.

    Attach skills to LLM agents through the ``skill_ids`` argument of
    ``client.operators.create`` / ``client.operators.update``. A skill can also
    own tools: pass its id as ``skill_id`` when creating a tool, and every
    agent that enables the skill can call it.
    """

    def list(self, project_id: UUID, *, skip: int = 0, limit: int = 100) -> SkillList:
        """List a project's skills.

        Calls ``GET /api/skills/``.

        Args:
            project_id (UUID): Project whose skills to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            SkillList: A page of skills plus the total count.
        """
        response = self._parent._request(
            "GET",
            "/api/skills/",
            params={"project_id": str(project_id), "skip": skip, "limit": limit},
        )
        return SkillList.model_validate(response.json())

    def get(self, skill_id: UUID) -> SkillResponse:
        """Fetch a single skill.

        Calls ``GET /api/skills/{skill_id}``.

        Args:
            skill_id (UUID): Skill to fetch.

        Returns:
            SkillResponse: The skill.

        Raises:
            NotFoundError: If no skill has that id.
        """
        response = self._parent._request("GET", f"/api/skills/{skill_id}")
        return SkillResponse.model_validate(response.json())

    def create(
        self,
        *,
        project_id: UUID,
        name: str,
        description: str,
        body: str,
        is_available: bool = True,
    ) -> SkillResponse:
        """Create a skill.

        Calls ``POST /api/skills/``.

        Args:
            project_id (UUID): Owning project.
            name (str): Display and load name; unique (case-insensitive) among
                the project's skills.
            description (str): The discovery text agents match tasks against.
                Say when to use the skill, not just what it is.
            body (str): The markdown instructions an agent receives when it
                loads the skill.
            is_available (bool): Whether the skill is served to agents.

        Returns:
            SkillResponse: The created skill.
        """
        payload = _body(
            project_id=project_id,
            name=name,
            description=description,
            body=body,
            is_available=is_available,
        )
        response = self._parent._request("POST", "/api/skills/", json_body=payload)
        return SkillResponse.model_validate(response.json())

    def update(
        self,
        skill_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        body: str | None = None,
        is_available: bool | None = None,
    ) -> SkillResponse:
        """Partially update a skill; omitted fields are left unchanged.

        Calls ``PUT /api/skills/{skill_id}``. Only the fields passed as
        non-``None`` are sent; no skill field can be cleared.

        Args:
            skill_id (UUID): Skill to update.
            name (str | None): New name.
            description (str | None): New discovery text.
            body (str | None): New markdown instructions.
            is_available (bool | None): New availability flag.

        Returns:
            SkillResponse: The updated skill.
        """
        payload = _body(
            name=name,
            description=description,
            body=body,
            is_available=is_available,
        )
        response = self._parent._request(
            "PUT", f"/api/skills/{skill_id}", json_body=payload
        )
        return SkillResponse.model_validate(response.json())

    def delete(self, skill_id: UUID) -> SkillDeleteResponse:
        """Delete a skill, unlinking it from every agent.

        Calls ``DELETE /api/skills/{skill_id}``. Tools the skill owned are not
        deleted; they become shared tools of the project.

        Args:
            skill_id (UUID): Skill to delete.

        Returns:
            SkillDeleteResponse: The deleted id, how many agents were unlinked,
            and how many tools were released.
        """
        response = self._parent._request("DELETE", f"/api/skills/{skill_id}")
        return SkillDeleteResponse.model_validate(response.json())
