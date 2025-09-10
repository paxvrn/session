# This bot provides a mini app, inline keyboard options, and interactive
# session generators for both Pyrogram and Telethon.

import os
import random
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from pyrogram.enums import ParseMode
from telethon import TelegramClient

# --- CONFIGURATION ---
# It is highly recommended to use environment variables for your credentials in production.
# Use the python-dotenv library for local development to load these from a .env file.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://your-hosted-domain.com/mini_app.html")

# Check if credentials are set
if not all([API_ID, API_HASH, BOT_TOKEN]):
    print("Error: Please set API_ID, API_HASH, and BOT_TOKEN environment variables.")
    exit(1)

# List of available libraries for session generation
LIBRARIES = ["Pyrogram", "Telethon"]
DEVICE_OPTIONS = ["Pyrogram", "Telethon", "Pyrogram-asyncio", "Telethon-asyncio", "Custom Device"]

# Initialize the Pyrogram client
app = Client(
    "device_selector_bot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    parse_mode=ParseMode.MARKDOWN
)

# --- COMMAND AND HANDLERS ---

@app.on_message(filters.command("start"))
async def start_command(client, message):
    """
    Handles the /start command.
    Sends a message with both inline keyboard options and a Mini App button.
    """
    keyboard_buttons = [[InlineKeyboardButton(text=device, callback_data=device)] for device in DEVICE_OPTIONS]
    keyboard_buttons.append([InlineKeyboardButton(text="🎲 Random Device", callback_data="random")])

    mini_app_button = [InlineKeyboardButton(text="✨ Open Mini App", web_app=WebAppInfo(url=MINI_APP_URL))]
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons + [mini_app_button])

    await message.reply_text(
        "Hello! Please select a device or open the Mini App.\n\n"
        "You can also use these commands to generate a session string:\n"
        "• `/generate_pyrogram_session`\n"
        "• `/generate_telethon_session`",
        reply_markup=reply_markup
    )

@app.on_callback_query()
async def callback_handler(client, callback_query):
    """
    Handles button presses from the inline keyboard.
    """
    query_data = callback_query.data
    
    if query_data == "random":
        selected_device = random.choice(DEVICE_OPTIONS)
    else:
        selected_device = query_data
    
    await callback_query.edit_message_text(
        f"✅ You have selected: **{selected_device}**"
    )

@app.on_message(filters.web_app_data)
async def web_app_data_handler(client, message):
    """
    Handles data sent from the Telegram Mini App.
    """
    selected_device = message.web_app_data.data
    await message.reply_text(
        f"✅ You have selected the device: **{selected_device}**\n\n"
        "Now, choose a library to generate a session string for this device:\n"
        "• `/generate_pyrogram_session`\n"
        "• `/generate_telethon_session`"
    )

@app.on_message(filters.command("generate_pyrogram_session"))
async def generate_pyrogram_session_command(client, message):
    """
    Starts an interactive flow to generate a Pyrogram session string.
    """
    chat_id = message.chat.id
    try:
        await app.send_message(
            chat_id,
            "**Pyrogram Session Generation Started.**\n\n"
            "Please follow the instructions in the chat. The process will be interactive.\n\n"
            "**Warning:** Never share your session string. It gives full control over your account."
        )

        session_client = Client(
            name="session_generator",
            api_id=int(API_ID),
            api_hash=API_HASH,
            in_memory=True
        )
        
        # Connect the client and export the session string
        async with session_client:
            session_string = await session_client.export_session_string()
        
        await app.send_message(
            chat_id,
            "**✅ Pyrogram Session String Generated!**\n\n"
            f"```\n{session_string}\n```\n\n"
            "This string is only for you. Use it to log in to Pyrogram-based apps.",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        print(f"Error during Pyrogram session generation: {e}")
        await app.send_message(
            chat_id,
            f"❌ An error occurred during session generation. Please try again later."
        )

@app.on_message(filters.command("generate_telethon_session"))
async def generate_telethon_session_command(client, message):
    """
    Starts an interactive flow to generate a Telethon session string.
    """
    chat_id = message.chat.id
    try:
        await app.send_message(
            chat_id,
            "**Telethon Session Generation Started.**\n\n"
            "Please enter your phone number with country code (e.g., `+11234567890`):"
        )

        # Wait for the user's phone number
        phone_number_message = await app.wait_for_message(chat_id)
        phone_number = phone_number_message.text.strip()
        
        session_client = TelegramClient('telethon_session', int(API_ID), API_HASH)

        await session_client.connect()
        
        # Send a login code and prompt the user
        await session_client.send_code_request(phone_number)
        await app.send_message(chat_id, "Please enter the login code you received:")
        
        # Wait for the login code
        code_message = await app.wait_for_message(chat_id)
        code = code_message.text.strip()
        
        try:
            # Try to sign in with the code
            await session_client.sign_in(phone_number, code)
        except Exception as e:
            if "Password required" in str(e):
                await app.send_message(chat_id, "Please enter your Two-Factor Authentication password:")
                password_message = await app.wait_for_message(chat_id)
                password = password_message.text.strip()
                await session_client.sign_in(phone_number, password=password)
            else:
                raise e # Re-raise if it's an unexpected error

        session_string = session_client.session.save()
        await session_client.disconnect()

        await app.send_message(
            chat_id,
            "**✅ Telethon Session String Generated!**\n\n"
            f"```\n{session_string}\n```\n\n"
            "This string is only for you. Use it to log in to Telethon-based apps.",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        print(f"Error during Telethon session generation: {e}")
        await app.send_message(
            chat_id,
            f"❌ An error occurred during session generation: {e}. Please try again later."
        )

# Main entry point to start the bot
if __name__ == "__main__":
    # Start the bot as a Web Service on Render.
    app.run()
