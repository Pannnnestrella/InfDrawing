"""Create production persistence schema.

Revision ID: 0001_production_schema
Revises:
"""

from __future__ import annotations

from alembic import op

from app.production.models import Base

revision = "0001_production_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial API, job, artifact, provider, and audit tables."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Drop the initial schema."""
    Base.metadata.drop_all(bind=op.get_bind())
