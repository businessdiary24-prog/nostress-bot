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

# ─── Состояния ───────────────────────────────────────────────────────────────
CONSENT, EMAIL, PHONE, INSTAGRAM, QUIZ = range(5)

# ─── Тест ────────────────────────────────────────────────────────────────────
QUESTIONS = [
    "Я просыпаюсь уже уставшей — даже если спала достаточно.",
    "Вещи, которые раньше радовали или вдохновляли, теперь не вызывают почти ничего.",
    "Я раздражаюсь на мелочи, которые раньше не цепляли, — или, наоборот, мне всё безразлично.",
    "Я постоянно чувствую, что не успеваю, не дотягиваю или делаю недостаточно.",
    "Мне стало сложнее концентрироваться: забываю, теряю мысль, не могу дочитать текст до конца.",
    "Тело напоминает о себе: головные боли, зажимы в шее и плечах, проблемы со сном или пищеварением.",
    "Я отдаляюсь от людей — меньше хочется общаться, отвечать на сообщения, быть «на связи».",
    "У меня есть ощущение, что я работаю на автопилоте — делаю, что нужно, но как будто не присутствую.",
    "Отдых не помогает: выходные или отпуск заканчиваются, а ощущение усталости остаётся.",
    "Я ловлю себя на мысли «я больше не могу так» — но не понимаю, что именно менять.",
]

ANSWERS = [
    ("Совсем не про меня", 0),
    ("Иногда", 1),
    ("Часто", 2),
    ("Почти всегда", 3),
]

RESULTS = [
    {
        "min": 0, "max": 7,
        "title": "🟢 Ресурсное состояние",
        "text": (
            "Стресс есть, но ты справляешься. Хорошее время, чтобы укрепить навыки "
            "регуляции — не когда горит, а когда есть силы учиться.\n\n"
            "Программа «Стабилизация» поможет закрепить это состояние и создать "
            "устойчивую опору на будущее — пока ресурс есть."
        ),
        "cta": "Хочешь узнать подробнее о программе? Напиши слово *Стресс* в личку Ирине 👉 https://t.me/irinkaruleva_coach"
    },
    {
        "min": 8, "max": 15,
        "title": "🟡 Хронический стресс",
        "text": (
            "Нервная система работает в режиме повышенной нагрузки. Ты ещё "
            "функционируешь, но ресурс тает.\n\n"
            "Это зона, где инструменты саморегуляции дают максимальный эффект — "
            "ты ловишь процесс до того, как он стал выгоранием."
        ),
        "cta": "Программа «Стабилизация» создана именно для этой точки. Напиши слово *Стресс* в личку Ирине 👉 https://t.me/irinkaruleva_coach"
    },
    {
        "min": 16, "max": 23,
        "title": "🟠 На пороге выгорания",
        "text": (
            "Тело и психика посылают сигналы, которые уже сложно игнорировать. "
            "Усталость не проходит, мотивация падает, эмоции «тускнеют» или, "
            "наоборот, выходят из-под контроля.\n\n"
            "Тебе нужны конкретные инструменты — и поддержка рядом."
        ),
        "cta": "Программа «Стабилизация» создана именно для тебя. Напиши слово *Стресс* в личку Ирине 👉 https://t.me/irinkaruleva_coach"
    },
    {
        "min": 24, "max": 30,
        "title": "🔴 Выгорание",
        "text": (
            "Ты давно работаешь на износ. Это не слабость — это нервная система, "
            "которая исчерпала ресурс восстановления.\n\n"
            "Инструменты курса помогут начать стабилизацию. Мы также рекомендуем "
            "параллельно обратиться к психологу или психотерапевту, чтобы пройти "
            "этот путь с поддержкой."
        ),
        "cta": "Программа «Стабилизация» — первый шаг к восстановлению. Напиши слово *Стресс* в личку Ирине 👉 https://t.me/irinkaruleva_coach"
    },
]


# ════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS
# ════════════════════════════════════════════════════════════════════════════

def get_sheet():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS не задана")
    creds_dict = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


def save_lead(telegram_id, telegram_username, first_name, email, phone, instagram, score, level):
    try:
        sheet = get_sheet()
        if sheet.row_count == 0 or not sheet.cell(1, 1).value:
            sheet.append_row(["Дата", "Telegram ID", "Telegram", "Имя", "Email", "Телефон", "Instagram", "Баллы", "Уровень"])
        sheet.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            str(telegram_id), telegram_username, first_name, email, phone, instagram, score, level
        ])
        logger.info(f"Лид сохранён: {email}, баллы: {score}")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")


# ════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ════════════════════════════════════════════════════════════════════════════

def get_question_keyboard(question_idx):
    """Кнопки ответов для вопроса."""
    keyboard = []
    for label, score in ANSWERS:
        keyboard.append([InlineKeyboardButton(label, callback_data=f"q_{question_idx}_{score}")])
    return InlineKeyboardMarkup(keyboard)


def get_result(score):
    for r in RESULTS:
        if r["min"] <= score <= r["max"]:
            return r
    return RESULTS[-1]


# ════════════════════════════════════════════════════════════════════════════
# ВОРОНКА: СБОР КОНТАКТОВ
# ════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я помогу тебе пройти экспресс-тест на уровень стресса и выгорания.\n\n"
        "Сначала три коротких документа — формальность, но важная 🙏"
    )
    for filepath in [POLICY_FILE, CONSENT_FILE, NEWSLETTER_FILE]:
        with open(filepath, "rb") as f:
            await update.message.reply_document(document=f)
    keyboard = [[InlineKeyboardButton("✅ Ознакомилась и соглашаюсь", callback_data="consent_yes")]]
    await update.message.reply_text(
        "☝️ Нажимая кнопку, ты подтверждаешь согласие с политикой обработки "
        "персональных данных и получением рассылки от Ирины Рулевой.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONSENT


async def consent_given(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✅ Спасибо!\n\n"
        "Пару быстрых вопросов — меньше минуты ⏱\n\n"
        "📧 На какую почту отправить результаты теста?"
    )
    return EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("Кажется, адрес неверный 😊 Попробуй ещё раз:")
        return EMAIL
    context.user_data["email"] = email
    keyboard = [[KeyboardButton("📱 Поделиться номером", request_contact=True)]]
    await update.message.reply_text(
        "📱 Оставь номер телефона:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.contact.phone_number if update.message.contact else update.message.text.strip()
    context.user_data["phone"] = phone
    await update.message.reply_text(
        "📸 Как тебя найти в Instagram? (напиши username или «нет»)",
        reply_markup=ReplyKeyboardRemove()
    )
    return INSTAGRAM


async def get_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["instagram"] = update.message.text.strip()
    context.user_data["answers"] = []

    await update.message.reply_text(
        "Отлично! 🎯\n\n"
        "Теперь пройдём тест «Где я сейчас?» — 10 утверждений, займёт 2–3 минуты.\n\n"
        "Оцени каждое утверждение честно — результат будет точнее 🧡"
    )
    await send_question(update.message, context, 0)
    return QUIZ


# ════════════════════════════════════════════════════════════════════════════
# ТЕСТ
# ════════════════════════════════════════════════════════════════════════════

async def send_question(message_obj, context, idx):
    text = f"*Вопрос {idx + 1} из {len(QUESTIONS)}*\n\n{QUESTIONS[idx]}"
    await message_obj.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_question_keyboard(idx)
    )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data  # формат: q_<idx>_<score>
    _, idx_str, score_str = data.split("_")
    idx = int(idx_str)
    score = int(score_str)

    answers = context.user_data.get("answers", [])
    answers.append(score)
    context.user_data["answers"] = answers

    # Подтверждаем выбор
    answer_label = ANSWERS[score][0]
    await query.edit_message_text(
        f"*Вопрос {idx + 1} из {len(QUESTIONS)}*\n\n{QUESTIONS[idx]}\n\n✅ _{answer_label}_",
        parse_mode="Markdown"
    )

    next_idx = idx + 1

    if next_idx < len(QUESTIONS):
        await send_question(query.message, context, next_idx)
        return QUIZ
    else:
        await finish_quiz(query, context)
        return ConversationHandler.END


async def finish_quiz(query, context):
    user = query.from_user
    answers = context.user_data.get("answers", [])
    total = sum(answers)
    result = get_result(total)

    # Сохраняем лид
    save_lead(
        telegram_id=user.id,
        telegram_username=f"@{user.username}" if user.username else "—",
        first_name=user.first_name or "—",
        email=context.user_data.get("email", "—"),
        phone=context.user_data.get("phone", "—"),
        instagram=context.user_data.get("instagram", "—"),
        score=total,
        level=result["title"]
    )

    # Уведомление администратору
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "🆕 *Новый лид + тест!*\n\n"
                    f"👤 {user.first_name}\n"
                    f"💬 @{user.username or '—'}\n"
                    f"📧 {context.user_data.get('email')}\n"
                    f"📞 {context.user_data.get('phone')}\n"
                    f"📸 {context.user_data.get('instagram')}\n"
                    f"📊 Баллы: {total} — {result['title']}\n"
                    f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Уведомление не отправлено: {e}")

    # Результат пользователю
    await query.message.reply_text(
        f"✨ *Твой результат: {total} из 30 баллов*\n\n"
        f"*{result['title']}*\n\n"
        f"{result['text']}\n\n"
        "——\n"
        "_Этот тест — не клинический диагноз. Он помогает увидеть общую картину "
        "и понять, где ты сейчас. Если результат тебя встревожил — это не повод "
        "для паники, а повод для первого шага._",
        parse_mode="Markdown"
    )

    # CTA отдельным сообщением
    await query.message.reply_text(
        f"🌿 Программа «Стабилизация»\n\n{result['cta']}",
        disable_web_page_preview=True
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Окей, до встречи! Напиши /start чтобы вернуться 👋",
                                    reply_markup=ReplyKeyboardRemove())
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
            PHONE:     [MessageHandler(filters.CONTACT, get_phone),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            INSTAGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_instagram)],
            QUIZ:      [CallbackQueryHandler(handle_answer, pattern="^q_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    logger.info("✅ Бот nostressbyruleva запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()    "Мне стало сложнее концентрироваться: забываю, теряю мысль, не могу дочитать текст до конца.",
    "Тело напоминает о себе: головные боли, зажимы в шее и плечах, проблемы со сном или пищеварением.",
    "Я отдаляюсь от людей — меньше хочется общаться, отвечать на сообщения, быть «на связи».",
    "У меня есть ощущение, что я работаю на автопилоте — делаю, что нужно, но как будто не присутствую.",
    "Отдых не помогает: выходные или отпуск заканчиваются, а ощущение усталости остаётся.",
    "Я ловлю себя на мысли «я больше не могу так» — но не понимаю, что именно менять.",
]

ANSWERS = [
    ("Совсем не про меня", 0),
    ("Иногда", 1),
    ("Часто", 2),
    ("Почти всегда", 3),
]

RESULTS = [
    {
        "min": 0, "max": 7,
        "title": "🟢 Ресурсное состояние",
        "text": (
            "Стресс есть, но ты справляешься. Хорошее время, чтобы укрепить навыки "
            "регуляции — не когда горит, а когда есть силы учиться.\n\n"
            "Программа «Стабилизация» поможет закрепить это состояние и создать "
            "устойчивую опору на будущее — пока ресурс есть."
        ),
        "cta": "Хочешь узнать подробнее о программе? Напиши слово *Стресс* в личку Ирине 👉 https://t.me/irinkaruleva_coach"
    },
    {
        "min": 8, "max": 15,
        "title": "🟡 Хронический стресс",
        "text": (
            "Нервная система работает в режиме повышенной нагрузки. Ты ещё "
            "функционируешь, но ресурс тает.\n\n"
            "Это зона, где инструменты саморегуляции дают максимальный эффект — "
            "ты ловишь процесс до того, как он стал выгоранием."
        ),
        "cta": "Программа «Стабилизация» создана именно для этой точки. Напиши слово *Стресс* в личку Ирине 👉 https://t.me/irinkaruleva_coach"
    },
    {
        "min": 16, "max": 23,
        "title": "🟠 На пороге выгорания",
        "text": (
            "Тело и психика посылают сигналы, которые уже сложно игнорировать. "
            "Усталость не проходит, мотивация падает, эмоции «тускнеют» или, "
            "наоборот, выходят из-под контроля.\n\n"
            "Тебе нужны конкретные инструменты — и поддержка рядом."
        ),
        "cta": "Программа «Стабилизация» создана именно для тебя. Напиши слово *Стресс* в личку Ирине 👉 https://t.me/irinkaruleva_coach"
    },
    {
        "min": 24, "max": 30,
        "title": "🔴 Выгорание",
        "text": (
            "Ты давно работаешь на износ. Это не слабость — это нервная система, "
            "которая исчерпала ресурс восстановления.\n\n"
            "Инструменты курса помогут начать стабилизацию. Мы также рекомендуем "
            "параллельно обратиться к психологу или психотерапевту, чтобы пройти "
            "этот путь с поддержкой."
        ),
        "cta": "Программа «Стабилизация» — первый шаг к восстановлению. Напиши слово *Стресс* в личку Ирине 👉 https://t.me/irinkaruleva_coach"
    },
]


# ════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS
# ════════════════════════════════════════════════════════════════════════════

def get_sheet():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS не задана")
    creds_dict = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


def save_lead(telegram_id, telegram_username, first_name, email, phone, instagram, score, level):
    try:
        sheet = get_sheet()
        if sheet.row_count == 0 or not sheet.cell(1, 1).value:
            sheet.append_row(["Дата", "Telegram ID", "Telegram", "Имя", "Email", "Телефон", "Instagram", "Баллы", "Уровень"])
        sheet.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            str(telegram_id), telegram_username, first_name, email, phone, instagram, score, level
        ])
        logger.info(f"Лид сохранён: {email}, баллы: {score}")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")


# ════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ════════════════════════════════════════════════════════════════════════════

def get_question_keyboard(question_idx):
    """Кнопки ответов для вопроса."""
    keyboard = []
    for label, score in ANSWERS:
        keyboard.append([InlineKeyboardButton(label, callback_data=f"q_{question_idx}_{score}")])
    return InlineKeyboardMarkup(keyboard)


def get_result(score):
    for r in RESULTS:
        if r["min"] <= score <= r["max"]:
            return r
    return RESULTS[-1]


# ════════════════════════════════════════════════════════════════════════════
# ВОРОНКА: СБОР КОНТАКТОВ
# ════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я помогу тебе пройти экспресс-тест на уровень стресса и выгорания.\n\n"
        "Сначала три коротких документа — формальность, но важная 🙏"
    )
    for filepath in [POLICY_FILE, CONSENT_FILE, NEWSLETTER_FILE]:
        with open(filepath, "rb") as f:
            await update.message.reply_document(document=f)
    keyboard = [[InlineKeyboardButton("✅ Ознакомилась и соглашаюсь", callback_data="consent_yes")]]
    await update.message.reply_text(
        "☝️ Нажимая кнопку, ты подтверждаешь согласие с политикой обработки "
        "персональных данных и получением рассылки от Ирины Рулевой.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONSENT


async def consent_given(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✅ Спасибо!\n\n"
        "Пару быстрых вопросов — меньше минуты ⏱\n\n"
        "📧 На какую почту отправить результаты теста?"
    )
    return EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("Кажется, адрес неверный 😊 Попробуй ещё раз:")
        return EMAIL
    context.user_data["email"] = email
    keyboard = [[KeyboardButton("📱 Поделиться номером", request_contact=True)]]
    await update.message.reply_text(
        "📱 Оставь номер телефона:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.contact.phone_number if update.message.contact else update.message.text.strip()
    context.user_data["phone"] = phone
    await update.message.reply_text(
        "📸 Как тебя найти в Instagram? (напиши username или «нет»)",
        reply_markup=ReplyKeyboardRemove()
    )
    return INSTAGRAM


async def get_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["instagram"] = update.message.text.strip()
    context.user_data["answers"] = []

    await update.message.reply_text(
        "Отлично! 🎯\n\n"
        "Теперь пройдём тест «Где я сейчас?» — 10 утверждений, займёт 2–3 минуты.\n\n"
        "Оцени каждое утверждение честно — результат будет точнее 🧡"
    )
    await send_question(update.message, context, 0)
    return QUIZ


# ════════════════════════════════════════════════════════════════════════════
# ТЕСТ
# ════════════════════════════════════════════════════════════════════════════

async def send_question(message_obj, context, idx):
    text = f"*Вопрос {idx + 1} из {len(QUESTIONS)}*\n\n{QUESTIONS[idx]}"
    await message_obj.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_question_keyboard(idx)
    )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data  # формат: q_<idx>_<score>
    _, idx_str, score_str = data.split("_")
    idx = int(idx_str)
    score = int(score_str)

    answers = context.user_data.get("answers", [])
    answers.append(score)
    context.user_data["answers"] = answers

    # Подтверждаем выбор
    answer_label = ANSWERS[score][0]
    await query.edit_message_text(
        f"*Вопрос {idx + 1} из {len(QUESTIONS)}*\n\n{QUESTIONS[idx]}\n\n✅ _{answer_label}_",
        parse_mode="Markdown"
    )

    next_idx = idx + 1

    if next_idx < len(QUESTIONS):
        await send_question(query.message, context, next_idx)
        return QUIZ
    else:
        await finish_quiz(query, context)
        return ConversationHandler.END


async def finish_quiz(query, context):
    user = query.from_user
    answers = context.user_data.get("answers", [])
    total = sum(answers)
    result = get_result(total)

    # Сохраняем лид
    save_lead(
        telegram_id=user.id,
        telegram_username=f"@{user.username}" if user.username else "—",
        first_name=user.first_name or "—",
        email=context.user_data.get("email", "—"),
        phone=context.user_data.get("phone", "—"),
        instagram=context.user_data.get("instagram", "—"),
        score=total,
        level=result["title"]
    )

    # Уведомление администратору
    if ADMIN_CHAT_ID:
        try:
            await query.message.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "🆕 *Новый лид + тест!*\n\n"
                    f"👤 {user.first_name}\n"
                    f"💬 @{user.username or '—'}\n"
                    f"📧 {context.user_data.get('email')}\n"
                    f"📞 {context.user_data.get('phone')}\n"
                    f"📸 {context.user_data.get('instagram')}\n"
                    f"📊 Баллы: {total} — {result['title']}\n"
                    f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Уведомление не отправлено: {e}")

    # Результат пользователю
    await query.message.reply_text(
        f"✨ *Твой результат: {total} из 30 баллов*\n\n"
        f"*{result['title']}*\n\n"
        f"{result['text']}\n\n"
        "——\n"
        "_Этот тест — не клинический диагноз. Он помогает увидеть общую картину "
        "и понять, где ты сейчас. Если результат тебя встревожил — это не повод "
        "для паники, а повод для первого шага._",
        parse_mode="Markdown"
    )

    # CTA отдельным сообщением
    await query.message.reply_text(
        f"🌿 *Программа «Стабилизация»*\n\n{result['cta']}",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Окей, до встречи! Напиши /start чтобы вернуться 👋",
                                    reply_markup=ReplyKeyboardRemove())
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
            PHONE:     [MessageHandler(filters.CONTACT, get_phone),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            INSTAGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_instagram)],
            QUIZ:      [CallbackQueryHandler(handle_answer, pattern="^q_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    logger.info("✅ Бот nostressbyruleva запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
