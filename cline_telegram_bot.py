import asyncio
import os
from collections import deque

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from agent_client import AgentClientManager
from bot_logging import (
    DEBUG_DEBUG,
    DEBUG_ERROR,
    DEBUG_INFO,
    DEBUG_WARN,
    debug_log,
    log_chat_history_event,
)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "0"))


class ClineTelegramBot:
    def __init__(self):
        self.output_queue = deque()
        self.agent_manager = AgentClientManager(self.output_queue)
        self.session_active = False
        self.current_command = ""
        self.application: Application | None = None
        debug_log(DEBUG_INFO, "Telegram bot initialized")

    def is_waiting_for_input(self) -> bool:
        return False

    async def start_agent(self) -> bool:
        started = await self.agent_manager.start()
        if started:
            self.session_active = True
        return started

    async def stop_agent(self) -> None:
        await self.agent_manager.stop()
        self.session_active = False
        self.current_command = ""

    async def send_command_to_agent(self, text: str) -> None:
        if not self.session_active:
            raise RuntimeError("Session not active")
        await self.agent_manager.send_prompt(text)
        self.current_command = text

    async def cancel_agent(self) -> bool:
        if not self.session_active:
            return False
        return await self.agent_manager.cancel()

    def get_pending_output(self, max_length: int = 4000):
        if not self.output_queue:
            return None
        combined = ""
        while self.output_queue and len(combined) < max_length:
            chunk = self.output_queue.popleft()
            if len(combined) + len(chunk) > max_length:
                self.output_queue.appendleft(chunk)
                break
            combined += chunk
        result = combined.strip()
        debug_log(
            DEBUG_DEBUG,
            "Prepared output for Telegram",
            length=len(result),
            queue_size=len(self.output_queue),
        )
        return result

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message_text = update.message.text.strip() if update.message.text else ""

        is_command_message = message_text.startswith("/") if message_text else False
        log_chat_history_event(
            {
                "type": "user_input",
                "direction": "inbound",
                "user_id": user_id,
                "authorized": user_id == AUTHORIZED_USER_ID,
                "message_id": getattr(update.message, "message_id", None),
                "chat_id": update.effective_chat.id if update.effective_chat else None,
                "update_id": getattr(update, "update_id", None),
                "text": message_text,
                "is_command": is_command_message,
                "session_active": self.session_active,
            }
        )

        debug_log(
            DEBUG_DEBUG,
            "Received Telegram message",
            user_id=user_id,
            authorized_id=AUTHORIZED_USER_ID,
            text_preview=message_text[:50] if message_text else "",
        )

        if user_id != AUTHORIZED_USER_ID:
            debug_log(DEBUG_WARN, "Unauthorized user attempted access", user_id=user_id)
            await update.message.reply_text("❌ Unauthorized access")
            return

        if message_text.startswith("/agent"):
            parts = message_text.split()
            available = list(self.agent_manager.available_agent_types())
            if len(parts) == 1:
                await update.message.reply_text(
                    f"Current agent: `{self.agent_manager.current_agent_type}`\n"
                    f"Available: {', '.join(available)}"
                )
                return

            requested = parts[1].lower()
            if requested not in available:
                await update.message.reply_text(
                    f"Unsupported agent `{requested}`. Supported: {', '.join(available)}"
                )
                return

            await self.agent_manager.set_agent_type(requested)
            await update.message.reply_text(
                f"Switched to `{requested}` agent. Start a session with /start."
            )
            return

        if message_text == "/start":
            if not self.session_active:
                if await self.start_agent():
                    await update.message.reply_text("✅ Cline session started via ACP")
                else:
                    await update.message.reply_text("❌ Failed to start Cline session")
            else:
                await update.message.reply_text("ℹ️ Session already running")
            return

        if message_text == "/stop":
            if self.session_active:
                await self.stop_agent()
                await update.message.reply_text("🛑 Session stopped")
            else:
                await update.message.reply_text("ℹ️ No session to stop")
            return

        if message_text == "/status":
            status = "🟢 Running" if self.session_active else "🔴 Stopped"
            await update.message.reply_text(f"Status: {status}")
            return

        if message_text == "/cancel":
            if self.session_active:
                canceled = await self.cancel_agent()
                await update.message.reply_text("🛑 Cancel signal sent" if canceled else "⚠️ Unable to cancel")
                await asyncio.sleep(0.5)
                output = self.get_pending_output()
                if output:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=output)
            else:
                await update.message.reply_text("❌ No active session to cancel")
            return

        if message_text in ("/plan", "/act"):
            if self.session_active:
                await self.send_command_to_agent(message_text)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"⚡ Sent {message_text} to the agent",
                )
                await asyncio.sleep(0.5)
                output = self.get_pending_output()
                if output:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=output)
            else:
                await update.message.reply_text("❌ Start a session first")
            return

        if self.session_active:
            await self.send_command_to_agent(message_text)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="📤 Command sent")
            await asyncio.sleep(0.5)
            output = self.get_pending_output()
            if output:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=output)
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="⏳ Waiting for response...")
        else:
            await update.message.reply_text("❌ No active session. Use /start to begin.")


async def output_monitor(bot_instance: ClineTelegramBot, application: Application):
    debug_log(DEBUG_INFO, "Output monitor started")
    while True:
        if bot_instance.session_active and bot_instance.output_queue:
            output = bot_instance.get_pending_output()
            if output:
                await application.bot.send_message(chat_id=AUTHORIZED_USER_ID, text=output)
        await asyncio.sleep(1)


def main():
    debug_log(
        DEBUG_INFO,
        "main() initializing",
        token_present=bool(TELEGRAM_BOT_TOKEN),
        authorized_id=AUTHORIZED_USER_ID,
    )

    if not TELEGRAM_BOT_TOKEN:
        debug_log(DEBUG_ERROR, "TELEGRAM_BOT_TOKEN missing")
        print("ERROR: TELEGRAM_BOT_TOKEN must be set.")
        return

    bot = ClineTelegramBot()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    bot.application = application

    application.add_handler(CommandHandler("start", bot.handle_message))
    application.add_handler(CommandHandler("stop", bot.handle_message))
    application.add_handler(CommandHandler("status", bot.handle_message))
    application.add_handler(CommandHandler("plan", bot.handle_message))
    application.add_handler(CommandHandler("act", bot.handle_message))
    application.add_handler(CommandHandler("cancel", bot.handle_message))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message)
    )

    loop = asyncio.get_event_loop()
    loop.create_task(output_monitor(bot, application))

    try:
        application.run_polling()
    except Exception as exc:
        debug_log(DEBUG_ERROR, "Bot polling failed", error=str(exc))


if __name__ == "__main__":
    main()
