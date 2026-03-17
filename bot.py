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
TEST_FILE       = os.path.join(DOCS_DIR, "Тест_на_определение_уровня_стресса.pdf")

CONSENT, EMAIL, PHONE, INSTAGRAM, QUIZ = range(5)

QUESTIONS = [
    "Я просыпаюсь уже уставшей — даже если спала достаточно.",
    "Вещи, которые раньше радовали или вдохновляли, теперь не вызывают почти ничего.",
    "Я раздражаюсь на мелочи, которые раньше не цепляли, — или, наоборот, мне всё безразлично.",
    "Я постоянно чувствую, что не успеваю, не дотягиваю или делаю недостаточно.",
    "Мне стало сложнее концентрироваться: забываю, теряю мысль, не могу дочитать текст до конца.",
    "Тело напоминает о себе: головные боли, зажимы в шее и плечах, проблемы со сном или пищеварением.",
    "Я отдаляюсь от людей — меньше хочется общаться, отвечать на сообщения, быть на связи.",
    "У меня есть ощущение, что я работаю на автопилоте — делаю, что нужно, но как будто не присутствую.",
    "Отдых не помогает: выходные или отпуск заканчиваются, а ощущение усталости остаётся.",
    "Я ловлю себя на мысли я больше не могу так — но не понимаю, что именно менять.",
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
        "title": "Ресурсное состояние",
        "emoji": "🟢",
        "text": (
            "Стресс есть — он есть у всех, кто живёт активной жизнью. "
            "Но прямо сейчас ты с ним справляешься. У тебя есть ресурс: "
            "энергия, способность радоваться, концентрация и желание быть в контакте с жизнью и людьми."
        ),
        "cta_personal": (
            "Сейчас — лучшее время, чтобы научиться поддерживать себя "
            "до того, как накопится усталость.\n\n"
            "Строить защиту лучше не тогда, когда горит, а когда есть силы учиться. "
            "Инструменты, освоенные в ресурсном состоянии, работают значительно эффективнее."
        ),
    },
    {
        "min": 8, "max": 15,
        "title": "Хронический стресс",
        "emoji": "🟡",
        "text": (
            "Нервная система работает в режиме повышенной нагрузки. "
            "Ты ещё функционируешь — выполняешь задачи, держишь ритм. "
            "Но это даётся с нарастающим усилием. Ресурс постепенно тает."
        ),
        "cta_personal": (
            "Ты ещё не выгорела — но нервная система уже просит о помощи.\n\n"
            "Сейчас у тебя есть и силы, и возможность действовать. "
            "Ты находишься в точке, где ещё можно поймать процесс до того, как он стал выгоранием. "
            "Хронический стресс не проходит сам — он либо прорабатывается, либо углубляется."
        ),
    },
    {
        "min": 16, "max": 23,
        "title": "На пороге выгорания",
        "emoji": "🟠",
        "text": (
            "Тело и психика посылают сигналы, которые уже сложно игнорировать. "
            "Усталость не проходит после сна. Мотивация падает. "
            "Эмоции тускнеют — или, наоборот, выходят из-под контроля в самые неожиданные моменты."
        ),
        "cta_personal": (
            "Ты дошла до этой точки скорее всего потому, что долго несла слишком много.\n\n"
            "Это не слабость характера. Это физиологическое состояние нервной системы, "
            "которая работает в режиме аварийной экономии ресурсов. "
            "Воля и взять себя в руки здесь не работают — нужны конкретные инструменты.\n\n"
            "Пора позволить себе помощь."
        ),
    },
    {
        "min": 24, "max": 30,
        "title": "Выгорание",
        "emoji": "🔴",
        "text": (
            "Ты давно работаешь на износ. Возможно, ты уже привыкла к этому состоянию настолько, "
            "что оно кажется тебе нормой. Но это не норма — это нервная система, "
            "которая исчерпала ресурс восстановления и работает в режиме выживания."
        ),
        "cta_personal": (
            "Хорошая новость: из выгорания выходят. "
            "Нервная система способна восстанавливаться — при правильной поддержке и в правильном темпе.\n\n"
            "Первый шаг — признать, где ты находишься. И ты уже сделала его, пройдя этот тест.\n\n"
            "Ты заслуживаешь не просто выжить — ты заслуживаешь снова чувствовать себя живой."
        ),
    },
]


def get_result(score):
    for r in RESULTS:
        if r["min"] <= score <= r["max"]:
            return r
    return RESULTS[-1]


def get_question_keyboard(idx):
    buttons = []
    for label, score in ANSWERS:
        buttons.append([InlineKeyboardButton(label, callback_data=f"q_{idx}_{score}")])
    return InlineKeyboardMarkup(buttons)


def get_sheet():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS не задана")
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


def save_lead(telegram_id, telegram_username, first_name, email, phone, instagram, score=None, level=None):
    try:
        sheet = get_sheet()
        if not sheet.cell(1, 1).value:
            sheet.append_row(["Дата", "TG ID", "Telegram", "Имя", "Email", "Телефон", "Instagram", "Баллы", "Уровень"])
        sheet.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            str(telegram_id), telegram_username, first_name,
            email, phone, instagram,
            score or "", level or ""
        ])
        logger.info(f"Лид сохранён: {email}, баллы: {score}")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Сейчас пришлю тест на уровень стресса — и сразу пройдём его вместе прямо здесь.\n\n"
        "Сначала три коротких документа — формальность, но важная 🙏"
    )
    for filepath in [POLICY_FILE, CONSENT_FILE, NEWSLETTER_FILE]:
        with open(filepath, "rb") as f:
            await update.message.reply_document(document=f)
    keyboard = [[InlineKeyboardButton("Ознакомилась и соглашаюсь", callback_data="consent_yes")]]
    await update.message.reply_text(
        "Нажимая кнопку, ты подтверждаешь согласие с политикой обработки "
        "персональных данных и получением рассылки от Ирины Рулевой.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONSENT


async def consent_given(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Отлично! 🧡\n\n"
        "Пару быстрых вопросов — меньше минуты.\n\n"
        "На какую почту отправить тест?"
    )
    return EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("Кажется, адрес неверный 😊 Попробуй ещё раз:")
        return EMAIL
    context.user_data["email"] = email
    keyboard = [[KeyboardButton("Поделиться номером", request_contact=True)]]
    await update.message.reply_text(
        "Оставь номер телефона:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.contact.phone_number if update.message.contact else update.message.text.strip()
    context.user_data["phone"] = phone
    await update.message.reply_text(
        "Как тебя найти в Instagram? (напиши username или нет)",
        reply_markup=ReplyKeyboardRemove()
    )
    return INSTAGRAM


async def get_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["instagram"] = update.message.text.strip()
    context.user_data["answers"] = []

    with open(TEST_FILE, "rb") as f:
        await update.message.reply_document(
            document=f,
            caption=(
                "Держи тест на уровень стресса!\n\n"
                "А ещё — пройди интерактивный тест прямо здесь в боте: напиши /test\n"
                "Я посчитаю баллы и расскажу, что они означают именно для тебя 🧡\n\n"
                "— Ирина @irina.ruleva.psy"
            )
        )

    await update.message.reply_text(
        "Теперь пройдём тест здесь — 10 утверждений, займёт 2-3 минуты.\n\n"
        "Оцени каждое утверждение честно — результат будет точнее 🧡"
    )
    await send_question(update.message, context, 0)
    return QUIZ


async def send_question(message_obj, context, idx):
    text = f"Вопрос {idx + 1} из {len(QUESTIONS)}\n\n{QUESTIONS[idx]}"
    await message_obj.reply_text(
        text,
        reply_markup=get_question_keyboard(idx)
    )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    _, idx_str, score_str = data.split("_")
    idx = int(idx_str)
    score = int(score_str)

    answers = context.user_data.get("answers", [])
    answers.append(score)
    context.user_data["answers"] = answers

    answer_label = ANSWERS[score][0]
    await query.edit_message_text(
        f"Вопрос {idx + 1} из {len(QUESTIONS)}\n\n{QUESTIONS[idx]}\n\nВыбрано: {answer_label}"
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

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"Новый лид + тест!\n\n"
                    f"Имя: {user.first_name}\n"
                    f"Telegram: @{user.username or '—'}\n"
                    f"Email: {context.user_data.get('email')}\n"
                    f"Телефон: {context.user_data.get('phone')}\n"
                    f"Instagram: {context.user_data.get('instagram')}\n"
                    f"Баллы: {total} — {result['emoji']} {result['title']}\n"
                    f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                )
            )
        except Exception as e:
            logger.warning(f"Уведомление не отправлено: {e}")

    # Сообщение 1 — результат и описание зоны
    await query.message.reply_text(
        f"Твой результат: {total} из 30 баллов\n\n"
        f"{result['emoji']} {result['title']}\n\n"
        f"{result['text']}\n\n"
        f"{result['cta_personal']}\n\n"
        f"——\n"
        f"Этот тест — не клинический диагноз. Любой результат — это не приговор. "
        f"Это информация. И с любой точки можно начать движение к лучшему состоянию."
    )

    # Сообщение 2 — описание программы
    await query.message.reply_text(
        "🌿 Программа Стабилизация\n"
        "Терапевтическая группа под руководством психолога Ирины Рулевой\n\n"
        "Это не лекции и не советы просто отдохни. "
        "Это живая, поддерживающая работа с нервной системой и с теми паттернами мышления, "
        "которые поддерживают стресс.\n\n"
        "Что тебя ждёт:\n\n"
        "Неделя 1 — Диагностика и первая помощь\n"
        "Неделя 2 — Работа с незавершёнными стресс-циклами\n"
        "Неделя 3 — Паттерны мышления, поддерживающие стресс\n"
        "Неделя 4 — Ресурс и движение к целям\n\n"
        "Программа ведётся психологом Ириной Рулевой — в формате, который сочетает "
        "доказательные методы работы с нервной системой и тёплую, поддерживающую атмосферу. "
        "Ты будешь в кругу людей, которые понимают, каково это — устать до самого дна."
    )

    # Сообщение 3 — финальный призыв
    await query.message.reply_text(
        "Хроническая усталость, выгорание, ощущение пустоты — всё это не навсегда. "
        "Нервная система умеет восстанавливаться. Тело умеет расслабляться. "
        "Жизнь умеет снова наполняться смыслом и радостью.\n\n"
        "Восстановление начинается не с того момента, когда всё наладится само. "
        "Оно начинается с момента, когда ты решаешь позаботиться о себе.\n\n"
        "4 недели программы — структурированный путь к стабильности\n"
        "1 шаг сейчас — написать слово Стресс в личные сообщения\n"
        "0 обязательств — просто узнай об условиях без давления\n\n"
        "Напиши слово Стресс Ирине: @IrinkaRuleva",
        disable_web_page_preview=True
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Окей, до встречи! Напиши /start чтобы вернуться 👋",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CONSENT:   [CallbackQueryHandler(consent_given, pattern="^consent_yes$")],
            EMAIL:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            PHONE:     [
                MessageHandler(filters.CONTACT, get_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)
            ],
            INSTAGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_instagram)],
            QUIZ:      [CallbackQueryHandler(handle_answer, pattern="^q_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    logger.info("Бот nostressbyruleva запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
