import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from config import BOT_TOKEN
from database import (
    add_look_photo,
    add_wishlist_item,
    create_look,
    delete_look,
    delete_wishlist_item,
    get_look_by_id,
    get_look_photos,
    get_random_look,
    get_stats,
    get_user_looks,
    get_wishlist_item_by_id,
    get_wishlist_items,
    init_db,
    search_looks,
    toggle_archive,
    toggle_favorite,
    update_look_note,
    update_look_title,
)

logging.basicConfig(level=logging.INFO)

router = Router()

CATEGORY_OPTIONS = ["casual", "sport", "office", "evening", "date", "other"]
SEASON_OPTIONS = ["Весна", "Лето", "Осень", "Зима", "На все сезоны"]


# -------------------------
# STATES
# -------------------------

class CreateLookState(StatesGroup):
    waiting_for_first_photo = State()
    waiting_for_more_photos = State()
    waiting_for_title = State()
    waiting_for_category = State()
    waiting_for_season = State()
    waiting_for_tags = State()
    waiting_for_note = State()


class SearchState(StatesGroup):
    waiting_for_query = State()


class FilterState(StatesGroup):
    waiting_for_category = State()
    waiting_for_season = State()
    waiting_for_favorites = State()


class EditTitleState(StatesGroup):
    waiting_for_new_title = State()


class EditNoteState(StatesGroup):
    waiting_for_new_note = State()


class WishlistState(StatesGroup):
    waiting_for_photo = State()
    waiting_for_title = State()
    waiting_for_article_or_link = State()
    waiting_for_price = State()
    waiting_for_season = State()
    waiting_for_note = State()


class CompareState(StatesGroup):
    waiting_first_look = State()
    waiting_second_look = State()


# -------------------------
# KEYBOARDS
# -------------------------

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✨ Создать лук"), KeyboardButton(text="🧥 Мои луки")],
        [KeyboardButton(text="🧭 Фильтры"), KeyboardButton(text="⭐ Избранное")],
        [KeyboardButton(text="🔎 Поиск"), KeyboardButton(text="⚖️ Сравнить 2 лука")],
        [KeyboardButton(text="🎲 Случайный лук"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🗂 Архив"), KeyboardButton(text="🛍 Wishlist")],
    ],
    resize_keyboard=True,
)

simple_cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Отмена"), KeyboardButton(text="🏠 Главное меню")],
    ],
    resize_keyboard=True,
)

skip_cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Пропустить")],
        [KeyboardButton(text="Отмена"), KeyboardButton(text="🏠 Главное меню")],
    ],
    resize_keyboard=True,
)

add_more_photos_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить ещё фото")],
        [KeyboardButton(text="Готово")],
        [KeyboardButton(text="Отмена"), KeyboardButton(text="🏠 Главное меню")],
    ],
    resize_keyboard=True,
)

category_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=cat)] for cat in CATEGORY_OPTIONS] + [
        [KeyboardButton(text="Пропустить")],
        [KeyboardButton(text="Отмена"), KeyboardButton(text="🏠 Главное меню")],
    ],
    resize_keyboard=True,
)

season_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=season)] for season in SEASON_OPTIONS] + [
        [KeyboardButton(text="Пропустить")],
        [KeyboardButton(text="Отмена"), KeyboardButton(text="🏠 Главное меню")],
    ],
    resize_keyboard=True,
)

wishlist_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить вещь"), KeyboardButton(text="📋 Мой wishlist")],
        [KeyboardButton(text="🏠 Главное меню")],
    ],
    resize_keyboard=True,
)

filters_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Пропустить")],
        [KeyboardButton(text="Отмена"), KeyboardButton(text="🏠 Главное меню")],
    ],
    resize_keyboard=True,
)


# -------------------------
# HELPERS
# -------------------------

def normalize_optional_text(text: str) -> str:
    text = text.strip()
    if text.lower() == "пропустить":
        return ""
    return text


def text_yes_no_to_bool(text: str) -> bool:
    return text.strip().lower() in ["да", "yes", "y"]


async def show_main_menu(message: Message, text: str = "Главное меню 🏠"):
    await message.answer(text, reply_markup=main_menu)


def get_scope_looks(user_id: int, scope: str):
    if scope == "all":
        return get_user_looks(user_id=user_id, favorites_only=False, archived_only=False)
    if scope == "favorites":
        return get_user_looks(user_id=user_id, favorites_only=True, archived_only=False)
    if scope == "archive":
        return get_user_looks(user_id=user_id, favorites_only=False, archived_only=True)
    return []


def get_cover_photo_file_id(look_id: int) -> str:
    photos = get_look_photos(look_id)
    if not photos:
        return ""
    return photos[0]["photo_file_id"]


def build_caption(look) -> str:
    favorite_mark = "⭐ Избранное\n" if look["is_favorite"] else ""
    category = look["category"] if look["category"] else "—"
    season = look["season"] if look["season"] else "—"
    tags = look["tags"] if look["tags"] else "—"
    note = look["note"] if look["note"] else "—"
    archive_status = "Да" if look["is_archived"] else "Нет"
    photos_count = len(get_look_photos(look["id"]))

    return (
        f"{favorite_mark}"
        f"👗 <b>{look['title']}</b>\n"
        f"🖼 Фото: {photos_count}\n"
        f"🗂 Категория: {category}\n"
        f"🍂 Сезон: {season}\n"
        f"🏷 Теги: {tags}\n"
        f"📝 Заметка: {note}\n"
        f"📦 В архиве: {archive_status}\n"
        f"🕒 Создан: {look['created_at']}"
    )


def build_compare_text(look1, look2) -> str:
    def fmt(look):
        return (
            f"👗 <b>{look['title']}</b>\n"
            f"🗂 Категория: {look['category'] or '—'}\n"
            f"🍂 Сезон: {look['season'] or '—'}\n"
            f"🏷 Теги: {look['tags'] or '—'}\n"
            f"📝 Заметка: {look['note'] or '—'}"
        )

    return (
        "⚖️ <b>Сравнение двух луков</b>\n\n"
        f"<b>Лук 1:</b>\n{fmt(look1)}\n\n"
        f"<b>Лук 2:</b>\n{fmt(look2)}"
    )


def gallery_keyboard(look, scope: str, index: int, total: int) -> InlineKeyboardMarkup:
    favorite_text = "💔 Убрать из избранного" if look["is_favorite"] else "⭐ В избранное"
    archive_text = "📤 Разархивировать" if look["is_archived"] else "🗂 В архив"

    prev_index = max(index - 1, 0)
    next_index = min(index + 1, total - 1)

    buttons = [
        [InlineKeyboardButton(text=favorite_text, callback_data=f"fav|{scope}|{index}|{look['id']}")],
        [
            InlineKeyboardButton(text="✏️ Название", callback_data=f"edit_title|{look['id']}"),
            InlineKeyboardButton(text="📝 Заметка", callback_data=f"edit_note|{look['id']}"),
        ],
        [
            InlineKeyboardButton(text="🖼 Фото", callback_data=f"photos|{look['id']}"),
            InlineKeyboardButton(text="⚖️ Сравнить", callback_data=f"pick_compare_first|{look['id']}"),
        ],
        [
            InlineKeyboardButton(text=archive_text, callback_data=f"archive|{scope}|{index}|{look['id']}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ask_delete|{scope}|{index}|{look['id']}"),
        ],
    ]

    if total > 1:
        buttons.append(
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"show|{scope}|{prev_index}"),
                InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop"),
                InlineKeyboardButton(text="➡️", callback_data=f"show|{scope}|{next_index}"),
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(text="📚 К списку", callback_data=f"list|{scope}"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="menu"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_delete_keyboard(scope: str, index: int, look_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete|{scope}|{index}|{look_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_delete|{scope}|{index}|{look_id}")],
        ]
    )


def search_results_keyboard(looks) -> InlineKeyboardMarkup:
    buttons = []
    for look in looks:
        buttons.append(
            [InlineKeyboardButton(text=f"👗 {look['title']}", callback_data=f"open_by_id|{look['id']}")]
        )
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def compare_pick_keyboard(looks, prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    for look in looks:
        buttons.append(
            [InlineKeyboardButton(text=f"👗 {look['title']}", callback_data=f"{prefix}|{look['id']}")]
        )
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def wishlist_inline_keyboard(items) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        buttons.append(
            [InlineKeyboardButton(text=f"🛍 {item['title']}", callback_data=f"wishlist_open|{item['id']}")]
        )
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def wishlist_item_keyboard(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"wishlist_delete|{item_id}")],
            [InlineKeyboardButton(text="📋 Назад к wishlist", callback_data="wishlist_list")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
        ]
    )


async def render_gallery(message: Message, looks, index: int, scope: str):
    if not looks:
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        await message.answer("Здесь пока нет луков.", reply_markup=main_menu)
        return

    if index < 0:
        index = 0
    if index >= len(looks):
        index = len(looks) - 1

    look = looks[index]
    cover_photo = get_cover_photo_file_id(look["id"])

    if not cover_photo:
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        await message.answer("У этого лука нет фотографий.", reply_markup=main_menu)
        return

    media = InputMediaPhoto(
        media=cover_photo,
        caption=build_caption(look),
        parse_mode="HTML",
    )

    try:
        await message.edit_media(
            media=media,
            reply_markup=gallery_keyboard(look, scope, index, len(looks)),
        )
    except TelegramBadRequest:
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        await message.answer_photo(
            photo=cover_photo,
            caption=build_caption(look),
            reply_markup=gallery_keyboard(look, scope, index, len(looks)),
        )


# -------------------------
# COMMON HANDLERS
# -------------------------

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет ✨\n\n"
        "Я твой стиль-архив.\n"
        "Помогу сохранять образы, добавлять несколько фото в один лук, "
        "вести wishlist вещей, сравнивать луки и быстро искать нужный стиль по фильтрам.",
        reply_markup=main_menu,
    )


@router.message(F.text == "🏠 Главное меню")
@router.message(F.text == "Отмена")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await show_main_menu(message)


# -------------------------
# CREATE LOOK WITH MULTI PHOTOS
# -------------------------

@router.message(F.text == "✨ Создать лук")
async def create_look_handler(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CreateLookState.waiting_for_first_photo)
    await message.answer(
        "Отправь первое фото для нового лука 📸",
        reply_markup=simple_cancel_keyboard,
    )


@router.message(CreateLookState.waiting_for_first_photo, F.photo)
async def first_photo_handler(message: Message, state: FSMContext):
    photo = message.photo[-1].file_id
    await state.update_data(photo_file_ids=[photo])
    await state.set_state(CreateLookState.waiting_for_more_photos)
    await message.answer(
        "Фото добавлено ✅\n\n"
        "Если хочешь, можешь добавить ещё фото этого же лука.",
        reply_markup=add_more_photos_keyboard,
    )


@router.message(CreateLookState.waiting_for_first_photo)
async def first_photo_wrong_handler(message: Message):
    await message.answer("Пожалуйста, отправь именно фото 📸")


@router.message(CreateLookState.waiting_for_more_photos, F.photo)
async def more_photo_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_file_ids = data.get("photo_file_ids", [])
    photo_file_ids.append(message.photo[-1].file_id)
    await state.update_data(photo_file_ids=photo_file_ids)

    await message.answer(
        f"Добавлено фото: {len(photo_file_ids)} ✅\n"
        "Можешь отправить ещё одно фото или нажать «Готово».",
        reply_markup=add_more_photos_keyboard,
    )


@router.message(CreateLookState.waiting_for_more_photos, F.text == "Добавить ещё фото")
async def add_more_prompt_handler(message: Message):
    await message.answer("Отправь ещё одно фото 📸")


@router.message(CreateLookState.waiting_for_more_photos, F.text == "Готово")
async def create_look_done_photos_handler(message: Message, state: FSMContext):
    await state.set_state(CreateLookState.waiting_for_title)
    await message.answer("Напиши название лука ✍️", reply_markup=simple_cancel_keyboard)


@router.message(CreateLookState.waiting_for_more_photos)
async def more_photo_wrong_handler(message: Message):
    await message.answer("Отправь фото или нажми «Готово».")


@router.message(CreateLookState.waiting_for_title, F.text)
async def save_title_handler(message: Message, state: FSMContext):
    title = message.text.strip()

    if len(title) < 2:
        await message.answer("Название слишком короткое. Напиши что-то длиннее.")
        return

    await state.update_data(title=title)
    await state.set_state(CreateLookState.waiting_for_category)
    await message.answer("Выбери категорию или нажми «Пропустить».", reply_markup=category_keyboard)


@router.message(CreateLookState.waiting_for_category, F.text)
async def save_category_handler(message: Message, state: FSMContext):
    category = normalize_optional_text(message.text)
    await state.update_data(category=category)
    await state.set_state(CreateLookState.waiting_for_season)
    await message.answer("Выбери сезон или нажми «Пропустить».", reply_markup=season_keyboard)


@router.message(CreateLookState.waiting_for_season, F.text)
async def save_season_handler(message: Message, state: FSMContext):
    season = normalize_optional_text(message.text)
    await state.update_data(season=season)
    await state.set_state(CreateLookState.waiting_for_tags)
    await message.answer(
        "Напиши теги через запятую.\nПример: black, oversize, autumn\n\nИли нажми «Пропустить».",
        reply_markup=skip_cancel_keyboard,
    )


@router.message(CreateLookState.waiting_for_tags, F.text)
async def save_tags_handler(message: Message, state: FSMContext):
    tags = normalize_optional_text(message.text)
    await state.update_data(tags=tags)
    await state.set_state(CreateLookState.waiting_for_note)
    await message.answer(
        "Добавь заметку к луку или нажми «Пропустить».",
        reply_markup=skip_cancel_keyboard,
    )


@router.message(CreateLookState.waiting_for_note, F.text)
async def save_note_handler(message: Message, state: FSMContext):
    note = normalize_optional_text(message.text)
    data = await state.get_data()

    look_id = create_look(
        user_id=message.from_user.id,
        title=data["title"],
        category=data.get("category", ""),
        season=data.get("season", ""),
        tags=data.get("tags", ""),
        note=note,
    )

    photos = data.get("photo_file_ids", [])
    for idx, photo_file_id in enumerate(photos):
        add_look_photo(look_id, photo_file_id, idx)

    await state.clear()
    await message.answer(
        f"✅ Лук сохранён!\nДобавлено фото: {len(photos)}",
        reply_markup=main_menu,
    )


# -------------------------
# LOOKS / FAVORITES / ARCHIVE
# -------------------------

@router.message(F.text == "🧥 Мои луки")
async def all_looks_handler(message: Message):
    looks = get_scope_looks(message.from_user.id, "all")
    if not looks:
        await message.answer(
            "У тебя пока нет сохранённых луков 👗\nНажми «Создать лук», чтобы добавить первый образ.",
            reply_markup=main_menu,
        )
        return

    look = looks[0]
    cover = get_cover_photo_file_id(look["id"])
    if not cover:
        await message.answer("У этого лука нет фото.", reply_markup=main_menu)
        return

    await message.answer_photo(
        photo=cover,
        caption=build_caption(look),
        reply_markup=gallery_keyboard(look, "all", 0, len(looks)),
    )


@router.message(F.text == "⭐ Избранное")
async def favorites_handler(message: Message):
    looks = get_scope_looks(message.from_user.id, "favorites")
    if not looks:
        await message.answer("У тебя пока нет избранных луков ⭐", reply_markup=main_menu)
        return

    look = looks[0]
    cover = get_cover_photo_file_id(look["id"])
    if not cover:
        await message.answer("У этого лука нет фото.", reply_markup=main_menu)
        return

    await message.answer_photo(
        photo=cover,
        caption=build_caption(look),
        reply_markup=gallery_keyboard(look, "favorites", 0, len(looks)),
    )


@router.message(F.text == "🗂 Архив")
async def archive_handler(message: Message):
    looks = get_scope_looks(message.from_user.id, "archive")
    if not looks:
        await message.answer("Архив пока пуст 📦", reply_markup=main_menu)
        return

    look = looks[0]
    cover = get_cover_photo_file_id(look["id"])
    if not cover:
        await message.answer("У этого лука нет фото.", reply_markup=main_menu)
        return

    await message.answer_photo(
        photo=cover,
        caption=build_caption(look),
        reply_markup=gallery_keyboard(look, "archive", 0, len(looks)),
    )


# -------------------------
# FILTERS
# -------------------------

@router.message(F.text == "🧭 Фильтры")
async def filters_handler(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(FilterState.waiting_for_category)
    await message.answer(
        "Экран фильтров 🧭\n\nВыбери категорию или нажми «Пропустить».",
        reply_markup=category_keyboard,
    )


@router.message(FilterState.waiting_for_category, F.text)
async def filters_category_handler(message: Message, state: FSMContext):
    category = normalize_optional_text(message.text)
    await state.update_data(filter_category=category)
    await state.set_state(FilterState.waiting_for_season)
    await message.answer(
        "Теперь выбери сезон или нажми «Пропустить».",
        reply_markup=season_keyboard,
    )


@router.message(FilterState.waiting_for_season, F.text)
async def filters_season_handler(message: Message, state: FSMContext):
    season = normalize_optional_text(message.text)
    await state.update_data(filter_season=season)
    await state.set_state(FilterState.waiting_for_favorites)
    await message.answer(
        "Показать только избранное?\nНапиши: Да или Нет",
        reply_markup=filters_keyboard,
    )


@router.message(FilterState.waiting_for_favorites, F.text)
async def filters_favorites_handler(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    favorites_only = text in ["да", "yes", "y"]

    data = await state.get_data()
    category = data.get("filter_category", "")
    season = data.get("filter_season", "")

    results = search_looks(
        user_id=message.from_user.id,
        category=category,
        season=season,
        favorites_only=favorites_only,
        archived_only=False,
    )

    await state.clear()

    if not results:
        await message.answer("По этим фильтрам ничего не найдено.", reply_markup=main_menu)
        return

    await message.answer(
        f"Найдено луков: {len(results)}",
        reply_markup=search_results_keyboard(results),
    )


# -------------------------
# SEARCH
# -------------------------

@router.message(F.text == "🔎 Поиск")
async def search_handler(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(SearchState.waiting_for_query)
    await message.answer(
        "Напиши, что искать:\nназвание, категорию, сезон, тег или заметку 🔎",
        reply_markup=simple_cancel_keyboard,
    )


@router.message(SearchState.waiting_for_query, F.text)
async def process_search_handler(message: Message, state: FSMContext):
    query = message.text.strip()

    if len(query) < 2:
        await message.answer("Запрос слишком короткий.")
        return

    results = search_looks(message.from_user.id, search_text=query)
    await state.clear()

    if not results:
        await message.answer("Ничего не найдено.", reply_markup=main_menu)
        return

    await message.answer(
        f"Найдено луков: {len(results)}",
        reply_markup=search_results_keyboard(results),
    )


# -------------------------
# RANDOM / STATS
# -------------------------

@router.message(F.text == "🎲 Случайный лук")
async def random_handler(message: Message):
    look = get_random_look(message.from_user.id)
    if not look:
        await message.answer("У тебя пока нет луков для случайного выбора.", reply_markup=main_menu)
        return

    cover = get_cover_photo_file_id(look["id"])
    if not cover:
        await message.answer("У этого лука нет фото.", reply_markup=main_menu)
        return

    await message.answer_photo(
        photo=cover,
        caption=build_caption(look),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎲 Ещё один", callback_data="random_again")],
                [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
            ]
        ),
    )


@router.message(F.text == "📊 Статистика")
async def stats_handler(message: Message):
    stats = get_stats(message.from_user.id)
    categories = stats["categories"]

    if categories:
        categories_text = "\n".join([f"• {row['category']}: {row['cnt']}" for row in categories])
    else:
        categories_text = "• Пока нет категорий"

    text = (
        "📊 <b>Твоя статистика</b>\n\n"
        f"👗 Активных луков: {stats['total']}\n"
        f"⭐ Избранных: {stats['favorites']}\n"
        f"📦 В архиве: {stats['archived']}\n\n"
        f"<b>Категории:</b>\n{categories_text}"
    )

    await message.answer(text, reply_markup=main_menu)


# -------------------------
# COMPARE
# -------------------------

@router.message(F.text == "⚖️ Сравнить 2 лука")
async def compare_handler(message: Message, state: FSMContext):
    looks = get_user_looks(message.from_user.id, favorites_only=False, archived_only=False)
    if len(looks) < 2:
        await message.answer("Для сравнения нужно минимум 2 лука.", reply_markup=main_menu)
        return

    await state.clear()
    await state.set_state(CompareState.waiting_first_look)
    await message.answer(
        "Выбери первый лук для сравнения ⚖️",
        reply_markup=main_menu,
    )
    await message.answer(
        "Первый лук:",
        reply_markup=compare_pick_keyboard(looks, "compare_first"),
    )


@router.callback_query(F.data.startswith("pick_compare_first|"))
async def pick_compare_first_from_card(callback: CallbackQuery, state: FSMContext):
    _, look_id_str = callback.data.split("|")
    look_id = int(look_id_str)

    looks = get_user_looks(callback.from_user.id, favorites_only=False, archived_only=False)
    if len(looks) < 2:
        await callback.answer("Нужно минимум 2 лука")
        return

    await state.set_state(CompareState.waiting_second_look)
    await state.update_data(compare_first_id=look_id)

    await callback.message.answer(
        "Теперь выбери второй лук:",
        reply_markup=compare_pick_keyboard(looks, "compare_second"),
    )
    await callback.answer("Первый лук выбран")


@router.callback_query(F.data.startswith("compare_first|"))
async def compare_first_callback(callback: CallbackQuery, state: FSMContext):
    _, look_id_str = callback.data.split("|")
    look_id = int(look_id_str)

    looks = get_user_looks(callback.from_user.id, favorites_only=False, archived_only=False)
    await state.set_state(CompareState.waiting_second_look)
    await state.update_data(compare_first_id=look_id)

    await callback.message.answer(
        "Теперь выбери второй лук:",
        reply_markup=compare_pick_keyboard(looks, "compare_second"),
    )
    await callback.answer("Первый лук выбран")


@router.callback_query(F.data.startswith("compare_second|"))
async def compare_second_callback(callback: CallbackQuery, state: FSMContext):
    _, second_id_str = callback.data.split("|")
    second_id = int(second_id_str)

    data = await state.get_data()
    first_id = data.get("compare_first_id")

    if not first_id:
        await state.clear()
        await callback.message.answer("Ошибка сравнения.", reply_markup=main_menu)
        await callback.answer()
        return

    if first_id == second_id:
        await callback.answer("Нужно выбрать другой лук")
        return

    look1 = get_look_by_id(first_id, callback.from_user.id)
    look2 = get_look_by_id(second_id, callback.from_user.id)

    await state.clear()

    if not look1 or not look2:
        await callback.message.answer("Не удалось найти луки для сравнения.", reply_markup=main_menu)
        await callback.answer()
        return

    await callback.message.answer(
        build_compare_text(look1, look2),
        reply_markup=main_menu,
    )
    await callback.answer("Сравнение готово")


# -------------------------
# WISHLIST
# -------------------------

@router.message(F.text == "🛍 Wishlist")
async def wishlist_handler(message: Message):
    await message.answer(
        "Wishlist 🛍\n\nЗдесь можно хранить вещи, которые ты хочешь купить.",
        reply_markup=wishlist_menu,
    )


@router.message(F.text == "➕ Добавить вещь")
async def wishlist_add_start_handler(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(WishlistState.waiting_for_photo)
    await message.answer("Отправь фото вещи 🛍", reply_markup=simple_cancel_keyboard)


@router.message(WishlistState.waiting_for_photo, F.photo)
async def wishlist_photo_handler(message: Message, state: FSMContext):
    photo = message.photo[-1].file_id
    await state.update_data(wishlist_photo_file_id=photo)
    await state.set_state(WishlistState.waiting_for_title)
    await message.answer("Напиши название вещи.", reply_markup=simple_cancel_keyboard)


@router.message(WishlistState.waiting_for_photo)
async def wishlist_wrong_photo_handler(message: Message):
    await message.answer("Пожалуйста, отправь именно фото.")


@router.message(WishlistState.waiting_for_title, F.text)
async def wishlist_title_handler(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 2:
        await message.answer("Название слишком короткое.")
        return

    await state.update_data(wishlist_title=title)
    await state.set_state(WishlistState.waiting_for_article_or_link)
    await message.answer(
        "Пришли артикул или ссылку на товар.\nИли нажми «Пропустить».",
        reply_markup=skip_cancel_keyboard,
    )


@router.message(WishlistState.waiting_for_article_or_link, F.text)
async def wishlist_link_handler(message: Message, state: FSMContext):
    value = normalize_optional_text(message.text)
    await state.update_data(wishlist_article_or_link=value)
    await state.set_state(WishlistState.waiting_for_price)
    await message.answer(
        "Напиши стоимость вещи.\nИли нажми «Пропустить».",
        reply_markup=skip_cancel_keyboard,
    )


@router.message(WishlistState.waiting_for_price, F.text)
async def wishlist_price_handler(message: Message, state: FSMContext):
    price = normalize_optional_text(message.text)
    await state.update_data(wishlist_price=price)
    await state.set_state(WishlistState.waiting_for_season)
    await message.answer(
        "Выбери сезон для вещи.\nИли нажми «Пропустить».",
        reply_markup=season_keyboard,
    )


@router.message(WishlistState.waiting_for_season, F.text)
async def wishlist_season_handler(message: Message, state: FSMContext):
    season = normalize_optional_text(message.text)
    await state.update_data(wishlist_season=season)
    await state.set_state(WishlistState.waiting_for_note)
    await message.answer(
        "Добавь заметку к вещи.\nИли нажми «Пропустить».",
        reply_markup=skip_cancel_keyboard,
    )


@router.message(WishlistState.waiting_for_note, F.text)
async def wishlist_note_handler(message: Message, state: FSMContext):
    note = normalize_optional_text(message.text)
    data = await state.get_data()

    add_wishlist_item(
        user_id=message.from_user.id,
        title=data["wishlist_title"],
        article_or_link=data.get("wishlist_article_or_link", ""),
        photo_file_id=data.get("wishlist_photo_file_id", ""),
        price=data.get("wishlist_price", ""),
        season=data.get("wishlist_season", ""),
        note=note,
    )

    await state.clear()
    await message.answer("✅ Вещь добавлена в wishlist!", reply_markup=wishlist_menu)


@router.message(F.text == "📋 Мой wishlist")
async def wishlist_list_handler(message: Message):
    items = get_wishlist_items(message.from_user.id)

    if not items:
        await message.answer("Wishlist пока пуст 🛍", reply_markup=wishlist_menu)
        return

    await message.answer(
        f"В wishlist вещей: {len(items)}",
        reply_markup=wishlist_inline_keyboard(items),
    )


# -------------------------
# CALLBACKS
# -------------------------

@router.callback_query(F.data == "menu")
async def menu_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer("Главное меню 🏠", reply_markup=main_menu)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "random_again")
async def random_again_callback(callback: CallbackQuery):
    look = get_random_look(callback.from_user.id)
    if not look:
        await callback.answer("Луков пока нет")
        return

    cover = get_cover_photo_file_id(look["id"])
    if not cover:
        await callback.answer("У этого лука нет фото")
        return

    media = InputMediaPhoto(
        media=cover,
        caption=build_caption(look),
        parse_mode="HTML",
    )

    try:
        await callback.message.edit_media(
            media=media,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🎲 Ещё один", callback_data="random_again")],
                    [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
                ]
            ),
        )
    except TelegramBadRequest:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(
            photo=cover,
            caption=build_caption(look),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🎲 Ещё один", callback_data="random_again")],
                    [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
                ]
            ),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("show|"))
async def show_scope_item_callback(callback: CallbackQuery):
    _, scope, index_str = callback.data.split("|")
    index = int(index_str)
    looks = get_scope_looks(callback.from_user.id, scope)
    await render_gallery(callback.message, looks, index, scope)
    await callback.answer()


@router.callback_query(F.data.startswith("list|"))
async def list_scope_callback(callback: CallbackQuery):
    _, scope = callback.data.split("|")
    looks = get_scope_looks(callback.from_user.id, scope)

    if not looks:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer("Здесь пока нет луков.", reply_markup=main_menu)
        await callback.answer()
        return

    buttons = []
    for idx, look in enumerate(looks):
        buttons.append(
            [InlineKeyboardButton(text=f"👗 {look['title']}", callback_data=f"show|{scope}|{idx}")]
        )
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])

    text_map = {
        "all": "🧥 Все луки",
        "favorites": "⭐ Избранное",
        "archive": "🗂 Архив",
    }

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await callback.message.answer(
        text_map.get(scope, "Луки"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("open_by_id|"))
async def open_by_id_callback(callback: CallbackQuery):
    _, look_id_str = callback.data.split("|")
    look_id = int(look_id_str)

    look = get_look_by_id(look_id, callback.from_user.id)
    if not look:
        await callback.answer("Лук не найден")
        return

    cover = get_cover_photo_file_id(look["id"])
    if not cover:
        await callback.answer("У этого лука нет фото")
        return

    await callback.message.answer_photo(
        photo=cover,
        caption=build_caption(look),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fav|"))
async def favorite_callback(callback: CallbackQuery):
    _, scope, index_str, look_id_str = callback.data.split("|")
    index = int(index_str)
    look_id = int(look_id_str)

    toggle_favorite(look_id, callback.from_user.id)

    looks = get_scope_looks(callback.from_user.id, scope)
    await render_gallery(callback.message, looks, index, scope)
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("archive|"))
async def archive_callback(callback: CallbackQuery):
    _, scope, index_str, look_id_str = callback.data.split("|")
    index = int(index_str)
    look_id = int(look_id_str)

    toggle_archive(look_id, callback.from_user.id)

    looks = get_scope_looks(callback.from_user.id, scope)
    await render_gallery(callback.message, looks, index, scope)
    await callback.answer("Обновлено")


@router.callback_query(F.data.startswith("ask_delete|"))
async def ask_delete_callback(callback: CallbackQuery):
    _, scope, index_str, look_id_str = callback.data.split("|")
    look_id = int(look_id_str)

    look = get_look_by_id(look_id, callback.from_user.id)
    if not look:
        await callback.answer("Лук не найден")
        return

    try:
        await callback.message.edit_caption(
            caption=f"⚠️ Ты точно хочешь удалить лук «{look['title']}»?",
            reply_markup=confirm_delete_keyboard(scope, int(index_str), look_id),
        )
    except TelegramBadRequest:
        await callback.message.answer(
            f"⚠️ Ты точно хочешь удалить лук «{look['title']}»?",
            reply_markup=confirm_delete_keyboard(scope, int(index_str), look_id),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("cancel_delete|"))
async def cancel_delete_callback(callback: CallbackQuery):
    _, scope, index_str, _ = callback.data.split("|")
    index = int(index_str)
    looks = get_scope_looks(callback.from_user.id, scope)
    await render_gallery(callback.message, looks, index, scope)
    await callback.answer("Удаление отменено")


@router.callback_query(F.data.startswith("delete|"))
async def delete_callback(callback: CallbackQuery):
    _, scope, index_str, look_id_str = callback.data.split("|")
    index = int(index_str)
    look_id = int(look_id_str)

    delete_look(look_id, callback.from_user.id)

    looks = get_scope_looks(callback.from_user.id, scope)
    await render_gallery(callback.message, looks, index, scope)
    await callback.answer("Лук удалён")


@router.callback_query(F.data.startswith("edit_title|"))
async def edit_title_callback(callback: CallbackQuery, state: FSMContext):
    _, look_id_str = callback.data.split("|")
    look_id = int(look_id_str)

    look = get_look_by_id(look_id, callback.from_user.id)
    if not look:
        await callback.answer("Лук не найден")
        return

    await state.set_state(EditTitleState.waiting_for_new_title)
    await state.update_data(edit_look_id=look_id)

    await callback.message.answer(
        f"Текущее название: <b>{look['title']}</b>\n\nНапиши новое название ✏️",
        reply_markup=simple_cancel_keyboard,
    )
    await callback.answer()


@router.message(EditTitleState.waiting_for_new_title, F.text)
async def save_new_title_handler(message: Message, state: FSMContext):
    new_title = message.text.strip()

    if len(new_title) < 2:
        await message.answer("Название слишком короткое.")
        return

    data = await state.get_data()
    look_id = data.get("edit_look_id")

    if not look_id:
        await state.clear()
        await message.answer("Ошибка редактирования.", reply_markup=main_menu)
        return

    update_look_title(look_id, message.from_user.id, new_title)
    await state.clear()
    await message.answer("✅ Название обновлено!", reply_markup=main_menu)


@router.callback_query(F.data.startswith("edit_note|"))
async def edit_note_callback(callback: CallbackQuery, state: FSMContext):
    _, look_id_str = callback.data.split("|")
    look_id = int(look_id_str)

    look = get_look_by_id(look_id, callback.from_user.id)
    if not look:
        await callback.answer("Лук не найден")
        return

    current_note = look["note"] if look["note"] else "—"

    await state.set_state(EditNoteState.waiting_for_new_note)
    await state.update_data(edit_note_look_id=look_id)

    await callback.message.answer(
        f"Текущая заметка: <b>{current_note}</b>\n\nНапиши новую заметку 📝",
        reply_markup=skip_cancel_keyboard,
    )
    await callback.answer()


@router.message(EditNoteState.waiting_for_new_note, F.text)
async def save_new_note_handler(message: Message, state: FSMContext):
    note = normalize_optional_text(message.text)

    data = await state.get_data()
    look_id = data.get("edit_note_look_id")

    if not look_id:
        await state.clear()
        await message.answer("Ошибка редактирования заметки.", reply_markup=main_menu)
        return

    update_look_note(look_id, message.from_user.id, note)
    await state.clear()
    await message.answer("✅ Заметка обновлена!", reply_markup=main_menu)


@router.callback_query(F.data.startswith("photos|"))
async def photos_callback(callback: CallbackQuery):
    _, look_id_str = callback.data.split("|")
    look_id = int(look_id_str)

    photos = get_look_photos(look_id)
    if not photos:
        await callback.answer("У этого лука нет фото")
        return

    await callback.message.answer(f"🖼 Фото этого лука: {len(photos)}")
    for idx, photo in enumerate(photos, start=1):
        await callback.message.answer_photo(
            photo=photo["photo_file_id"],
            caption=f"Фото {idx}",
        )

    await callback.answer()


# -------------------------
# WISHLIST CALLBACKS
# -------------------------

@router.callback_query(F.data == "wishlist_list")
async def wishlist_list_callback(callback: CallbackQuery):
    items = get_wishlist_items(callback.from_user.id)

    if not items:
        await callback.message.answer("Wishlist пока пуст 🛍", reply_markup=wishlist_menu)
        await callback.answer()
        return

    await callback.message.answer(
        f"В wishlist вещей: {len(items)}",
        reply_markup=wishlist_inline_keyboard(items),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wishlist_open|"))
async def wishlist_open_callback(callback: CallbackQuery):
    _, item_id_str = callback.data.split("|")
    item_id = int(item_id_str)

    item = get_wishlist_item_by_id(item_id, callback.from_user.id)
    if not item:
        await callback.answer("Вещь не найдена")
        return

    text = (
        f"🛍 <b>{item['title']}</b>\n"
        f"🔗 Артикул/ссылка: {item['article_or_link'] or '—'}\n"
        f"💰 Цена: {item['price'] or '—'}\n"
        f"🍂 Сезон: {item['season'] or '—'}\n"
        f"📝 Заметка: {item['note'] or '—'}"
    )

    if item["photo_file_id"]:
        await callback.message.answer_photo(
            photo=item["photo_file_id"],
            caption=text,
            reply_markup=wishlist_item_keyboard(item_id),
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=wishlist_item_keyboard(item_id),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("wishlist_delete|"))
async def wishlist_delete_callback(callback: CallbackQuery):
    _, item_id_str = callback.data.split("|")
    item_id = int(item_id_str)

    deleted = delete_wishlist_item(item_id, callback.from_user.id)
    if deleted:
        await callback.message.answer("🗑 Вещь удалена из wishlist", reply_markup=wishlist_menu)
    else:
        await callback.message.answer("Вещь не найдена", reply_markup=wishlist_menu)

    await callback.answer()


# -------------------------
# MAIN
# -------------------------

async def main():
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())