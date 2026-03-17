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
CHECKLIST_FILE  = os.path.join(DOCS_DIR, "Тест_на_определение_уровня_стресса.pdf")

# ─── Состояния ────────────────────────────────────────────────────────────────
CONSENT, EMAIL, PHONE, INSTAGRAM = range(4)
TEST_Q1, TEST_Q2, TEST_Q3, TEST_Q4, TEST_Q5, TEST_Q6, TEST_Q7, TEST_Q8, TEST_Q9, TEST_Q10 = range(10, 20)

# ─── Вопросы теста ────────────────────────────────────────────────────────────
TEST_QUESTIONS = [
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

ANSWER_BUTTONS = [
    [InlineKeyboardButton("0 — совсем не про меня", callback_data="0")],
    [InlineKeyboardButton("1 — иногда", callback_data="1")],
    [InlineKeyboardButton("2 — часто", callback_data="2")],
    [InlineKeyboardButton("3 — почти всегда", callback_data="3")],
]

# ─── Результаты теста ─────────────────────────────────────────────────────────
def get_result(score: int) -> dict:
    if score <= 7:
        return {
            "level": 1,
            "title": "🟢 Ресурсное состояние",
            "text": (
                "Стресс есть, но ты справляешься. "
                "Хорошее время, чтобы укрепить навыки регуляции — "
                "не когда горит, а когда есть силы учиться."
            ),
            "cta": (
                "💚 Даже в ресурсном состоянии полезно освоить инструменты "
                "саморегуляции — чтобы оставаться устойчивой, когда жизнь подбросит нагрузку.\n\n"
                "Программа «Стабилизация» как раз для этого — 4 недели работы с нервной системой "
                "в поддерживающей среде.\n\n"
                "Напиши слово *Стресс* в личные сообщения @irinkaruleva_coach — узнай подробности."
            )
        }
    elif score <= 15:
        return {
            "level": 2,
            "title": "🟡 Хронический стресс",
            "text": (
                "Нервная система работает в режиме повышенной нагрузки. "
                "Ты ещё функционируешь, но ресурс тает. "
                "Это зона, где инструменты саморегуляции дают максимальный эффект — "
                "ты ловишь процесс до того, как он стал выгоранием."
            ),
            "cta": (
                "🌿 Сейчас — идеальный момент для работы. Ты ещё не на дне, "
                "но уже чувствуешь, что что-то нужно менять.\n\n"
                "Программа «Стабилизация» создана именно для этой точки — "
                "структурированная работа с нервной системой, паттернами мышления "
                "и конкретными инструментами.\n\n"
                "Напиши слово *Стресс* в личные сообщения @irinkaruleva_coach — узнай подробности."
            )
        }
    elif score <= 23:
        return {
            "level": 3,
            "title": "🟠 На пороге выгорания",
            "text": (
                "Тело и психика посылают сигналы, которые уже сложно игнорировать. "
                "Усталость не проходит, мотивация падает, эмоции «тускнеют» или, "
                "наоборот, выходят из-под контроля. "
                "Тебе нужны конкретные инструменты — и, возможно, поддержка специалиста."
            ),
            "cta": (
                "🧡 Твой результат говорит о том, что пора действовать — не завтра, а сейчас.\n\n"
                "Программа «Стабилизация» — это живая терапевтическая работа "
                "с нервной системой под руководством психолога Ирины Рулевой. "
                "Не лекции, не советы «просто отдохни». Реальные инструменты + поддержка.\n\n"
                "Напиши слово *Стресс* в личные сообщения @irinkaruleva_coach — узнай подробности."
            )
        }
    else:
        return {
            "level": 4,
            "title": "🔴 Выгорание",
            "text": (
                "Ты давно работаешь на износ. "
                "Это не слабость — это нервная система, которая исчерпала ресурс восстановления. "
                "Инструменты курса помогут начать стабилизацию, но мы рекомендуем параллельно "
                "обратиться к психологу или психотерапевту, чтобы пройти этот путь с поддержкой."
            ),
            "cta": (
                "❤️ Твой результат требует внимания и заботы — прежде всего твоей собственной.\n\n"
                "Программа «Стабилизация» создана для людей в твоей точке. "
                "Психолог Ирина Рулева проведёт тебя через структурированный путь восстановления "
                "в кругу людей, которые понимают, каково это — устать до самого дна.\n\n"
                "Напиши слово *Стресс* в личные сообщения @irinkaruleva_coach — это первый шаг."
            )
        }


# ─── Google Sheets ────────────────────────────────────────────────────────────
def get_sheet():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS не задана")
    creds_dict = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


def save_lead(telegram_id, telegram_username, first_name, email, phone, instagram, score=None, level=None):
    try:
        sheet = get_sheet()
        if sheet.row_count == 0 or not sheet.cell(1, 1).value:
            sheet.append_row(["Дата", "Telegram ID", "Telegram", "Имя", "Email", "Телефон", "Instagram", "Баллы теста", "Уровень стресса"])
        sheet.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            str(telegram_id), telegram_username, first_name, email, phone, instagram,
            score or "", level or ""
        ])
        logger.info(f"Лид сохранён: {email}")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")


# ════════════════════════════════════════════════════════════════════════════
# ВОРОНКА ЛИД-МАГНИТА (/start)
# ════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Сейчас пришлю тебе PDF с тестом на уровень стресса.\n\n"
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
    await query.edit_message_text("✅ Спасибо!\n\n📧 На какую почту отправить тест?")
    return EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("Кажется, что-то не так с адресом 😊\nПопробуй ещё раз:")
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
        "📸 Как тебя найти в Instagram? (или напиши «нет»)",
        reply_markup=ReplyKeyboardRemove()
    )
    return INSTAGRAM


async def get_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    instagram = update.message.text.strip()
    user = update.effective_user
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
                text=(f"🆕 *Новый лид!*\n\n👤 {user.first_name}\n💬 @{user.username or '—'}\n"
                      f"📧 {context.user_data.get('email')}\n📞 {context.user_data.get('phone')}\n"
                      f"📸 {instagram}\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Уведомление не отправлено: {e}")
    with open(CHECKLIST_FILE, "rb") as f:
        await update.message.reply_document(
            document=f,
            caption=(
                "🎁 Держи тест на уровень стресса!\n\n"
                "А ещё — пройди интерактивный тест прямо здесь в боте: напиши /тест\n"
                "Я посчитаю баллы и расскажу, что они означают именно для тебя 💜\n\n"
                "— Ирина @irina.ruleva.psy"
            )
        )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# ИНТЕРАКТИВНЫЙ ТЕСТ (/тест)
# ════════════════════════════════════════════════════════════════════════════

async def send_question(update_or_query, context, q_index: int):
    text = f"*Вопрос {q_index + 1} из {len(TEST_QUESTIONS)}*\n\n{TEST_QUESTIONS[q_index]}"
    keyboard = InlineKeyboardMarkup(ANSWER_BUTTONS)
    if hasattr(update_or_query, 'message'):
        await update_or_query.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def test_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["test_scores"] = []
    await update.message.reply_text(
        "📊 *Тест «Где я сейчас?»*\n\n"
        "10 коротких вопросов. Оцени каждое утверждение честно — "
        "здесь нет правильных или неправильных ответов.\n\n"
        "Готова? Поехали 👇",
        parse_mode="Markdown"
    )
    await send_question(update, context, 0)
    return TEST_Q1


async def make_answer_handler(q_index: int, next_state):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        scores = context.user_data.get("test_scores", [])
        scores.append(int(query.data))
        context.user_data["test_scores"] = scores

        if q_index + 1 < len(TEST_QUESTIONS):
            await send_question(query, context, q_index + 1)
            return next_state
        else:
            return await show_result(query, context)
    return handler


async def show_result(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    scores = context.user_data.get("test_scores", [])
    total = sum(scores)
    result = get_result(total)
    user = query.from_user

    await query.edit_message_text(
        f"✅ Тест завершён!\n\n"
        f"Твой результат: *{total} из 30 баллов*\n\n"
        f"{result['title']}\n\n"
        f"{result['text']}",
        parse_mode="Markdown"
    )

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=result['cta'],
        parse_mode="Markdown"
    )

    # Сохраняем результат теста
    try:
        sheet = get_sheet()
        sheet.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            str(user.id),
            f"@{user.username}" if user.username else "—",
            user.first_name or "—",
            "—", "—", "—",
            total,
            result['title']
        ])
    except Exception as e:
        logger.error(f"Ошибка сохранения теста: {e}")

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(f"📊 *Тест пройден!*\n\n👤 {user.first_name}\n💬 @{user.username or '—'}\n"
                      f"🎯 {total} баллов — {result['title']}\n"
                      f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Уведомление не отправлено: {e}")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Окей, до встречи! 👋", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ════════════════════════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(TOKEN).build()

    # Воронка лид-магнита
    lead_handler = ConversationHandler(
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

    # Обработчики ответов на вопросы теста
    import asyncio
    answer_handlers = []
    states = [TEST_Q1, TEST_Q2, TEST_Q3, TEST_Q4, TEST_Q5, TEST_Q6, TEST_Q7, TEST_Q8, TEST_Q9, TEST_Q10]
    next_states = states[1:] + [ConversationHandler.END]

    test_states = {}
    for i, (state, next_state) in enumerate(zip(states, next_states)):
        handler_func = None
        # Создаём замыкание для каждого индекса
        def make_handler(idx, ns):
            async def h(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
                query = update.callback_query
                await query.answer()
                sc = context.user_data.get("test_scores", [])
                sc.append(int(query.data))
                context.user_data["test_scores"] = sc
                if idx + 1 < len(TEST_QUESTIONS):
                    await send_question(query, context, idx + 1)
                    return ns
                else:
                    return await show_result(query, context)
            return h
        test_states[state] = [CallbackQueryHandler(make_handler(i, next_state), pattern="^[0-3]$")]

    test_handler = ConversationHandler(
        entry_points=[
            CommandHandler("test", test_start),
            CommandHandler("test", test_start),
        ],
        states=test_states,
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(lead_handler)
    app.add_handler(test_handler)

    logger.info("✅ Бот nostressbyruleva запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
