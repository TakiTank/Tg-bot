from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, \
    BotCommand, MenuButtonCommands, BotCommandScopeChat, MenuButtonDefault
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
import os
import logging

logger = logging.getLogger(__name__)


# ===============================================
#             ДОПОМІЖНІ ФУНКЦІЇ
# ===============================================

# конвертує об'єкт user в рядок
def dialog_user_info_to_str(user_data: dict) -> str:
    """Конвертує словник даних користувача в читабельний рядок."""
    mapper = {'language_from': 'Мова оригіналу', 'language_to': 'Мова перекладу',
              'text_to_translate': 'Текст для перекладу'}

    result_lines = []
    for key, value in user_data.items():
        # Додаємо лише ті ключі, які є в mapper
        if key in mapper:
            result_lines.append(f"*{mapper[key]}*: {value}")

    # Використовуємо MarkdownV2 для виділення ключа
    return '\n'.join(result_lines)


def _get_chat_id(update: Update) -> int:
    """Отримує chat_id з об'єкта Update, незалежно від типу оновлення."""
    if update.effective_chat:
        return update.effective_chat.id
    if update.callback_query and update.callback_query.message:
        return update.callback_query.message.chat_id
    raise ValueError("Не вдалося визначити Chat ID з об'єкта Update.")


def _get_thread_id(update: Update) -> int | None:
    """Отримує message_thread_id з об'єкта Update."""
    if update.effective_message and update.effective_message.message_thread_id:
        return update.effective_message.message_thread_id
    return None


def _markdown_v2_escape(text: str) -> str:
    """Екранує спеціальні символи MarkdownV2, щоб уникнути помилок синтаксису.
       ЦЕ КРИТИЧНО для безпечного використання ParseMode.MARKDOWN_V2.
    """
    # Символи: _, *, [, ], (, ), ~, `, >, #, +, -, =, |, {, }, ., !
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # Попередження: Неправильне екранування може пошкодити ваші наміри форматування.
    # Найкраще екранувати ВСЕ, а потім вручну застосовувати форматування там, де це потрібно.
    # Для запобігання помилки з непарною кількістю "_" при MARKDOWN,
    # переходимо на MARKDOWN_V2 та використовуємо більш агресивне екранування.

    # Використовуємо replace для найпоширеніших символів, які викликають проблеми
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')

    return text.replace('\\\\', '\\')  # Запобігаємо подвійному екрануванню


# ===============================================
#             ФУНКЦІЇ ВІДПРАВЛЕННЯ
# ===============================================

# надсилає в чат текстове повідомлення
async def send_text(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    text: str, reply_markup: InlineKeyboardMarkup = None,
                    parse_mode: ParseMode = ParseMode.MARKDOWN_V2) -> Message:
    """Надсилає текстове повідомлення з підтримкою MarkdownV2."""

    chat_id = _get_chat_id(update)
    thread_id = _get_thread_id(update)

    # Виправлення: Для безпечного MARKDOWN_V2 (рекомендований Telegram),
    # ми повинні екранувати текст, якщо він не HTML
    if parse_mode == ParseMode.MARKDOWN_V2:
        # Ваш оригінальний код намагався обійти проблему Markdown
        # з непарною кількістю _, але це ненадійний підхід.
        # Агресивне екранування тексту гарантує відсутність помилок.
        text = _markdown_v2_escape(text)

    # Використовуємо .encode/.decode для підтримки широкого діапазону символів (як у вашому оригіналі)
    text = text.encode('utf16', errors='surrogatepass').decode('utf16')

    return await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
        message_thread_id=thread_id
    )


# надсилає в чат html повідомлення
async def send_html(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    text: str) -> Message:
    """Надсилає текстове повідомлення у форматі HTML."""
    return await send_text(update, context, text, parse_mode=ParseMode.HTML)


# надсилає в чат текстове повідомлення, та додає до нього кнопки
async def send_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            text: str, buttons: dict,
                            parse_mode: ParseMode = ParseMode.MARKDOWN_V2) -> Message:
    """Надсилає повідомлення з кнопками InlineKeyboardMarkup."""

    keyboard = []
    for key, value in buttons.items():
        # Важливо: значення кнопок (value) не потрібно екранувати, оскільки воно не проходить парсер
        button = InlineKeyboardButton(str(value), callback_data=str(key))
        keyboard.append([button])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Використовуємо загальну функцію send_text
    return await send_text(update, context, text, reply_markup, parse_mode)


# надсилає в чат фото
async def send_image(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     name: str) -> Message:
    """Надсилає фото з локального файлу."""
    file_path = os.path.join('resources', 'images', f'{name}.jpg')

    if not os.path.exists(file_path):
        logger.error(f"Файл зображення не знайдено: {file_path}")
        return await send_text(update, context,
                               f"😔 Зображення _{name}_ не знайдено.",
                               parse_mode=ParseMode.MARKDOWN)

    with open(file_path, 'rb') as image:
        return await context.bot.send_photo(chat_id=_get_chat_id(update),
                                            photo=image,
                                            message_thread_id=_get_thread_id(update))


# ===============================================
#             КОМАНДИ ТА ФАЙЛИ
# ===============================================

# відображає команду та головне меню
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         commands: dict):
    """Встановлює список команд бота для поточного чату."""
    chat_id = _get_chat_id(update)
    command_list = [BotCommand(key, value) for key, value in commands.items()]

    # Встановлення команд
    await context.bot.set_my_commands(command_list, scope=BotCommandScopeChat(
        chat_id=chat_id))

    # Встановлення кнопки меню (це може бути зайвим, якщо ви встановлюєте команди)
    await context.bot.set_chat_menu_button(menu_button=MenuButtonCommands(),
                                           chat_id=chat_id)


# видаляємо команди для конкретного чату
async def hide_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Видаляє команди бота для поточного чату."""
    chat_id = _get_chat_id(update)
    await context.bot.delete_my_commands(
        scope=BotCommandScopeChat(chat_id=chat_id))
    await context.bot.set_chat_menu_button(menu_button=MenuButtonDefault(),
                                           chat_id=chat_id)


# завантажує повідомлення з папки /resources/messages/
def load_message(name):
    """Завантажує вміст текстового повідомлення з файлу."""
    file_path = os.path.join("resources", "messages", f"{name}.txt")
    try:
        with open(file_path, "r", encoding="utf8") as file:
            return file.read()
    except FileNotFoundError:
        logger.error(f"Файл повідомлення не знайдено: {file_path}")
        return f"Помилка: Повідомлення '{name}' не знайдено."


# завантажує промпт з папки /resources/prompts/
def load_prompt(name):
    """Завантажує вміст промпта (інструкції для AI) з файлу."""
    file_path = os.path.join("resources", "prompts", f"{name}.txt")
    try:
        with open(file_path, "r", encoding="utf8") as file:
            return file.read()
    except FileNotFoundError:
        logger.error(f"Файл промпта не знайдено: {file_path}")
        return f"Помилка: Промпт '{name}' не знайдено."


async def default_callback_handler(update: Update,
                                   context: ContextTypes.DEFAULT_TYPE):
    """Обробник за замовчуванням для необроблених колбеків."""
    await update.callback_query.answer()
    query = update.callback_query.data
    await send_html(update, context,
                    f'Ви натиснули кнопку з колбеком: <code>{query}</code>')


class Dialog:
    pass