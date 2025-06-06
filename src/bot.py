#initialise le bot telegram et il a relation avec notification_service.py assurée par le token pour gerer les alertes
import os
import re
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram import Update
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ENV = PROJECT_ROOT / '.env'
load_dotenv(ENV, override=True)

# Pre-escaped message templates
WELCOME_MESSAGE = """
HELLO !
"""
HELP_MESSAGE = """
ALERTE !
"""

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command with user name escaping"""
    if not update.message or not (user := update.effective_user):
        return
    # Escape special characters in user's first name
    safe_name = re.sub(r'([_*\[\]()~`>#+=|{}.!-])', r'\\\1', user.first_name or "User")

    await update.message.reply_text(
        WELCOME_MESSAGE.format(safe_name),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👨💻 LinkedIn", url="https://www.linkedin.com"),  
                InlineKeyboardButton(
                    "📂 GitHub", url="https://github.com/"),  
            ],
            [InlineKeyboardButton("❓ Need Help?", callback_data="send_help")]
        ]),
        parse_mode="MarkdownV2"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    if update.message:
        await update.message.reply_text(HELP_MESSAGE, parse_mode="MarkdownV2")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button interactions"""
    if query := update.callback_query:
        await query.answer()
        if query.data == "send_help":
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=HELP_MESSAGE,
                parse_mode="MarkdownV2"
            )

def main() -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(token).build()
    application.add_handlers([
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
        CallbackQueryHandler(button_handler)
    ])

    print("Bot is running...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
