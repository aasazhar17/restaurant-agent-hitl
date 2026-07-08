import sqlite3
import json
import re
from datetime import datetime

# Database file path
DB_PATH = "data/restaurant.db"

def get_connection():
    """Returns database connection with row factory configured."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes tables and populates sample menu items."""
    import os
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Menu Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS menu (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price REAL NOT NULL,
            available_qty INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # 2. Orders Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_thread_id TEXT NOT NULL,
            items TEXT NOT NULL,  -- JSON list: [{"name": "Pizza", "qty": 2}]
            status TEXT DEFAULT 'DRAFT',
            manager_note TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. Insert default menu items
    sample_items = [
        ("Margherita Pizza", 299, 10, 1),
        ("Pepperoni Pizza", 399, 8, 1),
        ("Veg Burger", 149, 15, 1),
        ("Chicken Burger", 199, 12, 1),
        ("French Fries", 99, 20, 1),
        ("Coca-Cola", 60, 30, 1),
        ("Mango Shake", 120, 5, 1),
    ]

    for name, price, qty, active in sample_items:
        cursor.execute('''
            INSERT OR IGNORE INTO menu (name, price, available_qty, is_active)
            VALUES (?, ?, ?, ?)
        ''', (name, price, qty, active))

    conn.commit()
    conn.close()
    print("Database initialized successfully!")

def reset_db_db():
    """Drops tables and re-initializes database (for testing reset)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS menu")
    cursor.execute("DROP TABLE IF EXISTS orders")
    conn.commit()
    conn.close()
    init_db()


def add_menu_item_db(name, price, stock, active=1):
    """Add a new menu item for admin management."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO menu (name, price, available_qty, is_active) VALUES (?, ?, ?, ?)",
            (name, price, stock, active)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_menu_item_db(item_id, name=None, price=None, stock=None, active=None):
    """Update an existing menu item from the admin console."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if price is not None:
            updates.append("price = ?")
            params.append(price)
        if stock is not None:
            updates.append("available_qty = ?")
            params.append(stock)
        if active is not None:
            updates.append("is_active = ?")
            params.append(active)

        if not updates:
            return False

        params.append(item_id)
        cursor.execute(f"UPDATE menu SET {', '.join(updates)} WHERE item_id = ?", params)
        conn.commit()
        return True
    finally:
        conn.close()

# ------------------ SELECTION & CREATION HELPERS ------------------

ALIASES = {
    "coke": "Coca-Cola",
    "cola": "Coca-Cola",
    "mobile": "Phone",
    "phone": "Phone",
    "burger": "Veg Burger",
    "fries": "French Fries",
    "shake": "Mango Shake",
    "pizza": "Margherita Pizza",
}


def _normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _get_menu_items():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM menu WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_menu_items_db():
    """Return all active menu items from the database."""
    return _get_menu_items()


def get_item_by_name(name):
    """Fetch item by name with fuzzy matching and simple aliases."""
    if not name:
        return None

    normalized_query = _normalize(name)
    if not normalized_query:
        return None

    alias_target = ALIASES.get(normalized_query)
    if alias_target:
        name = alias_target
        normalized_query = _normalize(name)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM menu WHERE LOWER(name) = LOWER(?) AND is_active = 1", (name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)

    items = _get_menu_items()
    if not items:
        return None

    normalized_items = []
    for item in items:
        candidate = _normalize(item['name'])
        normalized_items.append((candidate, item))

    # Exact token overlap first
    query_tokens = set(normalized_query.split())
    scored = []
    for candidate, item in normalized_items:
        candidate_tokens = set(candidate.split())
        overlap = len(query_tokens & candidate_tokens)
        if overlap:
            score = overlap
            if candidate.startswith(normalized_query) or normalized_query.startswith(candidate):
                score += 5
            if normalized_query in candidate or candidate in normalized_query:
                score += 3
            scored.append((score, item))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        top_score, top_item = scored[0]
        if top_score > 0:
            return top_item

    return None

def get_order_by_id(order_id):
    """Fetch order details and parse JSON items."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        order = dict(row)
        order['items'] = json.loads(order['items'])
        return order
    return None

def get_all_orders_db():
    """Fetch all orders sorted by newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    orders = []
    for row in rows:
        order = dict(row)
        order['items'] = json.loads(order['items'])
        orders.append(order)
    return orders

def create_order_db(thread_id, items_list):
    """Creates a new order with status PENDING_APPROVAL."""
    conn = get_connection()
    cursor = conn.cursor()
    items_json = json.dumps(items_list)
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO orders (customer_thread_id, items, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (thread_id, items_json, 'PENDING_APPROVAL', now, now))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

# ------------------ STOCKS & STATUS CONTROL (TRANSACTIONAL) ------------------

def deduct_stock(item_name, qty):
    """Deduct stock of a single item. Returns True if successful."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT available_qty FROM menu WHERE LOWER(name) = LOWER(?)", (item_name,))
        row = cursor.fetchone()
        if not row or row[0] < qty:
            return False
        cursor.execute("UPDATE menu SET available_qty = available_qty - ? WHERE LOWER(name) = LOWER(?)", (qty, item_name))
        conn.commit()
        return True
    except Exception as e:
        print("Deduct stock error:", e)
        return False
    finally:
        conn.close()

def restore_stock(item_name, qty):
    """Restore stock of a single item."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE menu SET available_qty = available_qty + ? WHERE LOWER(name) = LOWER(?)", (qty, item_name))
        conn.commit()
        return True
    except Exception as e:
        print("Restore stock error:", e)
        return False
    finally:
        conn.close()

def approve_order_and_deduct_stock_db(order_id, note=""):
    """
    Approves an order and deducts inventory in a single SQLite transaction.
    Returns (True, message) if approved, or (False, error_msg) if out of stock.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        # 1. Fetch order
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "Order not found."
        
        order = dict(row)
        old_status = order['status']
        if old_status == 'APPROVED':
            conn.rollback()
            return True, "Order is already approved."
        elif old_status != 'PENDING_APPROVAL':
            conn.rollback()
            return False, f"Cannot approve an order that is {old_status}. Only PENDING_APPROVAL orders can be approved."
            
        items = json.loads(order['items'])
        
        # 2. Check and deduct stock for each item
        for item in items:
            name = item['name']
            qty = item['qty']
            
            cursor.execute("SELECT available_qty FROM menu WHERE LOWER(name) = LOWER(?) AND is_active = 1", (name,))
            menu_row = cursor.fetchone()
            if not menu_row:
                conn.rollback()
                return False, f"Item '{name}' is not on the menu or is inactive."
            
            avail = menu_row[0]
            if avail < qty:
                conn.rollback()
                return False, f"Insufficient stock for '{name}'. Required: {qty}, Available: {avail}."
            
            # Deduct stock
            cursor.execute("UPDATE menu SET available_qty = available_qty - ? WHERE LOWER(name) = LOWER(?)", (qty, name))
            
        # 3. Update status to APPROVED
        now = datetime.now().isoformat()
        cursor.execute('''
            UPDATE orders 
            SET status = 'APPROVED', manager_note = ?, updated_at = ?
            WHERE order_id = ?
        ''', (note, now, order_id))
        
        conn.commit()
        return True, "Order approved and stock deducted successfully."
    except Exception as e:
        conn.rollback()
        return False, f"Database error during approval: {str(e)}"
    finally:
        conn.close()

def modify_order_in_db(order_id, new_items_list):
    """
    Modifies an order. If it was APPROVED, restores stock before checking and applying modification.
    Sets status back to PENDING_APPROVAL. Returns (True, message) or (False, error_msg).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        # 1. Fetch old order
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "Order not found."
        
        order = dict(row)
        old_items = json.loads(order['items'])
        old_status = order['status']
        
        if old_status in ['DELIVERED', 'CANCELLED']:
            conn.rollback()
            return False, f"Cannot modify a {old_status.lower()} order."
        
        # 2. If status was APPROVED, restore stock temporarily inside the transaction
        if old_status == 'APPROVED':
            for item in old_items:
                cursor.execute("UPDATE menu SET available_qty = available_qty + ? WHERE LOWER(name) = LOWER(?)", (item['qty'], item['name']))
                
        # 3. Check feasibility of new items
        for item in new_items_list:
            name = item['name']
            qty = item['qty']
            
            cursor.execute("SELECT available_qty FROM menu WHERE LOWER(name) = LOWER(?) AND is_active = 1", (name,))
            menu_row = cursor.fetchone()
            if not menu_row:
                conn.rollback()
                return False, f"Item '{name}' is not on the menu or is inactive."
                
            avail = menu_row[0]
            if avail < qty:
                conn.rollback()
                return False, f"Insufficient stock for '{name}'. Required: {qty}, Available: {avail}."
                
        # 4. Save new items and reset status to PENDING_APPROVAL
        items_json = json.dumps(new_items_list)
        now = datetime.now().isoformat()
        cursor.execute('''
            UPDATE orders 
            SET items = ?, status = 'PENDING_APPROVAL', updated_at = ?
            WHERE order_id = ?
        ''', (items_json, now, order_id))
        
        conn.commit()
        return True, "Order modified successfully and reset to PENDING_APPROVAL."
    except Exception as e:
        conn.rollback()
        return False, f"Database error during modification: {str(e)}"
    finally:
        conn.close()

def deliver_order_db(order_id):
    """Transition status from APPROVED to DELIVERED."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        UPDATE orders 
        SET status = 'DELIVERED', updated_at = ?
        WHERE order_id = ? AND status = 'APPROVED'
    ''', (now, order_id))
    changes = conn.total_changes
    conn.commit()
    conn.close()
    return changes > 0

def update_order_status_db(order_id, new_status, note=""):
    """Normal status updates (e.g. DRAFT or REJECTED) without complex transaction."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        UPDATE orders 
        SET status = ?, manager_note = ?, updated_at = ?
        WHERE order_id = ?
    ''', (new_status, note, now, order_id))
    conn.commit()
    conn.close()

def update_order_items_db(order_id, new_items_list):
    """Normal item updates resetting status to PENDING_APPROVAL without complex transaction."""
    conn = get_connection()
    cursor = conn.cursor()
    items_json = json.dumps(new_items_list)
    now = datetime.now().isoformat()
    cursor.execute('''
        UPDATE orders 
        SET items = ?, status = 'PENDING_APPROVAL', updated_at = ?
        WHERE order_id = ?
    ''', (items_json, now, order_id))
    conn.commit()
    conn.close()

def cancel_order_db(order_id):
    """
    Cancels an order. If it was APPROVED, restores its items' stock.
    Sets status to 'CANCELLED'.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        # 1. Fetch order
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "Order not found."
            
        order = dict(row)
        old_status = order['status']
        
        if old_status == 'DELIVERED':
            conn.rollback()
            return False, "Cannot cancel a delivered order."
            
        if old_status == 'CANCELLED':
            conn.rollback()
            return True, "Order is already cancelled."
            
        # 2. If it was APPROVED, restore stock
        if old_status == 'APPROVED':
            items = json.loads(order['items'])
            for item in items:
                cursor.execute("UPDATE menu SET available_qty = available_qty + ? WHERE LOWER(name) = LOWER(?)", (item['qty'], item['name']))
                
        # 3. Update status to CANCELLED
        now = datetime.now().isoformat()
        cursor.execute('''
            UPDATE orders 
            SET status = 'CANCELLED', updated_at = ?
            WHERE order_id = ?
        ''', (now, order_id))
        
        conn.commit()
        return True, "Order cancelled successfully."
    except Exception as e:
        conn.rollback()
        return False, f"Database error during cancellation: {str(e)}"
    finally:
        conn.close()

def partial_approve_order_db(order_id, approved_item_names, note=""):
    """
    Partially approves an order: deducts stock only for approved items,
    updates the order items list to only contain approved items,
    and sets status to 'APPROVED'. Old stock is NOT deducted for rejected items.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        # 1. Fetch order
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "Order not found."
            
        order = dict(row)
        old_status = order['status']
        if old_status == 'APPROVED':
            conn.rollback()
            return True, "Order is already approved."
        elif old_status != 'PENDING_APPROVAL':
            conn.rollback()
            return False, f"Cannot partially approve an order that is {old_status}. Only PENDING_APPROVAL orders can be approved."
            
        items = json.loads(order['items'])
        
        # 2. Filter approved items & rejected items
        approved_items = []
        rejected_items = []
        for item in items:
            if item['name'] in approved_item_names:
                approved_items.append(item)
            else:
                rejected_items.append(item)
                
        if not approved_items:
            conn.rollback()
            return False, "Cannot partially approve with 0 items. Please reject the order instead."
            
        # 3. Check and deduct stock for approved items only
        for item in approved_items:
            name = item['name']
            qty = item['qty']
            
            cursor.execute("SELECT available_qty FROM menu WHERE LOWER(name) = LOWER(?) AND is_active = 1", (name,))
            menu_row = cursor.fetchone()
            if not menu_row:
                conn.rollback()
                return False, f"Item '{name}' is not on the menu or is inactive."
                
            avail = menu_row[0]
            if avail < qty:
                conn.rollback()
                return False, f"Insufficient stock for '{name}'. Required: {qty}, Available: {avail}."
                
            # Deduct stock
            cursor.execute("UPDATE menu SET available_qty = available_qty - ? WHERE LOWER(name) = LOWER(?)", (qty, name))
            
        # 4. Update the order items to approved list, update status to APPROVED, add manager note
        items_json = json.dumps(approved_items)
        now = datetime.now().isoformat()
        
        # Format manager note to document partial approval
        rejected_str = ", ".join([f"{item['name']} (x{item['qty']})" for item in rejected_items])
        full_note = f"{note} [Partially Approved. Rejected items: {rejected_str}]" if rejected_items else note
        
        cursor.execute('''
            UPDATE orders 
            SET items = ?, status = 'APPROVED', manager_note = ?, updated_at = ?
            WHERE order_id = ?
        ''', (items_json, full_note, now, order_id))
        
        conn.commit()
        return True, f"Order partially approved. Deducted stock only for approved items. Rejected: {rejected_str or 'None'}."
    except Exception as e:
        conn.rollback()
        return False, f"Database error during partial approval: {str(e)}"
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()