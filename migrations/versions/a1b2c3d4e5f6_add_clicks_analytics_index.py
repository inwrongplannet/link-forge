"""add composite index on clicks for analytics

Revision ID: a1b2c3d4e5f6
Revises: 67076b87a3ad
Create Date: 2026-08-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '67076b87a3ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite index on (url_id, clicked_at) for analytics queries."""
    op.create_index(
        'ix_clicks_url_id_clicked_at',
        'clicks',
        ['url_id', 'clicked_at'],
    )


def downgrade() -> None:
    """Drop the composite index."""
    op.drop_index('ix_clicks_url_id_clicked_at', table_name='clicks')
