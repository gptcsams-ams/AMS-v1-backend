"""placeholder for DB migration that exists in production but has no local file"""

revision = "f1a2b3c4d5e6"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    pass  # already applied in DB


def downgrade():
    pass
