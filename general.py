import os
import sqlite3
import logging
import nest_asyncio
import telegram
nest_asyncio.apply()

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
import asyncio

# Параметры бота
BOT_TOKEN = "7814500090:AAH8V_ZakvdPi_N7rNRaCHL20gPLGQYgHtI"
ADMIN_ID = 7801573997
BOT_USERNAME = "redpeakbot"  # без @
PUBLICATION_CHANNEL_ID = "@redpeaktj"  # если требуется публикация

# Эмодзи
EMOJI_WAVE = "👋"
EMOJI_ORDER = "🛒"
EMOJI_PHOTO = "📸"
EMOJI_LINK = "🔗"
EMOJI_PRICE = "💰"
EMOJI_OK = "✅"
EMOJI_CANCEL = "❌"
EMOJI_INFO = "ℹ️"
EMOJI_ADMIN = "👑"

# Состояния для оформления заказа клиента
CHOOSING_CATEGORY, RECEIVING_NAME, RECEIVING_PHOTO, RECEIVING_PRODUCT_LINK, RECEIVING_PRICE, CONFIRMING_ORDER = range(6)
# Состояния для создания объявления (админ)
OFFER_RECEIVING_CATEGORY, OFFER_RECEIVING_PHOTO, OFFER_RECEIVING_PRODUCT_LINK, OFFER_RECEIVING_PRICE, OFFER_RECEIVING_DESCRIPTION, OFFER_CONFIRMATION = range(10, 16)
# Состояние для подтверждения заказа по объявлению
OFFER_ORDER_CONFIRM = 20

# Словарь для хранения ожидающих причин отказа (админ)
admin_rejections = {}


keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_main_menu")]]
nazad = InlineKeyboardMarkup(keyboard)

keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="all_orders_all")]]
orderss = InlineKeyboardMarkup(keyboard)

# ----------------- Инициализация БД -----------------
def init_db():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            category TEXT,
            product_name TEXT,
            photo_file_id TEXT,
            product_link TEXT,
            price TEXT,
            status TEXT,
            admin_comment TEXT
        )
    ''')
    cursor.execute("PRAGMA table_info(orders)")
    columns = [info[1] for info in cursor.fetchall()]
    if "product_name" not in columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN product_name TEXT")
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            category TEXT,
            photo_file_id TEXT,
            product_link TEXT,
            price TEXT,
            description TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ----------------- Админ-меню -----------------
async def admin_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Считаем количество заказов со статусом "Новый"
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = ?", ("Новый",))
    new_count = cursor.fetchone()[0]
    conn.close()

    message = f"{EMOJI_ADMIN} *Главное меню администратора*\n\nВыберите действие:"
    keyboard = [
        [InlineKeyboardButton(f"Новые заявки ({new_count})", callback_data="new_orders_menu")],
        [InlineKeyboardButton("Все заявки", callback_data="all_orders_all")],
        [InlineKeyboardButton("Создать объявления", callback_data="create_ad")],
        [InlineKeyboardButton("Поиск заявок", callback_data="search_orders")],
        [InlineKeyboardButton("Удаление заявок", callback_data="delete_orders_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)

# ------------- Новые заявки (только статус "Новый") -------------
async def new_orders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Список", callback_data="new_orders_list"),
         InlineKeyboardButton("Пагинация", callback_data="new_orders_pag_0")],
        [InlineKeyboardButton("Назад", callback_data="admin_main_menu")]
    ]
    text = f"{EMOJI_ADMIN} Выберите режим отображения новых заявок:"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_new_orders_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, username, first_name, category, product_name, product_link, price, status 
        FROM orders WHERE status = ?
    """, ("Новый",))
    orders = cursor.fetchall()
    conn.close()
    if orders:
        text = f"{EMOJI_ORDER} *Список новых заявок:*\n\n"
        for order in orders:
            order_id, user_id, username, first_name, category, product_name, product_link, price, status = order
            text += (
                f"*Заказ #{order_id}:*\n"
                f"Клиент: {first_name} (@{username if username else 'нет username'})\n"
                f"Название: {product_name}\n"
                f"Категория: {category}\n"
                f"{EMOJI_LINK} Ссылка: {product_link}\n"
                f"{EMOJI_PRICE} Цена: {price}\n\n"
            )
    else:
        text = "Нет новых заявок."
    keyboard = [[InlineKeyboardButton("Назад", callback_data="new_orders_menu")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_new_orders_pag(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, username, first_name, category, product_name, photo_file_id, product_link, price, status 
        FROM orders WHERE status = ?
    """, ("Новый",))
    orders = cursor.fetchall()
    conn.close()
    total = len(orders)
    if total == 0:
        text = "Нет новых заявок."
        keyboard = [[InlineKeyboardButton("Назад", callback_data="new_orders_menu")]]
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if page < 0:
        page = 0
    if page >= total:
        page = total - 1
    order = orders[page]
    order_id, user_id, username, first_name, category, product_name, photo_file_id, product_link, price, status = order
    caption = (
        f"{EMOJI_ORDER} *Заказ #{order_id}*\n"
        f"Клиент: {first_name} (@{username if username else 'нет username'})\n"
        f"Название: {product_name}\n"
        f"Категория: {category}\n"
        f"{EMOJI_LINK} Ссылка: {product_link}\n"
        f"{EMOJI_PRICE} Цена: {price}\n"
        f"Страница: {page+1}/{total}"
    )
    buttons = [
        [InlineKeyboardButton("Принять", callback_data=f"accept_{order_id}"),
         InlineKeyboardButton("Отказать", callback_data=f"reject_{order_id}")]
    ]
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"new_orders_pag_{page-1}"))
    if page < total - 1:
        pagination_buttons.append(InlineKeyboardButton("➡️", callback_data=f"new_orders_pag_{page+1}"))
    if pagination_buttons:
        buttons.append(pagination_buttons)
    buttons.append([InlineKeyboardButton("Назад", callback_data="new_orders_menu")])
    reply_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_media(
                media=InputMediaPhoto(media=photo_file_id, caption=caption, parse_mode="Markdown"),
                reply_markup=reply_markup
            )
        except Exception:
            await update.callback_query.edit_message_text(text=caption, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_photo(photo=photo_file_id, caption=caption, parse_mode="Markdown", reply_markup=reply_markup)

async def new_orders_pag_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[-1])
    await show_new_orders_pag(update, context, page)

# ------------- Все заявки (группировка по пользователям) -------------
async def all_orders_all_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id, username, first_name FROM orders")
    users = cursor.fetchall()
    conn.close()
    if not users:
        await query.edit_message_text("Нет заявок.")
        return
    text = f"{EMOJI_ORDER} *Пользователи с заявками:*\n\n"
    keyboard = []
    for user in users:
        user_id, username, first_name = user
        btn_text = f"{first_name} (@{username})" if username else f"{first_name} ({user_id})"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"orders_by_user_{user_id}")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data="admin_main_menu")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

ORDERS_PER_PAGE = 1  # Показываем по 1 заказу на страницу

async def show_orders_by_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Разбираем callback_data
    data_parts = query.data.split("_")
    user_id = data_parts[3]
    page = int(data_parts[4]) if len(data_parts) > 4 else 0

    # Подключаемся к БД
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, category, product_name, product_link, price, status, admin_comment 
        FROM orders WHERE user_id = ?
        ORDER BY id ASC
    """, (user_id,))
    orders = cursor.fetchall()
    conn.close()

    # Если заявок нет
    if not orders:
        await query.edit_message_text("❌ Нет заявок для данного пользователя.")
        return

    total_orders = len(orders)
    total_pages = (total_orders + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE  # Вычисляем кол-во страниц
    page = max(0, min(page, total_pages - 1))  # Ограничиваем номер страницы

    # Получаем один заказ для текущей страницы
    order = orders[page]
    order_id, category, product_name, product_link, price, status, admin_comment = order

    text = (
        f"📌 *Заявка пользователя (ID: {user_id})* | *{page + 1}/{total_pages}*\n\n"
        f"*Заказ #{order_id}:*\n"
        f"Название: {product_name}\n"
        f"Категория: {category}\n"
        f"🔗 Ссылка: {product_link}\n"
        f"💰 Цена: {price}\n"
        f"📌 Статус: {status}\n"
        f"📝 Комментарий: {admin_comment}\n"
    )

    # Кнопки управления заказом
    keyboard = [
        [InlineKeyboardButton(f"🔄 Изменить статус #{order_id}", callback_data=f"change_status_{order_id}")],
        [InlineKeyboardButton("📝 Добавить заметку", callback_data=f"note_order_{order_id}")]
    ]

    # Кнопки пагинации
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"orders_by_user_{user_id}_{page-1}"))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"orders_by_user_{user_id}_{page+1}"))

    if pagination_buttons:
        keyboard.append(pagination_buttons)

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="all_orders_all")])

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def change_status_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = query.data.split("_")[-1]
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    conn.close()
    user_id = row[0] if row else ""
    keyboard = [
        [InlineKeyboardButton("Принятый", callback_data=f"set_status_{order_id}_Принятый"),
         InlineKeyboardButton("Доставка", callback_data=f"set_status_{order_id}_Доставка")],
        [InlineKeyboardButton("Прибыло", callback_data=f"set_status_{order_id}_Прибыло"),
         InlineKeyboardButton("Отказан", callback_data=f"set_status_{order_id}_Отказан")],
        [InlineKeyboardButton("Отмена", callback_data=f"orders_by_user_{user_id}")]
    ]
    text = f"Выберите новый статус для заказа #{order_id}:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def set_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    order_id = parts[2]
    new_status = "_".join(parts[3:])
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    # Получаем user_id для уведомления
    cursor.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()

    

    await query.edit_message_text(f"Статус заказа #{order_id} изменён на '{new_status}'.", reply_markup=nazad)
    if row:
        user_id = row[0]
        await context.bot.send_message(chat_id=user_id, text=f"Статус вашего заказа #{order_id, user_id} изменён на '{new_status}'.")

# ------------- Функции для добавления заметки к заказу -------------
async def note_order_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = query.data.split("_")[-1]
    context.user_data["note_order"] = order_id
    await query.edit_message_text(f"Введите заметку для заказа #{order_id}:")

async def note_order_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.pop("note_order", None)
    if not order_id:
        await update.message.reply_text("Нет заказа для добавления заметки.")
        return
    note = update.message.text
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET admin_comment = ? WHERE id = ?", (note, order_id))
    # Получаем user_id для уведомления
    cursor.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Заметка для заказа #{order_id} сохранена.", reply_markup=orderss)
    if row:
        user_id = row[0]
        await context.bot.send_message(chat_id=user_id, text=f"В ваш заказ #{order_id} добавлена заметка: {note}")

# ------------- Поиск заявок -------------
async def search_orders_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["admin_search"] = True
    await query.edit_message_text("Введите поисковой запрос:")

async def admin_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text
    context.user_data["admin_search"] = False
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, username, first_name, category, product_name, product_link, price, status
        FROM orders
        WHERE product_name LIKE ? OR category LIKE ?
    """, (f"%{query_text}%", f"%{query_text}%"))
    results = cursor.fetchall()
    conn.close()
    if results:
        text = f"{EMOJI_ORDER} *Результаты поиска:*\n\n"
        for order in results:
            order_id, user_id, username, first_name, category, product_name, product_link, price, status = order
            text += (
                f"*Заказ #{order_id}:*\n"
                f"Клиент: {first_name} (@{username if username else 'нет username'})\n"
                f"Название: {product_name}\n"
                f"Категория: {category}\n"
                f"{EMOJI_LINK} Ссылка: {product_link}\n"
                f"{EMOJI_PRICE} Цена: {price}\n\n"
            )
        keyboard = []
        for order in results:
            order_id = order[0]
            btn_status = InlineKeyboardButton(f"Изменить статус #{order_id}", callback_data=f"change_status_{order_id}")
            btn_note = InlineKeyboardButton("Добавить заметку", callback_data=f"note_order_{order_id}")
            keyboard.append([btn_status, btn_note])
        keyboard.append([InlineKeyboardButton("Назад", callback_data="admin_main_menu")])
    else:
        text = "По вашему запросу ничего не найдено."
        keyboard = [[InlineKeyboardButton("Назад", callback_data="admin_main_menu")]]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("admin_search"):
        await admin_search_handler(update, context)
    elif "note_order" in context.user_data:
        await note_order_received(update, context)
    elif update.effective_user.id in admin_rejections:
        await rejection_reason_admin(update, context)

# ------------- История заказов пользователя -------------
async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, category, product_name, product_link, price, status, admin_comment 
        FROM orders WHERE user_id = ?
    """, (user_id,))
    orders = cursor.fetchall()
    conn.close()
    if orders:
        text = f"{EMOJI_ORDER} *Ваша история заказов:*\n\n"
        for order in orders:
            order_id, category, product_name, product_link, price, status, comment = order
            comment_text = f"📝 Заметка: {comment}\n" if comment else ""
            text += (
                f"*👤 Заказ {user_id}{order_id}:*\n"
                f"📌 Название: {product_name}\n"
                f"📂 Категория: {category}\n"
                f"{EMOJI_LINK} Ссылка: {product_link}\n"
                f"{EMOJI_PRICE} Цена: {price}\n"
                f"📦 Статус: {status}\n"
                f"{comment_text}\n"
            )

    else:
        text = "У вас пока нет заказов."
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

# ------------- Оформление заказа клиентом -------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        await admin_main_menu(update, context)
        return

    args = context.args
    if args and args[0].startswith("offer_"):
        offer_id = args[0].split("_", 1)[1]
        conn = sqlite3.connect("orders.db")
        cursor = conn.cursor()
        cursor.execute("SELECT category, photo_file_id, product_link, price, description FROM offers WHERE id = ?", (offer_id,))
        offer = cursor.fetchone()
        conn.close()
        if offer:
            category, photo_file_id, product_link, price, description = offer
            context.user_data['order_data'] = {
                'category': category,
                'photo_file_id': photo_file_id,
                'product_link': product_link,
                'price': price,
                'offer_id': offer_id,
                'is_offer': True
            }
            summary = (
                f"{EMOJI_ORDER} *Подытожим заказ по объявлению:*\n"
                f"• Категория: {category}\n"
                f"• {EMOJI_LINK} Ссылка: {product_link}\n"
                f"• {EMOJI_PRICE} Цена: {price}\n\n"
                "Подтвердите оформление заявки:"
            )
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI_OK} Подтвердить", callback_data="confirm_order_offer"),
                 InlineKeyboardButton(f"{EMOJI_CANCEL} Отмена", callback_data="cancel_order_offer")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Объявление не найдено или устарело.")
        return

    keyboard = [
        [InlineKeyboardButton("📝 Оставить заявку", callback_data="new_order")],
        [InlineKeyboardButton("📋 Мои заказы", callback_data="my_orders")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = f"{EMOJI_WAVE} Привет, {user.first_name}!\n\nВыберите нужное действие:"
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def new_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await order_start(update, context)

async def my_orders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await my_orders(update, context)

async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Электроника ⚡", callback_data="category_Электроника"),
         InlineKeyboardButton("Одежда 👗", callback_data="category_Одежда")],
        [InlineKeyboardButton("Продукты 🍎", callback_data="category_Продукты"),
         InlineKeyboardButton("Другое 🔧", callback_data="category_Другое")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data.pop('order_data', None)
    if update.message:
        await update.message.reply_text("Выберите категорию товара:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("Выберите категорию товара:", reply_markup=reply_markup)
    return CHOOSING_CATEGORY

async def category_chosen_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, category = query.data.split("_", 1)
    if 'order_data' not in context.user_data:
        context.user_data['order_data'] = {}
    context.user_data['order_data']['category'] = category
    await query.edit_message_text(
        text=f"Вы выбрали категорию: *{category}*\n\nВведите название товара:",
        parse_mode="Markdown"
    )
    return RECEIVING_NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if 'order_data' not in context.user_data:
        context.user_data['order_data'] = {}
    context.user_data['order_data']['product_name'] = text
    await update.message.reply_text(
        f"Название товара: *{text}*\n\n{EMOJI_PHOTO} Пришлите, пожалуйста, фото товара.",
        parse_mode="Markdown"
    )
    return RECEIVING_PHOTO

async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        if 'order_data' not in context.user_data:
            context.user_data['order_data'] = {}
        context.user_data['order_data']['photo_file_id'] = file_id
        await update.message.reply_text(f"{EMOJI_LINK} Отлично! Теперь пришлите ссылку на товар.")
        return RECEIVING_PRODUCT_LINK
    await update.message.reply_text("❗ Пожалуйста, отправьте фотографию товара.")
    return RECEIVING_PHOTO

async def product_link_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'order_data' not in context.user_data:
        context.user_data['order_data'] = {}
    context.user_data['order_data']['product_link'] = update.message.text
    await update.message.reply_text(f"{EMOJI_PRICE} Укажите, пожалуйста, цену товара (например, 1999.99):")
    return RECEIVING_PRICE

async def price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'order_data' not in context.user_data:
        context.user_data['order_data'] = {}
    context.user_data['order_data']['price'] = update.message.text
    data = context.user_data['order_data']
    summary = (
        f"{EMOJI_ORDER} *Подытожим ваш заказ:*\n"
        f"Название: {data.get('product_name')}\n"
        f"Категория: {data.get('category')}\n"
        f"• {EMOJI_LINK} Ссылка: {data.get('product_link')}\n"
        f"• {EMOJI_PRICE} Цена: {data.get('price')}\n\n"
        "Подтвердите оформление заявки:"
    )
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_OK} Подтвердить", callback_data="confirm_order"),
         InlineKeyboardButton(f"{EMOJI_CANCEL} Отмена", callback_data="cancel_order")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=reply_markup)
    return CONFIRMING_ORDER

async def confirm_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('order_data')
    if not data:
        await query.edit_message_text("Ошибка: данные заявки не найдены.")
        return ConversationHandler.END

    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (user_id, username, first_name, category, product_name, photo_file_id, product_link, price, status, admin_comment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        update.effective_user.id,
        update.effective_user.username,
        update.effective_user.first_name,
        data.get('category'),
        data.get('product_name'),
        data.get('photo_file_id'),
        data.get('product_link'),
        data.get('price'),
        "Новый",
        ""
    ))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await query.edit_message_text("Ваш заказ отправлен на одобрение администратору.")
    caption = (
        f"{EMOJI_ORDER} *Новый заказ #{order_id}*\n"
        f"👤 Клиент: {update.effective_user.first_name} (@{update.effective_user.username})\n"
        f"Название: {data.get('product_name')}\n"
        f"Категория: {data.get('category')}\n"
        f"• {EMOJI_LINK} Ссылка: {data.get('product_link')}\n"
        f"• {EMOJI_PRICE} Цена: {data.get('price')}"
    )
    keyboard = [
        [InlineKeyboardButton("Принять", callback_data=f"accept_{order_id}"),
         InlineKeyboardButton("Отказать", callback_data=f"reject_{order_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=data.get('photo_file_id'),
        caption=caption,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    context.user_data.pop('order_data', None)
    return ConversationHandler.END

def get_order_title(user, order_id=None):
    """
    Формирует название заказа, используя UID пользователя.
    Если order_id передан, его можно добавить для уточнения.
    """
    title = f"Заказ от пользователя UID: {user.id}"
    if order_id:
        title += f" (ID заказа: {order_id})"
    return title

def get_user_profile_link(user):
    """
    Возвращает ссылку на профиль пользователя.
    Если username отсутствует, используется tg-ссылка.
    """
    if user.username:
        return f"https://t.me/{user.username}"
    else:
        return f"tg://user?id={user.id}"

# 
# Пример использования в функции подтверждения заказа (confirm_order_callback):
async def confirm_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('order_data')
    if not data:
        await query.edit_message_text("Ошибка: данные заявки не найдены.")
        return ConversationHandler.END

    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (user_id, username, first_name, category, product_name, photo_file_id, product_link, price, status, admin_comment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        update.effective_user.id,
        update.effective_user.username,
        update.effective_user.first_name,
        data.get('category'),
        data.get('product_name'),
        data.get('photo_file_id'),
        data.get('product_link'),
        data.get('price'),
        "Новый",
        ""
    ))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Получаем название заказа и ссылку на профиль пользователя
    order_title = get_order_title(update.effective_user, order_id)
    profile_link = get_user_profile_link(update.effective_user)

    await query.edit_message_text("Ваш заказ отправлен на одобрение администратору.")
    caption = (
        f"{EMOJI_ORDER} <b>{order_title}</b>\n"
        f"👤 Клиент: <a href=\"{profile_link}\">{update.effective_user.first_name}</a>\n"
        f"Название: {data.get('product_name')}\n"
        f"Категория: {data.get('category')}\n"
        f"• {EMOJI_LINK} Ссылка: {data.get('product_link')}\n"
        f"• {EMOJI_PRICE} Цена: {data.get('price')}"
    )
    keyboard = [
        [InlineKeyboardButton("Принять", callback_data=f"accept_{order_id}"),
         InlineKeyboardButton("Отказать", callback_data=f"reject_{order_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=data.get('photo_file_id'),
        caption=caption,
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    context.user_data.pop('order_data', None)
    return ConversationHandler.END


# 
# 4

async def cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Заявка отменена.")
    context.user_data.pop('order_data', None)
    await query.edit_message_text("Вы отменили оформление заявки.")
    return ConversationHandler.END

async def confirm_order_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await confirm_order_callback(update, context)

async def cancel_order_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cancel_order_callback(update, context)

# ------------- Создание объявления (админ) -------------
async def offer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("❗ Доступ запрещён.")
        elif update.callback_query:
            await update.callback_query.answer("❗ Доступ запрещён.", show_alert=True)
        return ConversationHandler.END
    keyboard = [
        [InlineKeyboardButton("Электроника ⚡", callback_data="offer_category_Электроника"),
         InlineKeyboardButton("Одежда 👗", callback_data="offer_category_Одежда")],
        [InlineKeyboardButton("Продукты 🍎", callback_data="offer_category_Продукты"),
         InlineKeyboardButton("Другое 🔧", callback_data="offer_category_Другое")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Создание объявления.\nВыберите категорию товара:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("Создание объявления.\nВыберите категорию товара:", reply_markup=reply_markup)
    return OFFER_RECEIVING_CATEGORY

async def offer_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, category = query.data.split("_", 2)
    context.user_data['offer'] = {'category': category}
    await query.edit_message_text(text=f"Категория: *{category}*\n\n{EMOJI_PHOTO} Пришлите фото товара для объявления.", parse_mode="Markdown")
    return OFFER_RECEIVING_PHOTO

async def offer_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data['offer']['photo_file_id'] = file_id
        await update.message.reply_text(f"{EMOJI_ORDER} Отправьте название товара:")
        return OFFER_RECEIVING_PRODUCT_LINK
    await update.message.reply_text("❗ Пожалуйста, отправьте фотографию товара.")
    return OFFER_RECEIVING_PHOTO

async def offer_product_link_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['offer']['product_link'] = update.message.text
    await update.message.reply_text(f"{EMOJI_PRICE} Укажите цену товара (например, 1999.99):")
    return OFFER_RECEIVING_PRICE

async def offer_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['offer']['price'] = update.message.text
    await update.message.reply_text("Опишите товар (например, характеристики, состояние):")
    return OFFER_RECEIVING_DESCRIPTION

async def offer_description_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['offer']['description'] = update.message.text
    data = context.user_data['offer']
    summary = (
        f"{EMOJI_ORDER} *Почти закончили:*\n"
        f"• Категория: {data.get('category')}\n"
        f"• {EMOJI_LINK} Ссылка: {data.get('product_link')}\n"
        f"• {EMOJI_PRICE} Цена: {data.get('price')}\n"
        f"• Описание: {data.get('description')}\n\n"
        "Подтвердите создание объявления:"
    )
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_OK} Подтвердить", callback_data="confirm_offer"),
         InlineKeyboardButton(f"{EMOJI_CANCEL} Отмена", callback_data="cancel_offer")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(summary, reply_markup=reply_markup, parse_mode="Markdown")
    return OFFER_CONFIRMATION

async def offer_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('offer')
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO offers (admin_id, category, photo_file_id, product_link, price, description)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        ADMIN_ID,
        data.get('category'),
        data.get('photo_file_id'),
        data.get('product_link'),
        data.get('price'),
        data.get('description')
    ))
    offer_id = cursor.lastrowid
    conn.commit()
    conn.close()
    offer_link = f"https://t.me/{BOT_USERNAME}?start=offer_{offer_id}"
    await query.edit_message_text(text=f"Объявление создано! {EMOJI_OK}\nСсылка для оформления заявки: {offer_link}")
    context.user_data.pop('offer', None)
    return ConversationHandler.END

async def offer_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Создание объявления отменено.")
    context.user_data.pop('offer', None)
    await query.edit_message_text("Создание объявления отменено.")
    return ConversationHandler.END

# ------------- Решение администратора по заявке -------------
async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # "accept_15" или "reject_15"
    action, order_id = data.split("_", 1)
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    if action == "accept":
        cursor.execute("UPDATE orders SET status = ? WHERE id = ?", ("Принятый", order_id))
        cursor.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        if row:
            user_id = row[0]
            await context.bot.send_message(chat_id=user_id, text="Ваш заказ принят! Ожидайте дальнейших инструкций.")
        await query.answer("Заказ принят!")
    elif action == "reject":
        admin_rejections[update.effective_user.id] = order_id
        if query.message.photo:
            await query.edit_message_caption(caption="Введите причину отказа:", reply_markup=None)
        else:
            await query.edit_message_text(text="Введите причину отказа:")
        return
    await show_new_orders_pag(update, context, page=0)

async def rejection_reason_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id in admin_rejections:
        order_id = admin_rejections.pop(admin_id)
        reason = update.message.text
        conn = sqlite3.connect("orders.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = ?, admin_comment = ? WHERE id = ?", ("Отказан", reason, order_id))
        cursor.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        if row:
            user_id = row[0]
            await context.bot.send_message(chat_id=user_id, text=f"Ваш заказ отклонён. Причина: {reason}")
        await update.message.reply_text("Причина отказа сохранена и отправлена клиенту.")
        await show_new_orders_pag(update, context, page=0)
    else:
        await update.message.reply_text("Нет ожидающего ввода причины отказа.")

# ------------- Пагинация для новых заказов -------------

async def admin_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Считаем количество заказов со статусом "Новый"
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = ?", ("Новый",))
    new_count = cursor.fetchone()[0]
    conn.close()

    message = f"{EMOJI_ADMIN} *Главное меню администратора*\n\nВыберите действие:"
    keyboard = [
        [InlineKeyboardButton(f"Новые заявки ({new_count})", callback_data="new_orders_menu")],
        [InlineKeyboardButton("Все заявки", callback_data="all_orders_all")],
        [InlineKeyboardButton("Создать объявления", callback_data="create_ad")],
        [InlineKeyboardButton("Поиск заявок", callback_data="search_orders")],
        [InlineKeyboardButton("Удаление заявок", callback_data="delete_orders_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        # Удаляем старое сообщение и отправляем новое
        try:
            await update.callback_query.message.delete()
        except telegram.error.BadRequest:
            pass  # Сообщение уже удалено

        await update.callback_query.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)


async def delete_orders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает первый заказ для удаления (режим удаления заказов)."""
    query = update.callback_query
    await query.answer()
    await show_order_delete_pag(update, context, page=0)

async def show_order_delete_pag(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    """Отображает заказ для удаления с пагинацией."""
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, username, first_name, category, product_name, photo_file_id, product_link, price, status, admin_comment 
        FROM orders ORDER BY id
    """)
    orders = cursor.fetchall()
    conn.close()

    total = len(orders)
    if total == 0:
        text = "❌ Нет заявок для удаления."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.message.delete()
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
        return

    page = max(0, min(page, total - 1))
    order = orders[page]
    order_id, user_id, username, first_name, category, product_name, photo_file_id, product_link, price, status, admin_comment = order

    caption = (
        f"🗑️ <b>Удаление заказа #{order_id}</b>\n"
        f"👤 Клиент: {first_name} (@{username if username else 'нет username'})\n"
        f"📌 Название: {product_name}\n"
        f"📂 Категория: {category}\n"
        f"🔗 Ссылка: {product_link}\n"
        f"💰 Цена: {price}\n"
        f"📌 Статус: {status}\n"
        f"📝 Комментарий: {admin_comment}\n"
        f"📄 Страница: {page+1}/{total}"
    )

    buttons = [[InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_order_{order_id}")]]
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"delete_orders_pag_{page-1}"))
    if page < total - 1:
        pagination_buttons.append(InlineKeyboardButton("➡️", callback_data=f"delete_orders_pag_{page+1}"))
    if pagination_buttons:
        buttons.append(pagination_buttons)
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_main_menu")])

    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.callback_query.message.delete()
    if photo_file_id:
        await update.callback_query.message.reply_photo(
            photo=photo_file_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup
        )
    else:
        await update.callback_query.message.reply_text(
            text=caption, parse_mode="HTML", reply_markup=reply_markup
        )

async def delete_orders_pag_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для кнопок пагинации в режиме удаления заказов."""
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[-1])
    await show_order_delete_pag(update, context, page)

async def delete_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет заказ из базы и изменяет сообщение на 'Публикация удалена'."""
    query = update.callback_query
    await query.answer()
    order_id = query.data.split("_")[-1]

    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    text = f"✅ Публикация #{order_id} удалена."
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="delete_orders_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.delete()
    await query.message.reply_text(text=text, reply_markup=reply_markup)

    if row:
        user_id = row[0]
        await context.bot.send_message(chat_id=user_id, text=f"Ваш заказ #{order_id} был удалён администратором.")



# ------------- Основная функция -------------
async def main():
    init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    order_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(new_order_callback, pattern=r"^new_order$"),
                      CommandHandler('order', order_start)],
        states={
            CHOOSING_CATEGORY: [CallbackQueryHandler(category_chosen_callback, pattern=r"^category_")],
            RECEIVING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            RECEIVING_PHOTO: [MessageHandler(filters.PHOTO, photo_received),
                              MessageHandler(filters.ALL & ~filters.COMMAND, photo_received)],
            RECEIVING_PRODUCT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, product_link_received)],
            RECEIVING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, price_received)],
            CONFIRMING_ORDER: [CallbackQueryHandler(confirm_order_callback, pattern="^confirm_order$"),
                               CallbackQueryHandler(cancel_order_callback, pattern="^cancel_order$")]
        },
        fallbacks=[CommandHandler('cancel', cancel_order_callback)]
    )

    offer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: offer_start(u, c), pattern=r"^create_ad$"),
                      CommandHandler('createoffer', offer_start)],
        states={
            OFFER_RECEIVING_CATEGORY: [CallbackQueryHandler(offer_category_callback, pattern=r"^offer_category_")],
            OFFER_RECEIVING_PHOTO: [MessageHandler(filters.PHOTO, offer_photo_received),
                                    MessageHandler(filters.ALL & ~filters.COMMAND, offer_photo_received)],
            OFFER_RECEIVING_PRODUCT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, offer_product_link_received)],
            OFFER_RECEIVING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, offer_price_received)],
            OFFER_RECEIVING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, offer_description_received)],
            OFFER_CONFIRMATION: [CallbackQueryHandler(offer_confirm_callback, pattern="^confirm_offer$"),
                                 CallbackQueryHandler(offer_cancel_callback, pattern="^cancel_offer$")]
        },
        fallbacks=[CommandHandler('cancel', offer_cancel_callback)]
    )

    offer_order_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(confirm_order_offer_callback, pattern="^confirm_order_offer$"),
                      CallbackQueryHandler(cancel_order_offer_callback, pattern="^cancel_order_offer$")],
        states={},
        fallbacks=[]
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(order_conv)
    application.add_handler(offer_conv)
    application.add_handler(offer_order_conv)
    # Обработчики админ-меню и режимов
    application.add_handler(CallbackQueryHandler(admin_main_menu, pattern=r"^admin_main_menu$"))
    application.add_handler(CallbackQueryHandler(new_orders_menu, pattern=r"^new_orders_menu$"))
    application.add_handler(CallbackQueryHandler(show_new_orders_list, pattern=r"^new_orders_list$"))
    application.add_handler(CallbackQueryHandler(new_orders_pag_callback, pattern=r"^new_orders_pag_\d+$"))
    application.add_handler(CallbackQueryHandler(all_orders_all_menu, pattern=r"^all_orders_all$"))
    application.add_handler(CallbackQueryHandler(show_orders_by_user, pattern=r"^orders_by_user_\d+$"))
    application.add_handler(CallbackQueryHandler(change_status_menu, pattern=r"^change_status_\d+$"))
    application.add_handler(CallbackQueryHandler(set_status_callback, pattern=r"^set_status_\d+_.+"))
    application.add_handler(CallbackQueryHandler(admin_decision, pattern=r"^(accept|reject)_"))
    application.add_handler(CallbackQueryHandler(search_orders_prompt, pattern=r"^search_orders$"))
    application.add_handler(CallbackQueryHandler(my_orders_callback, pattern=r"^my_orders$"))
    application.add_handler(CallbackQueryHandler(show_orders_by_user, pattern=r"^orders_by_user_\d+(_\d+)?$"))

    
    # Добавьте следующие строки в main() после регистрации других обработчиков:
    application.add_handler(CallbackQueryHandler(delete_orders_menu, pattern=r"^delete_orders_menu$"))
    application.add_handler(CallbackQueryHandler(delete_orders_pag_callback, pattern=r"^delete_orders_pag_\d+$"))
    application.add_handler(CallbackQueryHandler(delete_order_callback, pattern=r"^delete_order_\d+$"))

    # Обработчик для добавления заметки
    application.add_handler(CallbackQueryHandler(note_order_prompt, pattern=r"^note_order_\d+$"))
    application.add_handler(MessageHandler(filters.Chat(ADMIN_ID) & filters.TEXT & ~filters.COMMAND, admin_text_handler))
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
