from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from typing import Optional
import json
from db import (
    get_item_by_name, 
    create_order_db, 
    get_order_by_id, 
    update_order_status_db,
    approve_order_and_deduct_stock_db,
    modify_order_in_db,
    cancel_order_db
)


def _resolve_item_name(item_name: str) -> str:
    resolved_item = get_item_by_name(item_name)
    return resolved_item['name'] if resolved_item else item_name


@tool
def check_item_availability(item_name: str, qty: int) -> str:
    """
    Check if a single item is available in the requested quantity.
    Input: item_name (str), qty (int)
    """
    resolved_name = _resolve_item_name(item_name)
    db_item = get_item_by_name(resolved_name)
    if not db_item:
        return f"UNAVAILABLE: {item_name} is not on the menu."
    avail = db_item['available_qty']
    if avail < qty:
        return f"UNAVAILABLE: Only {avail} of {db_item['name']} available in stock."
    return f"AVAILABLE: {db_item['name']} is in stock with {avail} units available."

@tool
def check_order_feasibility(items_json: str, order_id: Optional[int] = None) -> str:
    """
    Check if the entire cart is feasible against live inventory.
    Input: items_json (JSON string of list like [{"name": "Veg Burger", "qty": 2}])
    Optional: order_id (int) if checking feasibility for modifying an existing order.
    """
    try:
        items = json.loads(items_json)
        resolved_items = []
        for item in items:
            resolved_name = _resolve_item_name(item['name'])
            item_copy = dict(item)
            item_copy['name'] = resolved_name
            resolved_items.append(item_copy)
        items = resolved_items
        
        # If we are checking feasibility for an order modification,
        # we temporarily restore the stock of the old items if the order was approved.
        restored_stock = {}
        if order_id is not None:
            order = get_order_by_id(order_id)
            if order and order['status'] == 'APPROVED':
                for item in order['items']:
                    restored_stock[item['name'].lower()] = item['qty']
                    
        for item in items:
            name = item['name']
            qty = item['qty']
            db_item = get_item_by_name(name)
            if not db_item:
                return f"INFEASIBLE: '{name}' is not on the menu."
            
            extra = restored_stock.get(name.lower(), 0)
            available = db_item['available_qty'] + extra
            if available < qty:
                return f"INFEASIBLE: Only {available} '{db_item['name']}' left in stock."
                
        return "FEASIBLE: Order is feasible and can be sent for approval."
    except Exception as e:
        return f"Error checking feasibility: {str(e)}"

@tool
def create_order(items_json: str, config: RunnableConfig) -> str:
    """
    Creates a new order with status PENDING_APPROVAL.
    Input: items_json (JSON string of list like [{"name": "Veg Burger", "qty": 2}])
    """
    try:
        thread_id = config.get("configurable", {}).get("thread_id", "default_thread")
        items = json.loads(items_json)
        resolved_items = []
        for item in items:
            resolved_name = _resolve_item_name(item['name'])
            resolved_items.append({"name": resolved_name, "qty": item['qty']})
        order_id = create_order_db(thread_id, resolved_items)
        return f"Order created with ID: {order_id}. Status: PENDING_APPROVAL. Waiting for manager approval."
    except Exception as e:
        return f"Error creating order: {str(e)}"

@tool
def get_order_status(order_id: int) -> str:
    """
    Fetch the current status of an order.
    Input: order_id (int)
    """
    order = get_order_by_id(order_id)
    if not order:
        return f"Order #{order_id} not found."
    return f"Order #{order_id}: Status = {order['status']}. Items = {order['items']}. Manager Note = '{order.get('manager_note', '')}'."

@tool
def modify_order(order_id: int, new_items_json: str) -> str:
    """
    Modifies items in an existing order. Resets status to PENDING_APPROVAL.
    Input: order_id (int), new_items_json (JSON string of list like [{"name": "Veg Burger", "qty": 1}])
    """
    try:
        new_items = json.loads(new_items_json)
        resolved_items = []
        for item in new_items:
            resolved_name = _resolve_item_name(item['name'])
            resolved_items.append({"name": resolved_name, "qty": item['qty']})
        success, message = modify_order_in_db(order_id, resolved_items)
        if success:
            return f"Order #{order_id} modified successfully. Status reset to PENDING_APPROVAL. Please get manager approval again."
        else:
            return f"Error modifying order: {message}"
    except Exception as e:
        return f"Error modifying order: {str(e)}"

@tool
def update_order_status(order_id: int, decision: str, note: str = "") -> str:
    """
    Approve or reject a pending order.
    Input: order_id (int), decision ('approve' or 'reject'), note (str)
    """
    decision_clean = decision.strip().lower()
    if decision_clean == "approve":
        success, message = approve_order_and_deduct_stock_db(order_id, note)
        if success:
            return f"Order #{order_id} APPROVED. Stock deducted. Status updated to APPROVED."
        else:
            return f"Approval failed: {message}"
    elif decision_clean == "reject":
        update_order_status_db(order_id, "REJECTED", note)
        return f"Order #{order_id} REJECTED. Reason/Note: {note}."
    else:
        return "Invalid decision. Use 'approve' or 'reject'."

@tool
def cancel_order(order_id: int) -> str:
    """
    Cancels an order. If it was approved, restores inventory to stock.
    Input: order_id (int)
    """
    try:
        success, message = cancel_order_db(order_id)
        if success:
            return f"Order #{order_id} has been CANCELLED successfully. Stock is restored if it was approved."
        else:
            return f"Error cancelling order: {message}"
    except Exception as e:
        return f"Error cancelling order: {str(e)}"