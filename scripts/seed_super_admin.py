import asyncio
import os

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


async def seed_super_admin() -> None:
    email = os.getenv("SUPER_ADMIN_EMAIL", "admin@ams.local")
    password = os.getenv("SUPER_ADMIN_PASSWORD", "ChangeMe123!")
    name = os.getenv("SUPER_ADMIN_NAME", "Super Admin")

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            print(f"Super admin already exists: {email}")
            return

        user = User(
            name=name,
            email=email,
            password=hash_password(password),
            role="SUPER_ADMIN",
            branch_id=None,
            is_active=True,
            totp_enabled=False,
        )
        db.add(user)
        await db.commit()
        print(f"Super admin created: {email}")


if __name__ == "__main__":
    asyncio.run(seed_super_admin())
