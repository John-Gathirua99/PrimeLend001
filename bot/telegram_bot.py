

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Ai_Loan_System.settings")
django.setup()

from application.models import ChatMessage

BOT_TOKEN = "8721585715:AAH5B7cwdlw4mwCHJsb3vUXyDXN0mtgBfAU"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.chat_id)
    text = update.message.text

    # 🔹 Simple AI logic
    if "loan" in text.lower():
        response = "We offer loans. Tell me your monthly income."
        escalated = False
    else:
        response = "I'm not sure. I've forwarded your request to admin."
        escalated = True

    # Save to DB
    ChatMessage.objects.create(
        user_id=user_id,
        message=text,
        response=response,
        escalated=escalated
    )

    await update.message.reply_text(response)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle_message))

if __name__ == "__main__":
    app.run_polling()



from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! How can I help you today?")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"You said: {update.message.text}")

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

app.run_polling()
