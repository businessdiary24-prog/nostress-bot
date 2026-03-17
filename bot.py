import os
import json
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN          = os.getenv("BOT_TOKEN", "8784647952:AAHzGHp1LoN3wFSyMWdkuX3nboNpEsJbL_4")
ADMIN_CHAT_ID  = os.getenv("ADMIN_CHAT_ID", "")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1md6HVQOGNa3S1GYtx9TTq-YKXs9sX8hpdnYvute0uM8")

DOCS_DIR        = "docs"
POLICY_FILE     = os.path.join(DOCS_DIR, "Политика_обработки_ПД.pdf")
CONSENT_FILE    = os.path.join(DOCS_DIR, "Согласие_на_обработку_ПД.pdf")
NEWSLETTER_FILE = os.path.join(DOCS_DIR, "Согласие_на_рассылку.pdf")
CHECKLIST_FILE  = os.path.join(DOCS_DIR, "docs/Где я сейчас.pdf")

CONSENT, EMAIL, PHONE, INSTAGRAM = range(4)


def get_sheet():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS не задана")
    creds_dict = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


def save_lead(telegram_id, telegram_username, first_name, email, phone, instagram):
    try:
        sheet = get_sheet()
        if sheet.row_count == 0 or not sheet.cell(1, 1).value:
            sheet.append_row(["Дата", "Telegram ID", "Telegram", "Имя", "Email", "Телефон", "Instagram"])
        sheet.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            str(telegram_id), telegram_username, first_name, email, phone, instagram
        ])
        logger.info(f"Лид сохранён: {email}")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Сейчас пришлю тебе тест, на определение своего состояния.\n\n"
        "Сначала три коротких документа — формальность, но важная 🙏"
    )
    for filepath in [POLICY_FILE, CONSENT_FILE, NEWSLETTER_FILE]:
        with open(filepath, "rb") as f:
            await update.message.reply_document(document=f)
    keyboard = [[InlineKeyboardButton("✅ Ознакомилась и соглашаюсь", callback_data="consent_yes")]]
    await update.message.reply_text(
        "☝️ Пожалуйста, прочитай документы выше.\n\n"
        "Нажимая кнопку, ты подтверждаешь согласие с политикой обработки "
        "персональных данных и получением рассылки от Ирины Рулевой.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONSENT


async def consent_given(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✅ Спасибо!\n\n"
        "Осталось пару коротких вопросов — меньше минуты ⏱\n\n"
        "📧 На какую почту отправить чек-лист?"
    )
    return EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("Кажется, что-то не так с адресом 😊\nПопробуй ещё раз, например: hello@gmail.com")
        return EMAIL
    context.user_data["email"] = email
    keyboard = [[KeyboardButton("📱 Поделиться номером", request_contact=True)]]
    await update.message.reply_text(
        "📱 Оставь номер телефона — иногда провожу голосовые разборы и пишу участницам напрямую.\n\n"
        "Можешь нажать кнопку или написать вручную:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.contact.phone_number if update.message.contact else update.message.text.strip()
    context.user_data["phone"] = phone
    await update.message.reply_text(
        "📸 И последнее — как тебя найти в Instagram?\n\n"
        "Напиши username (например @irina.ruleva.psy) или напиши «нет»",
        reply_markup=ReplyKeyboardRemove()
    )
    return INSTAGRAM


async def get_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    instagram = update.message.text.strip()
    user = update.effective_user
    context.user_data["instagram"] = instagram

    save_lead(
        telegram_id=user.id,
        telegram_username=f"@{user.username}" if user.username else "—",
        first_name=user.first_name or "—",
        email=context.user_data.get("email", "—"),
        phone=context.user_data.get("phone", "—"),
        instagram=instagram,
    )

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "🆕 *Новый лид!*\n\n"
                    f"👤 {user.first_name}\n"
                    f"💬 @{user.username or '—'}\n"
                    f"📧 {context.user_data.get('email')}\n"
                    f"📞 {context.user_data.get('phone')}\n"
                    f"📸 {instagram}\n"
                    f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Уведомление не отправлено: {e}")

    with open(CHECKLIST_FILE, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename="Как_обрабатывать_свои_эмоции.pdf",
            caption=(
                "А вот и сам тест!\n\n"
                "Ответить на все вопросы и посчитай итоговый результат 🧡\n\n"
                "Я буду присылать сюда ещё много полезного, так что пока не прощаемся! До скорого 👋\n\n"
                "— Ирина @irina.ruleva.psy"
            )
        )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Окей, до встречи! Если захочешь вернуться — просто напиши /start 👋", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def main():
    app = Application.builder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CONSENT:   [CallbackQueryHandler(consent_given, pattern="^consent_yes$")],
            EMAIL:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            PHONE:     [MessageHandler(filters.CONTACT, get_phone), MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            INSTAGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_instagram)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv_handler)
    logger.info("✅ Бот nostressbyruleva запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
