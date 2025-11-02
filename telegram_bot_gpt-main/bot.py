import logging
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, ContextTypes, CommandHandler, MessageHandler, filters
)
import random
import json
from gpt import ChatGptService
from util import (
    load_message, load_prompt, send_text, send_image, show_main_menu,
    default_callback_handler, send_text_buttons
)
from credentials import ChatGPT_TOKEN, BOT_TOKEN
from telegram.error import Conflict, NetworkError

# Налаштування базового логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

chat_gpt = ChatGptService(ChatGPT_TOKEN)

# ===============================================
#             ГЛОБАЛЬНІ КОНСТАНТИ
# ===============================================

# Список команд бота, які будуть відображатися у меню (ДОДАНО /recommend)
BOT_COMMANDS = [
    BotCommand("start", "Почати роботу з ботом"),
    BotCommand("recommend", "Рекомендації фільмів та книг 🍿"),
    BotCommand("random", "Отримати випадкове число"),
    BotCommand("gpt", "Запитати щось у GPT"),
    BotCommand("help", "Показати довідку"),
]

# Доступні мови для перекладу
TRANSLATION_LANGUAGES = {
    'uk': 'Українська 🇺🇦',
    'de': 'Німецька 🇩🇪',
    'en': 'Англійська 🇬🇧',
    'fr': 'Французька 🇫🇷'
}

# Категорії для модуля рекомендацій
RECOMMENDATION_CATEGORIES = {
    'rec_film': 'Фільми 🎬',
    'rec_book': 'Книги 📚',
    'rec_music': 'Музика 🎵'
}


# ===============================================
#             ДОПОМІЖНА ФУНКЦІЯ
# ===============================================

def escape_markdown_v2(text: str) -> str:
    """Допоміжна функція для екранування символів, що використовуються в MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    text = text.replace('\\', '\\\\')
    return ''.join(f'\\{char}' if char in escape_chars and char != '\\' else char for char in text)


# ===============================================
#             ОБРОБНИКИ КОМАНД
# ===============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await show_main_menu(update, context, {
        'start': 'Головне меню',
        'recommend': 'Рекомендації 🍿',  # ДОДАНО
        'random': 'Дізнатися випадковий цікавий факт 🧠',
        'gpt': 'Задати питання чату GPT 🤖',
        'talk': 'Поговорити з відомою особистістю 👤',
        'quiz': 'Взяти участь у квізі ❓',
        'translator': 'Перекладач 🌍'
    })

    text = load_message('main')
    await send_image(update, context, 'main')
    await send_text(update, context, text)

async def random_fact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_image(update, context, 'random')

    message = await send_text(update, context, "🔍 Шукаю цікавий факт для вас...")

    try:
        prompt = load_prompt('random')
        fact = await chat_gpt.send_question(prompt, "Розкажи мені цікавий факт")

        buttons = {
            'random': 'Хочу ще факт 🔄',
            'start': 'Закінчити 🏁'
        }

        if message:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=message.message_id)
        await send_text_buttons(update, context, f"📚 *Випадковий факт:*\n\n{fact}", buttons)

    except Exception as e:
        logger.error(f"Помилка при отриманні випадкового факту: {e}")
        await send_text(update, context, "😔 На жаль, виникла помилка при отриманні факту. Спробуйте ще раз пізніше.")
        if message:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=message.message_id)
            except Exception:
                pass


async def gpt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send_image(update, context, 'gpt')

    prompt = load_prompt('gpt')
    chat_gpt.set_prompt(prompt)

    await send_text(update, context,
                    "🤖 Задайте питання, і я відповім на нього за допомогою ChatGPT.\nПросто надішліть текстове повідомлення.")

    context.user_data['conversation_state'] = 'gpt'


async def talk_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send_image(update, context, 'talk')

    personalities = {
        'talk_cobain': 'Курт Кобейн 🎸',
        'talk_hawking': 'Стівен Гокінг 🔭',
        'talk_nietzsche': 'Фрідріх Ніцше 📚',
        'talk_queen': 'Королева Єлизавета II 👑',
        'talk_tolkien': 'Дж.Р.Р. Толкін 🧙‍♂️',
        'start': 'Закінчити 🏁'
    }
    context.user_data['conversation_state'] = 'talk'

    await send_text_buttons(update, context, "👤 Виберіть особистість, з якою ви хочете поспілкуватися:", personalities)


# ===============================================
#          МОДУЛЬ РЕКОМЕНДАЦІЙ (НОВИЙ)
# ===============================================

async def generate_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерує рекомендацію, використовуючи ChatGPT, та надсилає її користувачеві."""
    user_data = context.user_data
    category_key = user_data.get('rec_category')
    genre = user_data.get('rec_genre')
    disliked_items = user_data.get('rec_disliked_items', [])

    if not category_key or not genre:
        await send_text(update, context, "⚠️ Помилка стану. Повертаю до вибору категорії.")
        await recommendations_handler(update, context)
        return

    category_name_ukr = RECOMMENDATION_CATEGORIES.get(category_key, 'Контент').split(' ')[0]  # Фільми, Книги, Музика

    waiting_message = await send_text(update, context,
                                      f"🤖 *Запускаю AI:* Шукаю рекомендацію {category_name_ukr} у жанрі *{genre}*...")

    system_prompt = (
        "Ти — експерт із рекомендацій культурного контенту. "
        "Твоє завдання — рекомендувати один об'єкт (фільм, книгу або музичний альбом) "
        "на основі наданої категорії та жанру. "
        "Відповідь має бути у форматі JSON з полями: 'title' (назва), 'description' (короткий опис), 'reason' (чому це підходить). "
        "НЕ повертай жодного тексту, окрім коректного JSON-об'єкта. "
    )

    user_query = f"Порекомендуй мені один {category_name_ukr} у жанрі '{genre}'."

    if disliked_items:
        disliked_list = ', '.join(disliked_items)
        user_query += f" Уникай рекомендацій, пов'язаних із цими творами: {disliked_list}."

    json_string = ""
    try:
        chat_gpt.set_prompt(system_prompt)
        json_string = await chat_gpt.send_question(system_prompt, user_query)

        # 1. Парсинг JSON
        json_string = json_string.strip().replace("```json", "").replace("```", "").strip()
        recommendation_data = json.loads(json_string)

        if not all(k in recommendation_data for k in ['title', 'description', 'reason']):
            raise ValueError("Некоректна структура JSON від GPT.")

        # 2. Збереження поточної рекомендації
        user_data['rec_current_suggestion'] = recommendation_data

        # 3. Видалення повідомлення очікування
        if waiting_message:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=waiting_message.message_id)

        # 4. Форматування та надсилання (Використовуємо escape_markdown_v2)
        title = escape_markdown_v2(recommendation_data['title'])
        description = escape_markdown_v2(recommendation_data['description'])
        reason = escape_markdown_v2(recommendation_data['reason'])

        rec_text = (
            f"🍿 *Рекомендація {category_name_ukr}*:\n\n"
            f"✨ \\*\\*{title}\\*\\*\\*\n\n"
            f"📝 {description}\n\n"
            f"💡 \\*Чому це підходить\\: * {reason}"
        )

        buttons = {
            'rec_dislike': 'Не подобається 👎',
            'start': 'Закінчити 🏁'
        }

        # Надсилання рекомендації з кнопками
        await send_text_buttons(update, context, rec_text, buttons)
        user_data['conversation_state'] = 'recommend_active'

    except json.JSONDecodeError as e:
        logger.error(f"Помилка парсингу JSON від GPT: {e}. Рядок: {json_string[:200]}...")
        if waiting_message:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=waiting_message.message_id)
        await send_text(update, context,
                        "😔 На жаль, AI повернув некоректний формат відповіді. Спробуйте ще раз пізніше.")
        user_data.pop('conversation_state', None)
    except Exception as e:
        logger.error(f"Невідома помилка генерації рекомендації: {e}")
        if waiting_message:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=waiting_message.message_id)
        await send_text(update, context, "😔 Виникла помилка при зверненні до ChatGPT. Спробуйте пізніше.")
        user_data.pop('conversation_state', None)


async def recommendations_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /recommend: запитує категорію."""
    context.user_data.clear()
    context.user_data['conversation_state'] = 'recommend_category'
    context.user_data['rec_disliked_items'] = []

    await send_image(update, context, 'recommend')

    keyboard = []
    for key, name in RECOMMENDATION_CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"rec_category|{key}")])

    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_text(update, context,
                    "🍿 *Рекомендації:* Виберіть, що ви шукаєте:",
                    reply_markup)


async def recommendations_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник вибору категорії: запитує жанр."""
    query = update.callback_query
    await query.answer()

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    _, category_key = query.data.split('|')
    category_name = RECOMMENDATION_CATEGORIES.get(category_key, 'Контент')

    context.user_data['rec_category'] = category_key
    context.user_data['conversation_state'] = 'recommend_genre'

    await send_text(update, context,
                    f"✅ Вибрано: *{category_name}*.\n\n"
                    f"➡️ *Введіть жанр*, який вас цікавить (наприклад, 'фантастика', 'класика', 'джаз').")


async def recommendations_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник кнопок 'Не подобається' та 'Закінчити'."""
    query = update.callback_query
    await query.answer()

    data = query.data

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if data == 'start':
        context.user_data.pop('conversation_state', None)
        context.user_data.pop('rec_disliked_items', None)
        context.user_data.pop('rec_current_suggestion', None)
        await start(update, context)
        return

    if data == 'rec_dislike':
        current_suggestion = context.user_data.get('rec_current_suggestion')

        if current_suggestion and 'title' in current_suggestion:
            title = current_suggestion['title']
            disliked_items = context.user_data.get('rec_disliked_items', [])

            if title not in disliked_items:
                disliked_items.append(title)

            context.user_data['rec_disliked_items'] = disliked_items
            context.user_data['rec_current_suggestion'] = None  # Очищаємо поточну рекомендацію

            await send_text(update, context,
                            f"✍️ Добре, *'{escape_markdown_v2(title)}'* додано до списку небажаних. Шукаю нове...")
            await generate_recommendation(update, context)
        else:
            await send_text(update, context,
                            "⚠️ Не вдалося знайти попередню рекомендацію для виключення. Генерую нову.")
            await generate_recommendation(update, context)


# ===============================================
#          ДИНАМІЧНА ЛОГІКА КВІЗУ
# ===============================================

# Допоміжна функція: НАДІСЛАТИ ПИТАННЯ КВІЗУ
async def send_quiz_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    current_question_index = user_data.get('current_quiz_index', 0)

    questions = user_data.get('dynamic_quiz_questions', [])

    if not questions:
        await send_text(update, context, "😔 Помилка: Не вдалося згенерувати питання для квізу. Спробуйте пізніше.")
        await start(update, context)
        return

    if current_question_index >= len(questions):
        await finish_quiz(update, context)
        return

    question_data = questions[current_question_index]

    # Перевірка наявності ключів у згенерованих даних
    if 'question' not in question_data or 'options' not in question_data:
        logger.error(f"Некоректний формат питання від GPT: {question_data}")
        await send_text(update, context, "😔 Помилка: Отримано питання у некоректному форматі. Квіз припинено.")
        await finish_quiz(update, context)
        return

    # Створення клавіатури з варіантами відповідей
    keyboard = []
    for i, option in enumerate(question_data["options"]):
        callback_data = f"quiz_answer_{i}"
        keyboard.append([InlineKeyboardButton(option, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("Закінчити квіз 🏁", callback_data="quiz_finish")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    question_text = f"❓ *Питання {current_question_index + 1} з {len(questions)}:*\n\n{question_data['question']}"

    # Завжди надсилаємо нове повідомлення
    message = await send_text(update, context, question_text, reply_markup=reply_markup)
    user_data['quiz_message_id'] = message.message_id


# ОСНОВНИЙ ОБРОБНИК КОМАНДИ /quiz
async def quiz_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    context.user_data['conversation_state'] = 'quiz'
    context.user_data['score'] = 0
    context.user_data['current_quiz_index'] = 0

    await send_image(update, context, 'quiz')

    # 1. Запит до ChatGPT
    waiting_message = await send_text(update, context,
                                      "🤖 *Запускаю AI:* Генерую унікальний квіз на 3 питання у сфері загальних знань...")

    # Ініціалізація json_string на випадок помилки
    json_string = ""
    quiz_prompt = load_prompt('quiz_generator')

    try:
        json_string = await chat_gpt.send_question(quiz_prompt, "Згенеруй мені квіз")

        json_string = json_string.strip().replace("```json", "").replace("```", "").strip()

        dynamic_questions = json.loads(json_string)
        context.user_data['dynamic_quiz_questions'] = dynamic_questions

        if waiting_message:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=waiting_message.message_id)

        await send_text(update, context, "🎉 *Квіз готовий!* Починаємо.")

    except json.JSONDecodeError as e:
        logger.error(f"Помилка парсингу JSON від GPT: {e}. Рядок: {json_string[:200]}...")
        if waiting_message:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=waiting_message.message_id)
        await send_text(update, context,
                        "😔 На жаль, ChatGPT повернув некоректний формат квізу. Спробуйте ще раз пізніше.")
        context.user_data.clear()
        return
    except Exception as e:
        logger.error(f"Невідома помилка генерації квізу: {e}")
        if waiting_message:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=waiting_message.message_id)
        await send_text(update, context, "😔 Виникла помилка при зверненні до ChatGPT. Спробуйте пізніше.")
        context.user_data.clear()
        return

    await send_quiz_question(update, context)


# ФУНКЦІЯ ЗАВЕРШЕННЯ КВІЗУ
async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    score = context.user_data.get('score', 0)
    total = len(context.user_data.get('dynamic_quiz_questions', []))

    context.user_data.pop('conversation_state', None)
    context.user_data.pop('score', None)
    context.user_data.pop('current_quiz_index', None)
    context.user_data.pop('dynamic_quiz_questions', None)

    quiz_message_id = context.user_data.pop('quiz_message_id', None)
    if quiz_message_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=quiz_message_id)
        except Exception:
            pass

    result_text = f"🎉 \\*Квіз завершено\\!\\* 🎉\n\nВаш результат: \\*\\*{score} з {total}\\*\\*\\."

    if score == total:
        result_text += "\n\n🤩 Фантастично\\! Ви справжній ерудит\\!"
    elif score >= total / 2:
        result_text += "\n\n👍 Добре\\! Продовжуйте в тому ж дусі\\."
    else:
        result_text += "\n\n🧐 Є над чим попрацювати\\. Спробуйте ще раз\\!"

    buttons = {
        'quiz_restart': 'Спробувати ще раз 🔄',
        'start': 'Головне меню 🏠'
    }

    await send_text_buttons(update, context, result_text, buttons)

# Обробник колбеків для квізу
async def quiz_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_data = context.user_data
    current_index = user_data.get('current_quiz_index', 0)
    questions = user_data.get('dynamic_quiz_questions', [])

    if data == 'quiz_finish':
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await finish_quiz(update, context)
        return

    if data.startswith('quiz_answer_'):
        try:
            answer_index = int(data.replace('quiz_answer_', ''))
        except ValueError:
            logger.error(f"Некоректний індекс відповіді: {data}")
            return

        if current_index >= len(questions):
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        question_data = questions[current_index]
        correct_answer = question_data.get("correct_answer")
        options = question_data.get("options")

        if not correct_answer or not options or answer_index >= len(options):
            logger.error(f"Не вдалося знайти коректну відповідь або опцію. Q:{question_data}, Index:{answer_index}")
            await query.edit_message_text(
                escape_markdown_v2("Помилка: Не вдалося визначити правильну відповідь або опції. Квіз припинено."),
                parse_mode='MarkdownV2')
            await finish_quiz(update, context)
            return

        user_answer = options[answer_index]

        # Виділення клавіатури після відповіді
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        user_answer_esc = escape_markdown_v2(str(user_answer))
        correct_answer_esc = escape_markdown_v2(str(correct_answer))

        if user_answer == correct_answer:
            feedback = "✅ \\*Правильно\\!\\*"
            user_data['score'] += 1
        else:
            feedback = f"❌ \\*Неправильно\\.\\* Правильна відповідь: \\*\\*{correct_answer_esc}\\*\\*\\."

        original_text = query.message.text

        question_parts = original_text.split('\n\n')
        question_header_body = "\n\n".join(question_parts[:2])

        final_text = (
            f"{escape_markdown_v2(question_header_body)}\n\n"
            f"Ваша відповідь: \\*\\*{user_answer_esc}\\*\\*\n"
            f"{feedback}"
        )

        await query.edit_message_text(final_text, parse_mode='MarkdownV2')

        user_data['current_quiz_index'] = current_index + 1
        user_data.pop('quiz_message_id', None)

        await send_quiz_question(update, context)

async def post_quiz_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if data == 'quiz_restart':
        await quiz_handler(update, context)
    elif data == 'start':
        await start(update, context)


# ===============================================
#          ЛОГІКА ПЕРЕКЛАДАЧА
# ===============================================

async def translator_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query or update.message and update.message.text == '/translator':
        context.user_data.clear()
        context.user_data['conversation_state'] = 'translate'
        context.user_data['language_from'] = None
        context.user_data['language_to'] = None

    await send_text(update, context, "🌍 *Режим Перекладача.*")
    await translator_send_language_selection(update, context, 'language_from')


async def translator_send_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, step: str):
    """Надсилає кнопки для вибору мови ('language_from' або 'language_to')."""

    current_from = context.user_data.get('language_from')

    if step == 'language_from':
        text = "1️⃣ *Виберіть мову оригіналу:*"
    else:
        text = "2️⃣ *Виберіть мову, на яку потрібно перекласти:*"

    keyboard = []
    for code, name in TRANSLATION_LANGUAGES.items():
        if step == 'language_to' and code == current_from:
            continue

        callback_data = f"translate_select|{step}|{code}"
        keyboard.append([InlineKeyboardButton(name, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_text(update, context, text, reply_markup)


async def translator_select_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    _, step, code = query.data.split('|')
    language_name = TRANSLATION_LANGUAGES.get(code)

    user_data = context.user_data

    if step == 'language_from':
        user_data['language_from'] = code
        user_data['language_from_name'] = language_name

        await send_text(update, context, f"✅ *Мова оригіналу:* {language_name}")
        await translator_send_language_selection(update, context, 'language_to')

    elif step == 'language_to':
        user_data['language_to'] = code
        user_data['language_to_name'] = language_name

        await send_text(update, context, f"✅ *Мова перекладу:* {language_name}")

        await send_text(update, context,
                        f"🎉 *Налаштування завершено.* "
                        f"Перекладаємо з *{user_data['language_from_name']}* на *{user_data['language_to_name']}*.\n\n"
                        f"➡️ *Надішліть текст, який потрібно перекласти.*")

    context.user_data['conversation_state'] = 'translate'


# ===============================================
#          ОБРОБНИК ПРОДОВЖЕННЯ РОЗМОВИ
# ===============================================

async def gpt_continue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    state = context.user_data.get('conversation_state')

    if state == 'gpt':
        await send_text(update, context, "🤖 *Режим ChatGPT активний.* Надішліть ваше наступне питання.")
    elif state == 'talk':
        personality_key = context.user_data.get('selected_personality', 'Особистість')
        personality_name = personality_key.replace('talk_', '').replace('_', ' ').title()
        await send_text(update, context, f"👤 *Розмова з {personality_name} активна.* Продовжуйте спілкування.")
    else:
        await start(update, context)


# ===============================================
#            ОБРОБНИКИ КОЛБЕКІВ ТА ПОВІДОМЛЕНЬ
# ===============================================

async def random_fact_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if data == 'random':
        await random_fact(update, context)
    elif data == 'start':
        await start(update, context)


async def talk_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if data == 'start':
        context.user_data.pop('conversation_state', None)
        context.user_data.pop('selected_personality', None)
        await start(update, context)
        return

    if data.startswith('talk_'):
        context.user_data.clear()
        context.user_data['selected_personality'] = data
        context.user_data['conversation_state'] = 'talk'

        prompt = load_prompt(data)
        chat_gpt.set_prompt(prompt)

        personality_name = data.replace('talk_', '').replace('_', ' ').title()

        await send_image(update, context, data)

        buttons = {'gpt_continue': 'Почати розмову 💬', 'start': 'Закінчити 🏁'}
        await send_text_buttons(update, context,
                                f"👤 Ви почали розмову з *{personality_name}*. Надішліть повідомлення, щоб отримати відповідь.",
                                buttons)


async def show_funny_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    funny_responses = [
        "🤔 Хмм... Цікаво, але я не зрозумів, що саме ви хочете. Може спробуєте одну з команд з меню?",
        "🧐 Дуже цікаве повідомлення! Але мені потрібні чіткіші інструкції. Ось доступні команди:",
        "😅 Ой, здається, ви мене застали зненацька! Я вмію багато чого, але мені потрібна конкретна команда:",
    ]
    hints = [
        "Спробуйте команду /gpt, щоб задати питання",
        "Використайте /random для отримання цікавого факту",
        "Команда /talk дозволить вам поспілкуватися з відомою особистістю",
        "Команда /translator відкриє перекладач",
        "Команда /recommend дозволить отримати рекомендації контенту 🍿"  # ДОДАНО
    ]
    response = f"{random.choice(funny_responses)}\n\n💡 *Підказка:* {random.choice(hints)}"
    await send_text(update, context, response)

async def interpret_random_input(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    message_text_lower = message_text.lower()

    if any(keyword in message_text_lower for keyword in ['факт', 'цікав', 'random', 'випадков']):
        await send_text(update, context, "🧠 Схоже, ви цікавитесь випадковими фактами! Зараз покажу вам один...")
        await random_fact(update, context)
        return True

    elif any(keyword in message_text_lower for keyword in ['рекоменд', 'фільм', 'книга', 'музик', 'recommend']):
        await send_text(update, context, "🍿 Схоже, вам потрібна рекомендація! Переходимо до вибору категорії...")
        await recommendations_handler(update, context)
        return True

    elif any(keyword in message_text_lower for keyword in ['gpt', 'чат', 'питання', 'запита', 'дізнатися']):
        await send_text(update, context, "🤖 Схоже, у вас є питання! Переходимо до режиму спілкування з ChatGPT...")
        await gpt_handler(update, context)
        return True

    elif any(keyword in message_text_lower for keyword in ['розмов', 'говори', 'спілкува', 'особист', 'talk']):
        await send_text(update, context,
                        "👤 Схоже, ви хочете поговорити з відомою особистістю! Зараз покажу вам доступні варіанти...")
        await talk_handler(update, context)
        return True

    elif any(keyword in message_text_lower for keyword in ['квіз', 'вікторин', 'quiz', 'питання']):
        await send_text(update, context, "❓ Схоже, ви хочете взяти участь у квізі! Починаємо...")
        await quiz_handler(update, context)
        return True

    elif any(keyword in message_text_lower for keyword in ['переклад', 'translate', 'мова']):
        await send_text(update, context, "🌍 Схоже, ви хочете щось перекласти! Запускаю перекладач...")
        await translator_handler(update, context)
        return True

    return False


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    conversation_state = context.user_data.get('conversation_state')

    if conversation_state == 'recommend_genre':
        context.user_data['rec_genre'] = message_text
        context.user_data.pop('conversation_state', None)
        await generate_recommendation(update, context)
        return

    if not conversation_state:
        intent_recognized = await interpret_random_input(update, context, message_text)
        if not intent_recognized:
            await show_funny_response(update, context)
        return

    if conversation_state == 'gpt' or conversation_state == 'talk':
        waiting_message = await send_text(update, context, "🔍 Обробляю ваше повідомлення...")
        try:
            response = await chat_gpt.add_message(message_text)

            if waiting_message:
                await context.bot.delete_message(chat_id=update.effective_chat.id,
                                                 message_id=waiting_message.message_id)

            if conversation_state == 'gpt':
                buttons = {'gpt_continue': 'Задати питання ще 🔄', 'start': 'Закінчити 🏁'}
                await send_text_buttons(update, context, f"🤖 *Відповідь ChatGPT:*\n\n{response}", buttons)

            elif conversation_state == 'talk':
                personality = context.user_data.get('selected_personality', 'Особистість')
                personality_name = personality.replace('talk_', '').replace('_', ' ').title()
                buttons = {'gpt_continue': 'Продовжити розмову 🔄', 'start': 'Закінчити 🏁'}
                await send_text_buttons(update, context, f"👤 *{personality_name}:*\n\n{response}", buttons)

        except Exception as e:
            logger.error(f"Помилка при отриманні відповіді від ChatGPT: {e}")
            await send_text(update, context,
                            "😔 На жаль, виникла помилка при отриманні відповіді. Спробуйте ще раз пізніше.")
            if waiting_message:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id,
                                                     message_id=waiting_message.message_id)
                except Exception:
                    pass


    # Логіка перекладу
    elif conversation_state == 'translate':
        lang_from_name = context.user_data.get('language_from_name')
        lang_to_name = context.user_data.get('language_to_name')

        if not lang_from_name or not lang_to_name:
            await send_text(update, context,
                            "⚠️ Спочатку потрібно вибрати мови перекладу.")
            await translator_send_language_selection(update, context, 'language_from')
            return

        waiting_message = await send_text(update, context,
                                          f"🌍 Перекладаю з *{lang_from_name}* на *{lang_to_name}*...")

        try:
            translation_prompt = load_prompt('translator')

            chat_gpt.set_prompt(translation_prompt)

            question = (f"Переклади наступний текст з {lang_from_name} на {lang_to_name}. "
                        f"Не додавай нічого зайвого, лише переклад: {message_text}")

            translation = await chat_gpt.send_question(translation_prompt, question)

            if waiting_message:
                await context.bot.delete_message(chat_id=update.effective_chat.id,
                                                 message_id=waiting_message.message_id)

            buttons = {'translator': 'Перекласти ще 🔄', 'start': 'Закінчити 🏁'}
            await send_text_buttons(update, context,
                                    f"✅ *Переклад на {lang_to_name}:*\n\n{translation}",
                                    buttons)

        except Exception as e:
            logger.error(f"Помилка при перекладі: {e}")
            if waiting_message:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id,
                                                     message_id=waiting_message.message_id)
                except Exception:
                    pass
            await send_text(update, context,
                            "😔 На жаль, виникла помилка при перекладі. Спробуйте ще раз пізніше.")


async def error_handler(update, context):
    if update:
        chat_id = update.effective_chat.id
        await context.bot.send_message(chat_id=chat_id, text=escape_markdown_v2(
            "❌ Ой! Виникла критична помилка. Будь ласка, спробуйте ще раз або перезапустіть бота командою /start."),
                                       parse_mode='MarkdownV2')

    logger.error(f"Помилка під час обробки оновлення: {context.error}")
    if isinstance(context.error, Conflict):
        logger.error("Конфлікт: інший екземпляр цього бота вже запущено.")
    elif isinstance(context.error, NetworkError):
        logger.error(f"Помилка мережі: {context.error}")


# =========================================
#          РЕЄСТРАЦІЯ ОБРОБНИКІВ
# =========================================

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler('start', start))
app.add_handler(CommandHandler('recommend', recommendations_handler))
app.add_handler(CommandHandler('random', random_fact))
app.add_handler(CommandHandler('gpt', gpt_handler))
app.add_handler(CommandHandler('talk', talk_handler))
app.add_handler(CommandHandler('quiz', quiz_handler))
app.add_handler(CommandHandler('translator', translator_handler))

app.add_handler(CallbackQueryHandler(recommendations_category_callback, pattern=r'^rec_category\|'))
app.add_handler(CallbackQueryHandler(recommendations_feedback_callback, pattern='^(rec_dislike|start)$'))

app.add_handler(CallbackQueryHandler(gpt_continue_handler, pattern='^gpt_continue$'))
app.add_handler(CallbackQueryHandler(random_fact_button_handler, pattern='^(random|start)$'))
app.add_handler(CallbackQueryHandler(post_quiz_buttons_handler, pattern='^(quiz_restart|start)$'))
app.add_handler(CallbackQueryHandler(translator_select_language, pattern=r'^translate_select\|'))
app.add_handler(
    CallbackQueryHandler(translator_handler, pattern='^translator$'))

app.add_handler(CallbackQueryHandler(quiz_callback_handler, pattern='^quiz_'))
app.add_handler(CallbackQueryHandler(talk_button_handler,
                                     pattern='^(talk_cobain|talk_hawking|talk_nietzsche|talk_queen|talk_tolkien|start)$'))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
app.add_handler(CallbackQueryHandler(default_callback_handler))

app.add_error_handler(error_handler)

# Запуск бота
if __name__ == '__main__':
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
