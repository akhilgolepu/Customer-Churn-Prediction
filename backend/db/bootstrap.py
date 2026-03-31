from __future__ import annotations

import uuid

from sqlalchemy import select

from db.models import Organization, Role
from db.session import PostgresSessionFactory


def ensure_postgres_baseline(session_factory: PostgresSessionFactory, desired_org_id: str) -> str:
    """Ensure baseline tenancy data exists and return the effective org id.

    The returned org id is safe to use for FK-constrained inserts.
    """
    desired_uuid = uuid.UUID(desired_org_id)
    default_slug = "default-org"

    with session_factory.session_scope() as session:
        org = session.execute(
            select(Organization).where(Organization.id == desired_uuid).limit(1)
        ).scalars().first()

        if org is None:
            org = session.execute(
                select(Organization).where(Organization.slug == default_slug).limit(1)
            ).scalars().first()

        if org is None:
            org = Organization(
                id=desired_uuid,
                name="Default Organization",
                slug=default_slug,
                status="active",
            )
            session.add(org)
            effective_org_id = str(desired_uuid)
        else:
            effective_org_id = str(org.id)

        existing_roles = {
            role.code
            for role in session.execute(
                select(Role).where(Role.deleted_at.is_(None))
            ).scalars().all()
        }

        for code, description in (
            ("admin", "Administrator"),
            ("analyst", "Analyst"),
            ("viewer", "Read-only viewer"),
        ):
            if code not in existing_roles:
                session.add(Role(code=code, description=description))

    return effective_org_id
