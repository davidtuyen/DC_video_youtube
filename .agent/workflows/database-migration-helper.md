---
description: Create a new database migration and update schema
---
1. Modify the schema definition (e.g. `schema.prisma` or `models.py`)
2. Generate migration file (e.g. `npx prisma migrate dev` or `alembic revision`)
3. Apply migration to local database
4. Regenerate client types (if using an ORM like Prisma)
