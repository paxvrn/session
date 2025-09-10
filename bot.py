# This bot provides a mini app and interactive session generators for Pyrogram and Telethon.

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

app = Client(
    "device_selector_bot",
    api_id=int(os.getenv("API_ID", 12345)),
    api_hash=os.getenv("API_HASH", "dummy_hash"),
    bot_token=BOT_TOKEN,
    parse_mode=ParseMode.MARKDOWN
)

# A simple in-memory state to track interactive login sessions
user_sessions = {}

# --- COMMAND AND HANDLERS ---

@app.on_message(filters.command("start"))
async def start_command(client, message):
    """
    Handles the /start command.
    Sends a message with both inline keyboard options and a Mini App button.
    """
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
    await start_interactive_session_generation(client, callback_query.message, "pyrogram")

@app.on_callback_query(filters.regex("telethon_session"))
async def telethon_session_callback(client, callback_query):
    await callback_query.answer("Starting Telethon session generation...", show_alert=False)
    await start_interactive_session_generation(client, callback_query.message, "telethon")

@app.on_message(filters.text & filters.private)
async def web_app_data_handler(client, message):
    """
    Handles data sent from the Telegram Mini App.
    """
    if message.web_app_data:
        data = json.loads(message.web_app_data.data)
        device = data.get("device")
        library = data.get("library")

        if device and library:
            await message.reply_text(
                f"✅ You have selected the device **{device}** and the library **{library}**.\n"
                f"To generate the session string, tap on the `🔑 {library} Session` button."
            )

async def start_interactive_session_generation(client, message, library_name):
    """
    Starts an interactive flow to generate a session string.
    """
    chat_id = message.chat.id

    await app.send_message(
        chat_id,
        f"**{library_name.capitalize()} Session Generation Started.**\n\n"
        "Please enter your API ID:"
    )
    user_sessions[chat_id] = {"client_type": library_name, "step": "api_id"}


@app.on_message(filters.private & filters.text & ~filters.command("start"))
async def interactive_login_handler(client, message):
    """
    Handles the interactive steps for session generation.
    """
    chat_id = message.chat.id
    user_state = user_sessions.get(chat_id)

    if not user_state:
        return

    client_type = user_state["client_type"]
    step = user_state["step"]

    try:
        if step == "api_id":
            user_state["api_id"] = message.text.strip()
            await message.reply_text("Please enter your API Hash:")
            user_state["step"] = "api_hash"
        
        elif step == "api_hash":
            user_state["api_hash"] = message.text.strip()
            await message.reply_text("Please enter your phone number with country code (e.g., `+11234567890`):")
            user_state["step"] = "phone_number"

        elif step == "phone_number":
            phone_number = message.text.strip()
            user_state["phone_number"] = phone_number
            
            if client_type == "pyrogram":
                session_client = Client(
                    name=str(chat_id),
                    api_id=int(user_state["api_id"]),
                    api_hash=user_state["api_hash"],
                    in_memory=True,
                )
                await session_client.connect()
                code = await session_client.send_code(phone_number)
                user_state["session_client"] = session_client
                user_state["phone_code_hash"] = code.phone_code_hash
                await message.reply_text("Please enter the login code you received:")
                user_state["step"] = "login_code"
            
            elif client_type == "telethon":
                session_client = TelegramClient(str(chat_id), int(user_state["api_id"]), user_state["api_hash"])
                await session_client.connect()
                await session_client.send_code_request(phone_number)
                user_state["session_client"] = session_client
                await message.reply_text("Please enter the login code you received:")
                user_state["step"] = "login_code"
        
        elif step == "login_code":
            code = message.text.strip()
            session_client = user_state["session_client"]
            
            if client_type == "pyrogram":
                phone_number = user_state["phone_number"]
                phone_code_hash = user_state["phone_code_hash"]
                await session_client.sign_in(phone_number, phone_code_hash, code)
                session_string = await session_client.export_session_string()
                await message.reply_text(f"✅ Pyrogram Session String:\n`{session_string}`")
                del user_sessions[chat_id]
                await session_client.disconnect()
            elif client_type == "telethon":
                phone_number = user_state["phone_number"]
                try:
                    await session_client.sign_in(phone_number, code)
                    session_string = session_client.session.save()
                    await message.reply_text(f"✅ Telethon Session String:\n`{session_string}`")
                    del user_sessions[chat_id]
                    await session_client.disconnect()
                except Exception as e:
                    if "Password required" in str(e):
                        await message.reply_text("Please enter your 2FA password:")
                        user_state["step"] = "2fa_password"
                    else:
                        await message.reply_text(f"❌ Login failed: {e}. Please try again.")
                        del user_sessions[chat_id]
                        await session_client.disconnect()
        
        elif step == "2fa_password":
            password = message.text.strip()
            session_client = user_state["session_client"]
            phone_number = user_state["phone_number"]
            try:
                await session_client.sign_in(phone_number, password=password)
                session_string = session_client.session.save()
                await message.reply_text(f"✅ Telethon Session String:\n`{session_string}`")
            except Exception as e:
                await message.reply_text(f"❌ 2FA login failed: {e}. Please try again.")
            finally:
                del user_sessions[chat_id]
                await session_client.disconnect()

    except Exception as e:
        if chat_id in user_sessions:
            del user_sessions[chat_id]
        await message.reply_text(f"❌ An unexpected error occurred: {e}. Please start over.")

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
