import sqlite3
from datetime import datetime

def init_db(conn):
    """Инициализация базы данных"""
    cursor = conn.cursor()
    
    # Таблица поставщиков
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            address TEXT,
            rating REAL DEFAULT 0.0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица счетов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER,
            file_name TEXT,
            date_received TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_amount REAL,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
        )
    ''')
    
    # Таблица позиций (история цен)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            item_name TEXT,
            quantity REAL,
            price_unit REAL,
            total_price REAL,
            unit TEXT,
            FOREIGN KEY (invoice_id) REFERENCES invoices (id)
        )
    ''')
    
    conn.commit()

def get_or_create_supplier(conn, name, address=""):
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM suppliers WHERE name = ?", (name,))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    else:
        cursor.execute("INSERT INTO suppliers (name, address) VALUES (?, ?)", (name, address))
        conn.commit()
        return cursor.lastrowid

def save_invoice(conn, supplier_name, file_name, items, total_amount=0.0, address=""):
    cursor = conn.cursor()
    supplier_id = get_or_create_supplier(conn, supplier_name, address)
    
    cursor.execute("INSERT INTO invoices (supplier_id, file_name, total_amount) VALUES (?, ?, ?)",
                   (supplier_id, file_name, total_amount))
    invoice_id = cursor.lastrowid
    
    for item in items:
        cursor.execute('''
            INSERT INTO items_history (invoice_id, item_name, quantity, price_unit, total_price, unit)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            invoice_id,
            item.get('name', 'Unknown'),
            item.get('quantity', 0),
            item.get('price', 0),
            item.get('total', 0),
            item.get('unit', 'шт')
        ))
    
    conn.commit()
    return invoice_id

def get_price_history(conn, item_name_pattern):
    cursor = conn.cursor()
    cursor.execute('''
        SELECT i.item_name, i.price_unit, i.quantity, s.name, inv.date_received
        FROM items_history i
        JOIN invoices inv ON i.invoice_id = inv.id
        JOIN suppliers s ON inv.supplier_id = s.id
        WHERE i.item_name LIKE ?
        ORDER BY inv.date_received DESC
        LIMIT 50
    ''', (f'%{item_name_pattern}%',))
    
    columns = ['item_name', 'price', 'quantity', 'supplier', 'date']
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def get_supplier_info(conn, supplier_name):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers WHERE name = ?", (supplier_name,))
    row = cursor.fetchone()
    if row:
        return {"id": row[0], "name": row[1], "address": row[2], "rating": row[3]}
    return {}
