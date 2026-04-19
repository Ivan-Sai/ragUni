"""Create admin user for testing. Run from backend directory with venv activated:
    cd backend && python ../scripts/create_admin.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings
from app.core.security import hash_password
from datetime import datetime, timezone

settings = get_settings()


async def main():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]

    # Create admin
    admin = await db.users.find_one({"email": "admin@test.com"})
    if admin:
        print(f"Admin already exists: {admin['email']}")
    else:
        await db.users.insert_one({
            "email": "admin@test.com",
            "hashed_password": hash_password("AdminPass1234"),
            "full_name": "Test Admin",
            "role": "admin",
            "faculty": "IT Faculty",
            "is_active": True,
            "is_approved": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": None,
        })
        print("Created admin: admin@test.com / AdminPass1234")

    # Create unapproved teacher for testing
    teacher = await db.users.find_one({"email": "testteacher1@test.com"})
    if teacher:
        print(f"Teacher already exists: {teacher['email']} approved={teacher.get('is_approved')}")
    else:
        await db.users.insert_one({
            "email": "testteacher1@test.com",
            "hashed_password": hash_password("TeacherPass1234"),
            "full_name": "Test Teacher One",
            "role": "teacher",
            "faculty": "IT Faculty",
            "department": "CS Department",
            "position": "Lecturer",
            "is_active": True,
            "is_approved": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": None,
        })
        print("Created teacher (unapproved): testteacher1@test.com / TeacherPass1234")

    # List all users
    print("\nAll users:")
    async for user in db.users.find({}, {"email": 1, "role": 1, "is_active": 1, "is_approved": 1}):
        print(f"  {user['email']} role={user['role']} active={user.get('is_active')} approved={user.get('is_approved')}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
