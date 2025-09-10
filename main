# This is the main bot script that handles user interaction.
# It uses a conversational flow with inline keyboards for a "production-grade" UX.

import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Local import for session generation logic
from session_generator import generate_pyrogram_session, generate_telethon_session

# Set up logging for the bot
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# State management for the bot's conversation flow
USER_STATE = {}

# Get environment variables
try:
    API_ID = os.environ["API_ID"]
    API_HASH = os.environ["API_HASH"]
    BOT_TOKEN = os.environ["BOT_TOKEN"]
except KeyError as e:
    logging.error(f"Missing required environment variable: {e}")
    exit(1)

# Pyrogram bot client
app = Client(
    name="SessionBot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    """Handles the /start command and begins the conversation flow."""
    welcome_text = (
        "Hello! I am a bot that can generate Pyrogram and Telethon session strings "
        "with enhanced security and device spoofing. "
        "This helps reduce the chances of your account being banned."
    )
    start_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("Begin Session Generation", callback_data="start_generation")]
    ])
    await message.reply_text(welcome_text, reply_markup=start_button)

@app.on_callback_query()
async def callback_query_handler(client, callback_query):
    """Handles all button presses from inline keyboards."""
    data = callback_query.data
    user_id = callback_query.from_user.id
    await callback_query.answer()
    
    if data == "start_generation":
        await client.send_message(
            user_id,
            "Please choose the library for which you want to generate a session string.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Pyrogram", callback_data="generate_pyrogram")],
                [InlineKeyboardButton("Telethon", callback_data="generate_telethon")]
            ])
        )
    elif data in ["generate_pyrogram", "generate_telethon"]:
        # Set up a new conversation state for the user
        USER_STATE[user_id] = {"stage": "awaiting_phone", "library": data.split('_')[1]}
        await client.send_message(
            user_id,
            "Please send your phone number with the country code (e.g., `+15551234567`)."
        )
    elif data == "generate_again":
        USER_STATE.pop(user_id, None)
        await start_command(client, callback_query.message)

@app.on_message(filters.private & filters.text)
async def text_handler(client, message):
    """Handles user text input based on the current conversation state."""
    user_id = message.from_user.id
    current_state = USER_STATE.get(user_id, {})

    if current_state.get("stage") == "awaiting_phone":
        phone_number = message.text
        current_state["phone_number"] = phone_number
        current_state["stage"] = "awaiting_code"
        USER_STATE[user_id] = current_state
        await message.reply_text("Please check your Telegram app for the authentication code and send it here.")

        # Trigger session generation in a separate task
        asyncio.create_task(run_session_generation(user_id, current_state))
        
    elif current_state.get("stage") == "awaiting_code":
        # Store the code received from the user
        current_state["code"] = message.text
        USER_STATE[user_id] = current_state
        # The session generation task will pick up this value automatically
        await message.reply_text("Processing your request...")

async def run_session_generation(user_id, state):
    """Starts the session generation process."""
    library = state["library"]
    phone_number = state["phone_number"]
    
    async def code_callback():
        """Callback to wait for the user to send the authentication code."""
        while "code" not in USER_STATE.get(user_id, {}):
            await asyncio.sleep(1) # Wait for the user to input the code
        return USER_STATE[user_id]["code"]

    session_string = None
    if library == "pyrogram":
        session_string = await generate_pyrogram_session(API_ID, API_HASH, phone_number, code_callback)
    elif library == "telethon":
        session_string = await generate_telethon_session(API_ID, API_HASH, phone_number, code_callback)

    if session_string:
        # Create an in-memory file and send it
        file_path = f"{library}_session.txt"
        with open(file_path, "w") as f:
            f.write(session_string)
        
        await app.send_document(
            user_id,
            file_path,
            caption=f"✅ Your {library.capitalize()} session string has been generated and saved to the file below. **Keep this secure!**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Generate Another Session", callback_data="generate_again")]
            ])
        )
        os.remove(file_path)
    else:
        await app.send_message(
            user_id,
            "❌ Session generation failed. Please check your credentials and try again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Try Again", callback_data="generate_again")]
            ])
        )

if __name__ == "__main__":
    app.run()
