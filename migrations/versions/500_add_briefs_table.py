"""Add briefs table

Revision ID: 500
Revises: 490
Create Date: 2016-01-25 15:45:50.363821

"""

# revision identifiers, used by Alembic.
revision = '500'
down_revision = '490'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('briefs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('data', postgresql.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_briefs_created_at'), 'briefs', ['created_at'], unique=False)
    op.create_index(op.f('ix_briefs_updated_at'), 'briefs', ['updated_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_briefs_updated_at'), table_name='briefs')
    op.drop_index(op.f('ix_briefs_created_at'), table_name='briefs')
    op.drop_table('briefs')
