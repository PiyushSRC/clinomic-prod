import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

async def reset_users():
    load_dotenv()
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    
    print(f"Connecting to {db_name}...")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Delete demo users to force re-seeding from default credentials
    users_to_reset = ["lab", "admin", "doctor"]
    
    for username in users_to_reset:
        result = await db.users.delete_many({"id": username})
        if result.deleted_count > 0:
            print(f"Deleted user '{username}' (Count: {result.deleted_count}) - Will be re-created on next login.")
        else:
            print(f"User '{username}' not found in DB (Clean state).")

if __name__ == "__main__":
    asyncio.run(reset_users())
