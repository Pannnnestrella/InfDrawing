"""Create controlled-edit session and version tables.

Revision ID: 0002_controlled_edit
Revises: 0001_production_schema
"""

from __future__ import annotations

from alembic import op

from app.production.models import EditSessionRow, EditVersionRow

revision = "0002_controlled_edit"
down_revision = "0001_production_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the controlled-edit tables."""
    bind = op.get_bind()
    EditSessionRow.__table__.create(bind=bind, checkfirst=True)
    EditVersionRow.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Drop the controlled-edit tables."""
    bind = op.get_bind()
    EditVersionRow.__table__.drop(bind=bind, checkfirst=True)
    EditSessionRow.__table__.drop(bind=bind, checkfirst=True)
