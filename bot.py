import os
import time
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ==========================================
# 1. INITIALIZATION & CONFIGURATION
# ==========================================

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Configure logging to track bot events and errors
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Validate that the API token is present
if not TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN environment variable is missing. Please check your .env file.")
    exit(1)

# ==========================================
# 2. IN-MEMORY STORAGE (STATE SYSTEM)
# ==========================================

# Stores pending deletions: list of dicts with {"chat_id": int, "message_id": int, "added_at": float}
pending_deletions = []

# Stores group custom deletion delay configurations: dict mapping chat_id (int) -> delay_seconds (int)
# Defaults to 300 seconds (5 minutes) if not configured
chat_settings = {}
DEFAULT_DELAY_SECONDS = 300

# ==========================================
# 3. MESSAGE MONITORS & EVENTS
# ==========================================

async def monitor_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Message handler that detects stickers and animation/GIF messages in groups.
    Ignores all other message types like text, photos, video files, and documents.
    """
    chat = update.effective_chat
    if not chat or chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return

    message = update.message
    if not message:
        return

    # Check if the message is a sticker or a GIF/animation
    is_sticker = bool(message.sticker)
    is_gif = bool(message.animation)

    if is_sticker or is_gif:
        msg_type = "Sticker" if is_sticker else "GIF"
        logger.info(f"Recorded {msg_type} message {message.message_id} in group '{chat.title}' ({chat.id})")
        
        # Add to the queue of pending deletions with the current timestamp
        pending_deletions.append({
            "chat_id": chat.id,
            "message_id": message.message_id,
            "added_at": time.time()
        })

# ==========================================
# 4. COMMAND HANDLERS
# ==========================================

async def start_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a startup/help message explaining features, usage, setup, and commands.
    """
    help_text = (
        "🤖 **Sticker & GIF Deleter Bot**\n\n"
        "This bot automatically cleans groups by removing stickers and GIFs/animations.\n\n"
        "**Core Features:**\n"
        "• Automatically captures stickers & GIFs in groups.\n"
        "• Ignores text messages, photos, standard videos, and documents.\n"
        "• Runs a background cleanup job every 5 minutes.\n"
        "• Allows customizing the deletion delay per group.\n\n"
        "**Commands:**\n"
        "• `/setdelay <minutes>` - Sets custom delay before deletion (Admin only).\n"
        "• `/help` or `/start` - Displays this helper information.\n\n"
        "**Setup Steps:**\n"
        "1. Add this bot to your Telegram group.\n"
        "2. Promote the bot to an **Administrator**.\n"
        "3. Grant the bot the **Delete Messages** permission."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Allows group administrators to configure the deletion delay (in minutes).
    Usage: /setdelay <minutes> (e.g. /setdelay 5)
    If used without arguments, it displays the current configuration.
    """
    chat = update.effective_chat
    if not chat or chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("❌ This command can only be used in Telegram groups.")
        return

    user_id = update.effective_user.id
    try:
        # Check if the user is an administrator or owner of the group
        member = await context.bot.get_chat_member(chat.id, user_id)
        if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            await update.message.reply_text("⚠️ Only group administrators can modify the deletion delay.")
            return
    except Exception as e:
        logger.error(f"Failed to fetch chat member status: {e}")
        await update.message.reply_text("❌ Error verifying administrator status. Please try again.")
        return

    # If no arguments provided, show current configuration
    if not context.args or len(context.args) < 1:
        current_delay = chat_settings.get(chat.id, DEFAULT_DELAY_SECONDS)
        current_minutes = current_delay // 60
        await update.message.reply_text(
            f"ℹ️ **Current Delay Configuration:**\n"
            f"Stickers and GIFs in this group are deleted after **{current_minutes}** minute(s).\n\n"
            f"To change it, use: `/setdelay <minutes>` (e.g., `/setdelay 10`).",
            parse_mode="Markdown"
        )
        return

    # Validate argument to be a positive integer
    try:
        minutes = int(context.args[0])
        if minutes <= 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ Please specify a valid positive integer for minutes (e.g., `/setdelay 5`).", parse_mode="Markdown")
        return

    # Limit to maximum 48 hours because Telegram won't allow deleting messages older than 48 hours
    if minutes > 2880:
        await update.message.reply_text("❌ Telegram limits message deletions to 48 hours (2880 minutes). Please set a lower value.")
        return

    # Update in-memory configuration mapping
    chat_settings[chat.id] = minutes * 60
    logger.info(f"Updated deletion delay for chat {chat.id} to {minutes} minutes")
    await update.message.reply_text(f"✅ Success! Stickers and GIFs will now be deleted after **{minutes}** minute(s).", parse_mode="Markdown")

# ==========================================
# 5. BACKGROUND SCHEDULER & CLEANUP JOB
# ==========================================

async def delete_expired_messages_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Background job triggered periodically. Scans the stored queue of stickers & GIFs,
    deletes any messages that have expired based on the group's delay configuration,
    and handles potential exceptions gracefully (e.g., message already deleted, no permission).
    """
    current_time = time.time()
    to_delete = []
    remaining = []

    # Filter messages into expired (ready for deletion) and active lists
    for item in pending_deletions:
        chat_id = item["chat_id"]
        delay = chat_settings.get(chat_id, DEFAULT_DELAY_SECONDS)
        
        if current_time - item["added_at"] >= delay:
            to_delete.append(item)
        else:
            remaining.append(item)

    # Update global queue to only keep non-expired messages
    pending_deletions.clear()
    pending_deletions.extend(remaining)

    if not to_delete:
        return

    logger.info(f"Scheduler: Found {len(to_delete)} messages to delete. Processing...")

    # Execute deletion actions sequentially
    for item in to_delete:
        chat_id = item["chat_id"]
        message_id = item["message_id"]
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.info(f"Successfully deleted message {message_id} in group {chat_id}")
        except BadRequest as e:
            # Handles errors like "Message to delete not found" (e.g., deleted by a user or another bot)
            logger.warning(f"Unable to delete message {message_id} in {chat_id} (BadRequest): {e.message}")
        except Forbidden as e:
            # Handles errors like "Permission denied" or if the bot was removed from the group
            logger.warning(f"Permission denied or bot was kicked from group {chat_id} (Forbidden): {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error while deleting message {message_id} in group {chat_id}: {e}")

# ==========================================
# 6. PING SERVER (FOR FREE WEB HOSTING)
# ==========================================

async def start_ping_server(port: str):
    """
    A lightweight, non-blocking HTTP server to keep the bot alive on free hosting platforms like Render.
    """
    async def handle_ping(reader, writer):
        # Respond with standard HTTP 200 OK
        response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK"
        writer.write(response)
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    try:
        server = await asyncio.start_server(handle_ping, "0.0.0.0", int(port))
        logger.info(f"Ping server started on port {port} to keep the bot alive.")
        async with server:
            await server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start ping server: {e}")

async def post_init(application):
    """
    Runs inside the event loop during bot initialization. Schedules the ping server.
    """
    port = os.getenv("PORT")
    if port:
        asyncio.create_task(start_ping_server(port))

# ==========================================
# 7. MAIN FUNCTION & APPLICATION LIFECYCLE
# ==========================================

def main():
    """
    Configures and runs the Telegram bot application.
    """
    # Create the application build with post_init hook
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    # Get the job queue for background task scheduling
    job_queue = application.job_queue
    if not job_queue:
        logger.error("JobQueue is not available. Please ensure APScheduler is installed (pip install python-telegram-bot[job-queue]).")
        return

    # Schedule the cleanup job to run every 5 minutes (300 seconds)
    # The first run starts 10 seconds after bot boot
    job_queue.run_repeating(delete_expired_messages_job, interval=300, first=10)
    logger.info("Background deletion scheduler initialized: running every 5 minutes (300s).")

    # Command handlers
    application.add_handler(CommandHandler(["start", "help"], start_help))
    application.add_handler(CommandHandler("setdelay", set_delay))

    # Message handlers: listens specifically for stickers and GIFs in groups
    # filters.ChatType.GROUPS filters for both standard groups and supergroups
    # filters.Sticker.ALL detects any stickers (static, animated, video)
    # filters.ANIMATION detects animation messages (GIFs)
    group_media_filter = filters.ChatType.GROUPS & (filters.Sticker.ALL | filters.ANIMATION)
    application.add_handler(MessageHandler(group_media_filter, monitor_messages))

    # Start the bot using long polling
    logger.info("=" * 60)
    logger.info("🤖 STICKER & GIF DELETER BOT HAS STARTED!")
    logger.info("=" * 60)
    logger.info("Startup Instructions & Status:")
    logger.info("1. Bot token loaded successfully from environment/dotenv.")
    logger.info("2. Background scheduler initialized to clean up every 5 minutes.")
    logger.info("3. To make it work: Add this bot to a Telegram group.")
    logger.info("4. Promote it to Administrator with 'Delete Messages' permission.")
    logger.info("5. Optional: Send /setdelay <minutes> in the group to customize delay.")
    logger.info("=" * 60)
    logger.info("Waiting for stickers and GIFs to delete... Press Ctrl+C to stop.")
    logger.info("=" * 60)
    
    application.run_polling()

if __name__ == "__main__":
    main()
