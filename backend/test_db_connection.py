import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

async def test_connection():
    load_dotenv()
    mongo_url = os.environ.get("MONGO_URL")
    print(f"Testing connection to: {mongo_url.split('@')[-1]}") # Hide credentials
    
    try:
        client = AsyncIOMotorClient(mongo_url)
        # The ismaster command is cheap and does not require auth.
        # But to test auth we should try to list collections or get server info
        await client.server_info()
        print("Successfully connected to MongoDB!")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
