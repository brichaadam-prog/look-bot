import os
import random
import sqlite3
from typing import Dict, List, Optional

DB_DIR = os.getenv("DB_DIR", ".")
os.makedirs(DB_DIR, exist_ok=True)
DB_NAME = os.path.join(DB_DIR, "looks.db")


def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")

    return conn


def column_exists(cur, table_name: str, column_name: str) -> bool:
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = cur.fetchall()
    return any(col["name"] == column_name for col in columns)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS looks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT DEFAULT '',
            season TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            note TEXT DEFAULT '',
            is_favorite INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS look_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            look_id INTEGER NOT NULL,
            photo_file_id TEXT NOT NULL,
            position INTEGER DEFAULT 0,
            FOREIGN KEY (look_id) REFERENCES looks(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wishlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            article_or_link TEXT DEFAULT '',
            photo_file_id TEXT DEFAULT '',
            price TEXT DEFAULT '',
            season TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    has_old_photo_column = column_exists(cur, "looks", "photo_file_id")

    if has_old_photo_column:
        cur.execute("""
            SELECT id, photo_file_id
            FROM looks
            WHERE photo_file_id IS NOT NULL AND TRIM(photo_file_id) != ''
        """)
        old_rows = cur.fetchall()

        for row in old_rows:
            look_id = row["id"]
            photo_file_id = row["photo_file_id"]

            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM look_photos
                WHERE look_id = ?
            """, (look_id,))
            exists_count = cur.fetchone()["cnt"]

            if exists_count == 0:
                cur.execute("""
                    INSERT INTO look_photos (look_id, photo_file_id, position)
                    VALUES (?, ?, 0)
                """, (look_id, photo_file_id))

    conn.commit()
    conn.close()


# -------------------------
# LOOKS
# -------------------------

def create_look(
    user_id: int,
    title: str,
    category: str = "",
    season: str = "",
    tags: str = "",
    note: str = "",
) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO looks (
            user_id, title, category, season, tags, note
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, title, category, season, tags, note))

    look_id = cur.lastrowid
    conn.commit()
    conn.close()
    return look_id


def add_look_photo(look_id: int, photo_file_id: str, position: int = 0) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO look_photos (look_id, photo_file_id, position)
        VALUES (?, ?, ?)
    """, (look_id, photo_file_id, position))

    conn.commit()
    conn.close()


def get_look_photos(look_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM look_photos
        WHERE look_id = ?
        ORDER BY position ASC, id ASC
    """, (look_id,))

    rows = cur.fetchall()
    conn.close()
    return rows


def get_look_by_id(look_id: int, user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM looks
        WHERE id = ? AND user_id = ?
    """, (look_id, user_id))

    row = cur.fetchone()
    conn.close()
    return row


def get_user_looks(
    user_id: int,
    favorites_only: bool = False,
    archived_only: bool = False,
) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT *
        FROM looks
        WHERE user_id = ?
    """
    params = [user_id]

    if favorites_only:
        query += " AND is_favorite = 1"

    if archived_only:
        query += " AND is_archived = 1"
    else:
        query += " AND is_archived = 0"

    query += " ORDER BY id DESC"

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def search_looks(
    user_id: int,
    search_text: str = "",
    category: str = "",
    season: str = "",
    favorites_only: bool = False,
    archived_only: bool = False,
) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT *
        FROM looks
        WHERE user_id = ?
    """
    params = [user_id]

    if archived_only:
        query += " AND is_archived = 1"
    else:
        query += " AND is_archived = 0"

    if favorites_only:
        query += " AND is_favorite = 1"

    if category:
        query += " AND category = ?"
        params.append(category)

    if season:
        query += " AND season = ?"
        params.append(season)

    if search_text.strip():
        pattern = f"%{search_text.strip()}%"
        query += """
            AND (
                title LIKE ?
                OR category LIKE ?
                OR season LIKE ?
                OR tags LIKE ?
                OR note LIKE ?
            )
        """
        params.extend([pattern, pattern, pattern, pattern, pattern])

    query += " ORDER BY id DESC"

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_look(look_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM looks
        WHERE id = ? AND user_id = ?
    """, (look_id, user_id))

    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def update_look_title(look_id: int, user_id: int, new_title: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE looks
        SET title = ?
        WHERE id = ? AND user_id = ?
    """, (new_title, look_id, user_id))

    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def update_look_note(look_id: int, user_id: int, new_note: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE looks
        SET note = ?
        WHERE id = ? AND user_id = ?
    """, (new_note, look_id, user_id))

    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def toggle_favorite(look_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE looks
        SET is_favorite = CASE WHEN is_favorite = 1 THEN 0 ELSE 1 END
        WHERE id = ? AND user_id = ?
    """, (look_id, user_id))

    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def toggle_archive(look_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE looks
        SET is_archived = CASE WHEN is_archived = 1 THEN 0 ELSE 1 END
        WHERE id = ? AND user_id = ?
    """, (look_id, user_id))

    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_random_look(user_id: int) -> Optional[sqlite3.Row]:
    looks = get_user_looks(user_id=user_id, favorites_only=False, archived_only=False)
    if not looks:
        return None
    return random.choice(looks)


def get_stats(user_id: int) -> Dict[str, object]:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) AS total
        FROM looks
        WHERE user_id = ? AND is_archived = 0
    """, (user_id,))
    total = cur.fetchone()["total"]

    cur.execute("""
        SELECT COUNT(*) AS total
        FROM looks
        WHERE user_id = ? AND is_favorite = 1 AND is_archived = 0
    """, (user_id,))
    favorites = cur.fetchone()["total"]

    cur.execute("""
        SELECT COUNT(*) AS total
        FROM looks
        WHERE user_id = ? AND is_archived = 1
    """, (user_id,))
    archived = cur.fetchone()["total"]

    cur.execute("""
        SELECT category, COUNT(*) AS cnt
        FROM looks
        WHERE user_id = ? AND is_archived = 0 AND category != ''
        GROUP BY category
        ORDER BY cnt DESC
    """, (user_id,))
    categories = cur.fetchall()

    conn.close()

    return {
        "total": total,
        "favorites": favorites,
        "archived": archived,
        "categories": categories,
    }


# -------------------------
# WISHLIST
# -------------------------

def add_wishlist_item(
    user_id: int,
    title: str,
    article_or_link: str = "",
    photo_file_id: str = "",
    price: str = "",
    season: str = "",
    note: str = "",
) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO wishlist_items (
            user_id, title, article_or_link, photo_file_id, price, season, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, title, article_or_link, photo_file_id, price, season, note))

    item_id = cur.lastrowid
    conn.commit()
    conn.close()
    return item_id


def get_wishlist_items(user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM wishlist_items
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()
    return rows


def get_wishlist_item_by_id(item_id: int, user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM wishlist_items
        WHERE id = ? AND user_id = ?
    """, (item_id, user_id))

    row = cur.fetchone()
    conn.close()
    return row


def delete_wishlist_item(item_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM wishlist_items
        WHERE id = ? AND user_id = ?
    """, (item_id, user_id))

    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted