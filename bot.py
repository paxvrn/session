# This bot provides a mini app and interactive session generators for Pyrogram and TelethoTelethonn.

import os
import random
import asyncio
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from pyrogram.enums import ParseMode
from telethon import TelegramClient

# --- CONFIGURATION ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://your-hosted-domain.com/mini_app.html")

if not BOT_TOKEN:
    print("Error: Please set BOT_TOKEN environment variable.")
    exit(1)

# Using an in-memory database for sessions
app = Client(
    "device_selector_bot",
    api_id=int(os.getenv("API_ID", 12345)),
    api_hash=os.getenv("API_HASH", "dummy_hash"),
    bot_token=BOT_TOKEN,
    parse_mode=ParseMode.MARKDOWN
)

# A dictionary to store conversation state for each user
user_states = {}

# --- HANDLERS ---

@app.on_message(filters.command("start"))
async def start_command(client, message):
    """
    Handles the /start command.
    Sends a message with both inline keyboard options and a Mini App button.
    """
    user_states.pop(message.chat.id, None)  # Clear state on start
    
    keyboard_buttons = [
        [InlineKeyboardButton(text="✨ Open Mini App", web_app=WebAppInfo(url=MINI_APP_URL))],
        [
            InlineKeyboardButton(text="🔑 Pyrogram Session", callback_data="pyrogram_session"),
            InlineKeyboardButton(text="🔑 Telethon Session", callback_data="telethon_session")
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    await message.reply_text(
        "Hello! Choose an option below to start generating a session string.",
        reply_markup=reply_markup
    )

@app.on_callback_query(filters.regex("pyrogram_session"))
async def pyrogram_session_callback(client, callback_query):
    await callback_query.answer("Starting Pyrogram session generation...", show_alert=False)
    await start_interactive_session(client, callback_query.message, "pyrogram")

@app.on_callback_query(filters.regex("telethon_session"))
async def telethon_session_callback(client, callback_query):
    await callback_query.answer("Starting Telethon session generation...", show_alert=False)
    await start_interactive_session(client, callback_query.message, "telethon")

async def start_interactive_session(client, message, client_type):
    """
    Initializes the interactive session generation flow.
    """
    chat_id = message.chat.id
    user_states[chat_id] = {"client_type": client_type, "step": "api_id"}
    await client.send_message(
        chat_id,
        f"**{client_type.capitalize()} Session Generation Started.**\n\n"
        "Please enter your **API ID**:"
    )

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def interactive_flow_handler(client, message):
    """
    Manages the conversational flow for session generation.
    """
    chat_id = message.chat.id
    user_data = user_states.get(chat_id)

    if not user_data:
        return

    step = user_data.get("step")
    client_type = user_data.get("client_type")
    user_input = message.text.strip()

    try:
        if step == "api_id":
            user_data["api_id"] = user_input
            user_data["step"] = "api_hash"
            await message.reply_text("Please enter your **API Hash**:")

        elif step == "api_hash":
            user_data["api_hash"] = user_input
            user_data["step"] = "phone_number"
            await message.reply_text("Please enter your **phone number** (e.g., `+11234567890`):")

        elif step == "phone_number":
            user_data["phone_number"] = user_input
            
            if client_type == "pyrogram":
                # Pyrogram login flow
                session_client = Client(
                    name=str(chat_id),
                    api_id=int(user_data["api_id"]),
                    api_hash=user_data["api_hash"],
                    in_memory=True,
                )
                await session_client.connect()
                sent_code = await session_client.send_code(user_input)
                user_data["session_client"] = session_client
                user_data["phone_code_hash"] = sent_code.phone_code_hash
                user_data["step"] = "login_code"
                await message.reply_text("Please enter the **login code** you received:")
            
            elif client_type == "telethon":
                # Telethon login flow
                session_client = TelegramClient(str(chat_id), int(user_data["api_id"]), user_data["api_hash"])
                await session_client.connect()
                await session_client.send_code_request(user_input)
                user_data["session_client"] = session_client
                user_data["step"] = "login_code"
                await message.reply_text("Please enter the **login code** you received:")

        elif step == "login_code":
            session_client = user_data["session_client"]
            if client_type == "pyrogram":
                await session_client.sign_in(user_data["phone_number"], user_data["phone_code_hash"], user_input)
                session_string = await session_client.export_session_string()
                await message.reply_text(f"✅ Pyrogram Session String:\n`{session_string}`")
                await session_client.disconnect()
            
            elif client_type == "telethon":
                try:
                    await session_client.sign_in(user_data["phone_number"], user_input)
                    session_string = session_client.session.save()
                    await message.reply_text(f"✅ Telethon Session String:\n`{session_string}`")
                    await session_client.disconnect()
                except Exception as e:
                    if "password required" in str(e).lower():
                        user_data["step"] = "2fa_password"
                        await message.reply_text("Please enter your **2FA password**:")
                    else:
                        await message.reply_text(f"❌ Login failed: {e}. Please try again.")
                        await session_client.disconnect()
            
            # Reset state for successful login
            user_states.pop(chat_id)
        
        elif step == "2fa_password":
            session_client = user_data["session_client"]
            try:
                await session_client.sign_in(user_data["phone_number"], password=user_input)
                session_string = session_client.session.save()
                await message.reply_text(f"✅ Telethon Session String:\n`{session_string}`")
            except Exception as e:
                await message.reply_text(f"❌ 2FA login failed: {e}. Please try again.")
            finally:
                user_states.pop(chat_id)
                await session_client.disconnect()
    
    except Exception as e:
        if chat_id in user_states:
            del user_states[chat_id]
        await message.reply_text(f"❌ An unexpected error occurred: {e}. Please start over with `/start`.")

@app.on_message(filters.web_app_data)
async def web_app_data_handler(client, message):
    """
    Handles data sent from the Telegram Mini App.
    """
    data = json.loads(message.web_app_data.data)
    device = data.get("device")
    library = data.get("library")

    if device and library:
        await message.reply_text(
            f"✅ You have selected the device **{device}** and the library **{library}**.\n"
            f"To generate the session string, tap on the `🔑 {library} Session` button."
        )

# Simple handler to satisfy Render's port requirement
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is running.")

def start_http_server():
    port = int(os.environ.get('PORT', 8080))
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    httpd.serve_forever()

if __name__ == "__main__":
    http_thread = threading.Thread(target=start_http_server)
    http_thread.daemon = True
    http_thread.start()
    app.run()
