--- glavobsnab_system/database.py (原始)


+++ glavobsnab_system/database.py (修改后)
"""
database.py - Модуль работы с базой данных SQLite
Хранение истории закупок, поставщиков, клиентов и цен
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Any
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "glavobsnab.db")


def get_connection():
    """Получить соединение с БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Инициализация таблиц базы данных"""
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица клиентов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Таблица поставщиков
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            coordinates_lat REAL,
            coordinates_lon REAL,
            free_delivery BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, address)
        )
    """)

    # Таблица документов (заявки и счета)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type TEXT NOT NULL,  -- 'request' или 'invoice'
            client_id INTEGER,
            supplier_id INTEGER,
            filename TEXT,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivery_address TEXT,
            total_amount REAL,
            FOREIGN KEY (client_id) REFERENCES clients(id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    # Таблица позиций номенклатуры
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            quantity REAL,
            unit TEXT,
            price_per_unit REAL,
            total_price REAL,
            article TEXT,
            gost_standard TEXT,
            weight_kg REAL,
            volume_m3 REAL,
            characteristics TEXT,  -- JSON с характеристиками
            compatibility_info TEXT,  -- JSON с информацией о совместимости
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)

    # Таблица истории цен
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name_hash TEXT NOT NULL,  -- Хэш названия для группировки
            item_name TEXT NOT NULL,
            supplier_id INTEGER,
            price_per_unit REAL,
            quantity REAL,
            document_id INTEGER,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)

    # Таблица логов обработки
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            status TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)

    # Индексы для ускорения поиска
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_document ON items(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_name ON items(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item ON price_history(item_name_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_supplier ON price_history(supplier_id)")

    conn.commit()
    conn.close()


# === CRUD операции для клиентов ===

def get_or_create_client(name: str) -> int:
    """Получить или создать клиента, вернуть ID"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM clients WHERE name = ?", (name,))
    row = cursor.fetchone()

    if row:
        client_id = row["id"]
    else:
        cursor.execute("INSERT INTO clients (name) VALUES (?)", (name,))
        client_id = cursor.lastrowid
        conn.commit()

    conn.close()
    return client_id


def get_all_clients() -> List[Dict]:
    """Получить всех клиентов"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients ORDER BY name")
    clients = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return clients


# === CRUD операции для поставщиков ===

def get_or_create_supplier(name: str, address: str = None,
                           lat: float = None, lon: float = None,
                           free_delivery: bool = False) -> int:
    """Получить или создать поставщика, вернуть ID"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM suppliers WHERE name = ? AND (address IS NULL OR address = ?)",
                   (name, address or ""))
    row = cursor.fetchone()

    if row:
        supplier_id = row["id"]
        # Обновляем координаты если есть
        if lat and lon:
            cursor.execute("""
                UPDATE suppliers SET coordinates_lat = ?, coordinates_lon = ?
                WHERE id = ?
            """, (lat, lon, supplier_id))
            conn.commit()
    else:
        cursor.execute("""
            INSERT INTO suppliers (name, address, coordinates_lat, coordinates_lon, free_delivery)
            VALUES (?, ?, ?, ?, ?)
        """, (name, address, lat, lon, free_delivery))
        supplier_id = cursor.lastrowid
        conn.commit()

    conn.close()
    return supplier_id


def get_all_suppliers() -> List[Dict]:
    """Получить всех поставщиков"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers ORDER BY name")
    suppliers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return suppliers


def get_supplier_by_name(name: str) -> Optional[Dict]:
    """Найти поставщика по имени"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers WHERE name LIKE ?", (f"%{name}%",))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# === CRUD операции для документов ===

def create_document(doc_type: str, client_id: int = None, supplier_id: int = None,
                    filename: str = None, delivery_address: str = None,
                    total_amount: float = None) -> int:
    """Создать документ (заявку или счет)"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO documents (doc_type, client_id, supplier_id, filename, delivery_address, total_amount)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (doc_type, client_id, supplier_id, filename, delivery_address, total_amount))

    doc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def get_document(doc_id: int) -> Optional[Dict]:
    """Получить документ по ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# === CRUD операции для позиций ===

def create_item(document_id: int, name: str, quantity: float = None,
                unit: str = None, price_per_unit: float = None,
                total_price: float = None, article: str = None,
                gost_standard: str = None, weight_kg: float = None,
                volume_m3: float = None, characteristics: Dict = None,
                compatibility_info: Dict = None) -> int:
    """Создать позицию номенклатуры"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO items (document_id, name, quantity, unit, price_per_unit, total_price,
                          article, gost_standard, weight_kg, volume_m3, characteristics, compatibility_info)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (document_id, name, quantity, unit, price_per_unit, total_price,
          article, gost_standard, weight_kg, volume_m3,
          json.dumps(characteristics) if characteristics else None,
          json.dumps(compatibility_info) if compatibility_info else None))

    item_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return item_id


def get_items_by_document(document_id: int) -> List[Dict]:
    """Получить все позиции документа"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items WHERE document_id = ?", (document_id,))
    items = []
    for row in cursor.fetchall():
        item = dict(row)
        if item.get("characteristics"):
            item["characteristics"] = json.loads(item["characteristics"])
        if item.get("compatibility_info"):
            item["compatibility_info"] = json.loads(item["compatibility_info"])
        items.append(item)
    conn.close()
    return items


def get_items_for_comparison(request_items: List[Dict], invoice_items: List[Dict]) -> List[Dict]:
    """
    Сопоставить позиции заявки и счета
    Возвращает список сравнений с статусами
    """
    results = []

    # Простое сопоставление по названию (можно улучшить с использованием fuzzy matching)
    request_names = {item["name"].lower().strip(): item for item in request_items}
    invoice_names = {item["name"].lower().strip(): item for item in invoice_items}

    matched_invoice = set()

    for req_name, req_item in request_names.items():
        # Ищем точное совпадение
        if req_name in invoice_names:
            inv_item = invoice_names[req_name]
            matched_invoice.add(req_name)

            delta_qty = inv_item["quantity"] - req_item["quantity"] if req_item["quantity"] and inv_item["quantity"] else None
            delta_price = inv_item["price_per_unit"] - req_item["price_per_unit"] if req_item["price_per_unit"] and inv_item["price_per_unit"] else None

            status = "exact_match"
            if delta_qty and abs(delta_qty) > 0.01:
                status = "quantity_diff"
            if delta_price and delta_price > 0.01:
                status = "price_increase" if delta_price > 0 else "price_decrease"

            results.append({
                "item_name": req_item["name"],
                "status": status,
                "request_qty": req_item["quantity"],
                "invoice_qty": inv_item["quantity"],
                "delta_qty": delta_qty,
                "request_price": req_item["price_per_unit"],
                "invoice_price": inv_item["price_per_unit"],
                "delta_price": delta_price,
                "request_total": req_item["total_price"],
                "invoice_total": inv_item["total_price"]
            })
        else:
            # Позиция отсутствует в счете
            results.append({
                "item_name": req_item["name"],
                "status": "missing",
                "request_qty": req_item["quantity"],
                "invoice_qty": None,
                "delta_qty": None,
                "request_price": req_item["price_per_unit"],
                "invoice_price": None,
                "delta_price": None,
                "request_total": req_item["total_price"],
                "invoice_total": None
            })

    # Лишние позиции в счете
    for inv_name, inv_item in invoice_names.items():
        if inv_name not in matched_invoice:
            results.append({
                "item_name": inv_item["name"],
                "status": "extra",
                "request_qty": None,
                "invoice_qty": inv_item["quantity"],
                "delta_qty": None,
                "request_price": None,
                "invoice_price": inv_item["price_per_unit"],
                "delta_price": None,
                "request_total": None,
                "invoice_total": inv_item["total_price"]
            })

    return results


# === История цен ===

def add_price_history(item_name: str, supplier_id: int, price_per_unit: float,
                      quantity: float, document_id: int):
    """Добавить запись в историю цен"""
    import hashlib

    # Создаем хэш названия для группировки похожих товаров
    name_hash = hashlib.md5(item_name.lower().strip().encode()).hexdigest()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO price_history (item_name_hash, item_name, supplier_id, price_per_unit, quantity, document_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name_hash, item_name, supplier_id, price_per_unit, quantity, document_id))

    conn.commit()
    conn.close()


def get_price_history(item_name: str, supplier_id: int = None, limit: int = 10) -> List[Dict]:
    """Получить историю цен для товара"""
    import hashlib

    name_hash = hashlib.md5(item_name.lower().strip().encode()).hexdigest()

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT ph.*, s.name as supplier_name
        FROM price_history ph
        LEFT JOIN suppliers s ON ph.supplier_id = s.id
        WHERE ph.item_name_hash = ?
    """
    params = [name_hash]

    if supplier_id:
        query += " AND ph.supplier_id = ?"
        params.append(supplier_id)

    query += " ORDER BY ph.recorded_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return history


def get_price_statistics(item_name: str) -> Dict:
    """Получить статистику цен для товара"""
    history = get_price_history(item_name, limit=100)

    if not history:
        return {"avg_price": None, "min_price": None, "max_price": None, "trend": "unknown"}

    prices = [h["price_per_unit"] for h in history if h["price_per_unit"]]

    if not prices:
        return {"avg_price": None, "min_price": None, "max_price": None, "trend": "unknown"}

    avg_price = sum(prices) / len(prices)
    min_price = min(prices)
    max_price = max(prices)

    # Определяем тренд (сравнение последних 3 записей с предыдущими 3)
    trend = "stable"
    if len(prices) >= 6:
        recent_avg = sum(prices[:3]) / 3
        old_avg = sum(prices[3:6]) / 3

        if recent_avg > old_avg * 1.05:
            trend = "increasing"
        elif recent_avg < old_avg * 0.95:
            trend = "decreasing"

    return {
        "avg_price": avg_price,
        "min_price": min_price,
        "max_price": max_price,
        "trend": trend,
        "records_count": len(prices)
    }


# === Логи ===

def log_processing(document_id: int, status: str, message: str):
    """Записать лог обработки"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO processing_logs (document_id, status, message)
        VALUES (?, ?, ?)
    """, (document_id, status, message))

    conn.commit()
    conn.close()


def get_processing_logs(document_id: int = None, limit: int = 50) -> List[Dict]:
    """Получить логи обработки"""
    conn = get_connection()
    cursor = conn.cursor()

    if document_id:
        cursor.execute("""
            SELECT * FROM processing_logs
            WHERE document_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (document_id, limit))
    else:
        cursor.execute("""
            SELECT * FROM processing_logs
            ORDER BY created_at DESC LIMIT ?
        """, (limit,))

    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return logs


# Инициализация БД при импорте
init_database()
