#gerer les utilisateurs par leur chatID 
import os
import asyncio
from notification_service import FlareGuardBot  
from dotenv import load_dotenv


load_dotenv()

async def force_update():
    # Get your bot token from environment variable
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_TOKEN environment variable not set")
        return

    try:
        # Initialize bot
        bot = FlareGuardBot(token)

        # Force update chat IDs
        print("Updating chat IDs...")
        await bot.initialize()

        # Read and display current chat IDs
        print("\nCurrent chat IDs:")
        for i, chat_id in enumerate(bot.chat_ids, 1):
            print(f"{i}. Chat ID: {chat_id}")

    except Exception as e:
        print(f"Error during update: {str(e)}")

if __name__ == "__main__":
    asyncio.run(force_update())
