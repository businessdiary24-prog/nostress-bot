import os
import csv
import logging
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

# ─── Логирование ────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Конфиг ─────────────────────────────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN", "8784647952:AAHzGHp1LoN3wFSyMWdkuX3nboNpEsJbL_4")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")   # Заполни после первого запуска

# ─── Пути к файлам ───────────────────────────────────────────────────────────
DOCS_DIR = "docs"
POLICY_FILE     = os.path.join(DOCS_DIR, "Политика_обработки_ПД.pdf")
CONSENT_FILE    = os.path.join(DOCS_DIR, "Согласие_на_обработку_ПД.pdf")
NEWSLETTER_FILE = os.path.join(DOCS_DIR, "Согласие_на_рассылку.pdf")
CHECKLIST_FILE  = os.path.join(DOCS_DIR, "Как_обрабатывать_свои_эмоции.pdf")
DATA_FILE = "leads.csv"

# ─── Состояния диалога ───────────────────────────────────────────────────────
CONSENT, EMAIL, PHONE, INSTAGRAM = range(4)


# ════════════════════════════════════════════════════════════════════════════
# ШАГИ ВОРОНКИ
# ════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 1: приветствие + отправка документов + кнопка согласия"""
    user = update.effective_user

    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Сейчас пришлю тебе чек-лист по работе с эмоциями по методу O.W.E.C.A.N. — "
        "это практичный инструмент, к которому ты сможешь возвращаться снова и снова.\n\n"
        "Сначала три коротких документа — это формальность, но важная 🙏"
    )

    # Отправляем три PDF-документа
    for filepath, label in [
        (POLICY_FILE,     "Политика обработки персональных данных"),
        (CONSENT_FILE,    "Согласие на обработку персональных данных"),
        (NEWSLETTER_FILE, "Согласие на рекламную рассылку"),
    ]:
        with open(filepath, "rb") as f:
            await update.message.reply_document(document=f, filename=os.path.basename(filepath))

    # Кнопка согласия
    keyboard = [[InlineKeyboardButton(
        "✅ Ознакомилась и соглашаюсь",
        callback_data="consent_yes"
    )]]

    await update.message.reply_text(
        "☝️ Пожалуйста, прочитай документы выше.\n\n"
        "Нажимая кнопку, ты подтверждаешь согласие с политикой обработки "
        "персональных данных и получением рассылки от Ирины Рулевой.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return CONSENT


async def consent_given(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 2: согласие получено — просим email"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "✅ Спасибо!\n\n"
        "Осталось пару коротких вопросов — меньше минуты ⏱\n\n"
        "📧 На какую почту отправить чек-лист?"
    )

    return EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 3: сохраняем email — просим телефон"""
    email = update.message.text.strip()

    if "@" not in email or "." not in email:
        await update.message.reply_text(
            "Кажется, что-то не так с адресом 😊\n"
            "Попробуй ещё раз, например: hello@gmail.com"
        )
        return EMAIL

    context.user_data["email"] = email

    keyboard = [[KeyboardButton("📱 Поделиться номером", request_contact=True)]]
    await update.message.reply_text(
        "📱 Оставь номер телефона — иногда провожу голосовые разборы "
        "и пишу участницам напрямую.\n\n"
        "Можешь нажать кнопку или написать вручную:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, one_time_keyboard=True, resize_keyboard=True
        )
    )

    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 4: сохраняем телефон — просим Instagram"""
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()

    context.user_data["phone"] = phone

    await update.message.reply_text(
        "📸 И последнее — как тебя найти в Instagram?\n\n"
        "Напиши username (например @irina.ruleva.psy) или напиши «нет»",
        reply_markup=ReplyKeyboardRemove()
    )

    return INSTAGRAM


async def get_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 5: сохраняем Instagram, пишем в таблицу, отправляем чек-лист"""
    instagram = update.message.text.strip()
    user = update.effective_user

    context.user_data["instagram"] = instagram

    # ── Сохраняем лид в CSV ──────────────────────────────────────────────
    save_lead(
        telegram_id=user.id,
        telegram_username=f"@{user.username}" if user.username else "—",
        first_name=user.first_name or "—",
        email=context.user_data.get("email", "—"),
        phone=context.user_data.get("phone", "—"),
        instagram=instagram,
    )

    # ── Уведомление администратору ───────────────────────────────────────
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "🆕 *Новый лид!*\n\n"
                    f"👤 Имя: {user.first_name}\n"
                    f"💬 Telegram: @{user.username or '—'}\n"
                    f"📧 Email: {context.user_data.get('email')}\n"
                    f"📞 Телефон: {context.user_data.get('phone')}\n"
                    f"📸 Instagram: {instagram}\n"
                    f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление админу: {e}")

    # ── Отправляем чек-лист ──────────────────────────────────────────────
    with open(CHECKLIST_FILE, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename="Как_обрабатывать_свои_эмоции.pdf",
            caption=(
                "🎁 Держи свой чек-лист по методу O.W.E.C.A.N.!\n\n"
                "Сохрани его — и возвращайся каждый раз, когда эмоции захлёстывают 💜\n\n"
                "Я буду присылать сюда ещё много полезного, "
                "так что пока не прощаемся! До скорого 👋\n\n"
                "— Ирина @irina.ruleva.psy"
            )
        )

    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ════════════════════════════════════════════════════════════════════════════

def save_lead(telegram_id, telegram_username, first_name, email, phone, instagram):
    """Сохраняет данные лида в CSV-файл."""
    file_exists = os.path.exists(DATA_FILE)
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Дата", "Telegram ID", "Telegram", "Имя", "Email", "Телефон", "Instagram"])
        writer.writerow([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            telegram_id, telegram_username, first_name, email, phone, instagram
        ])


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога."""
    await update.message.reply_text(
        "Окей, до встречи! Если захочешь вернуться — просто напиши /start 👋",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ════════════════════════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CONSENT:   [CallbackQueryHandler(consent_given, pattern="^consent_yes$")],
            EMAIL:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            PHONE:     [
                MessageHandler(filters.CONTACT, get_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone),
            ],
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
