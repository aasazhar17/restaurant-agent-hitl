# test_system.py
import os
import json
from db import reset_db_db, get_item_by_name, get_order_by_id, get_all_orders_db, add_menu_item_db
from tools import (
    check_item_availability,
    check_order_feasibility,
    create_order,
    modify_order,
    update_order_status,
    understand_order_request
)

def run_tests():
    print("=== STARTING RESTAURANT SYSTEM VERIFICATION TESTS ===")
    
    # 1. Reset database
    print("\n[Test 1] Resetting Database...")
    reset_db_db()
    
    # Verify initial stock
    burger = get_item_by_name("Veg Burger")
    coke = get_item_by_name("Coca-Cola")
    print(f"Initial Veg Burger Stock: {burger['available_qty']}")
    print(f"Initial Coca-Cola Stock: {coke['available_qty']}")
    
    assert burger['available_qty'] == 15, "Initial Veg Burger stock should be 15"
    assert coke['available_qty'] == 30, "Initial Coca-Cola stock should be 30"
    print("Test 1 Passed: Database initialized with correct values.")

    # 2. Check Feasibility & Stock Limit
    print("\n[Test 2] Testing Feasibility and Stock Limits...")
    # Single item availability check
    res_avail1 = check_item_availability.invoke({"item_name": "Veg Burger", "qty": 5})
    print("Availability check (5 Veg Burger):", res_avail1)
    assert "AVAILABLE" in res_avail1, "Should be available"
    
    res_avail2 = check_item_availability.invoke({"item_name": "Mango Shake", "qty": 10})
    print("Availability check (10 Mango Shake):", res_avail2)
    assert "UNAVAILABLE" in res_avail2, "Should be unavailable (stock is 5)"

    partial_match = check_item_availability.invoke({"item_name": "pizza", "qty": 1})
    print("Availability check (partial pizza):", partial_match)
    assert "AVAILABLE" in partial_match or "Margherita Pizza" in partial_match or "Pepperoni Pizza" in partial_match, "Partial item names should resolve to a menu item"

    alias_match = check_item_availability.invoke({"item_name": "coke", "qty": 1})
    print("Availability check (alias coke):", alias_match)
    assert "Coca-Cola" in alias_match, "Aliases should resolve to the correct menu item"

    ecommerce_style = understand_order_request.invoke({"message": "Please buy 2 pizzas and 1 coke for me"}, config={"configurable": {"thread_id": "test_thread_ecom"}})
    print("E-commerce style order parsing:", ecommerce_style)
    assert "Order created" in ecommerce_style or "pending approval" in ecommerce_style.lower(), "E-commerce style instructions should create an order"
    reset_db_db()
    
    # Whole cart feasibility
    cart_feasible = check_order_feasibility.invoke({"items_json": '[{"name": "Veg Burger", "qty": 2}, {"name": "Coca-Cola", "qty": 1}]'})
    print("Cart feasibility (feasible):", cart_feasible)
    assert "FEASIBLE" in cart_feasible, "Cart should be feasible"
    
    cart_infeasible = check_order_feasibility.invoke({"items_json": '[{"name": "Mango Shake", "qty": 10}]'})
    print("Cart feasibility (infeasible):", cart_infeasible)
    assert "INFEASIBLE" in cart_infeasible, "Cart should be infeasible"
    print("Test 2 Passed: Feasibility logic validates correctly.")

    # 3. Create Order
    print("\n[Test 3] Creating a new order...")
    # Simulate config
    config = {"configurable": {"thread_id": "test_thread_1"}}
    res_create = create_order.invoke({"items_json": '[{"name": "Veg Burger", "qty": 2}, {"name": "Coca-Cola", "qty": 1}]'}, config=config)
    print("Create order response:", res_create)
    
    # Get created order ID
    orders = get_all_orders_db()
    assert len(orders) == 1, "There should be exactly 1 order"
    order = orders[0]
    order_id = order['order_id']
    print(f"Created Order #{order_id} with status: {order['status']}")
    assert order['status'] == 'PENDING_APPROVAL', "Initial status must be PENDING_APPROVAL"
    
    # Stock should NOT be deducted yet
    burger = get_item_by_name("Veg Burger")
    coke = get_item_by_name("Coca-Cola")
    print(f"Veg Burger Stock after creation: {burger['available_qty']}")
    print(f"Coca-Cola Stock after creation: {coke['available_qty']}")
    assert burger['available_qty'] == 15, "Stock should remain 15 before approval"
    assert coke['available_qty'] == 30, "Stock should remain 30 before approval"
    print("Test 3 Passed: Order created in PENDING_APPROVAL and stock remains intact.")

    # 4. Approve Order (Deducts stock)
    print("\n[Test 4] Approving order (Manager Decision)...")
    res_approve = update_order_status.invoke({"order_id": order_id, "decision": "approve", "note": "Approve it!"})
    print("Approve response:", res_approve)
    
    order = get_order_by_id(order_id)
    print(f"Order status after approval: {order['status']}")
    assert order['status'] == 'APPROVED', "Status should be APPROVED"
    
    # Stock should be deducted
    burger = get_item_by_name("Veg Burger")
    coke = get_item_by_name("Coca-Cola")
    print(f"Veg Burger Stock after approval: {burger['available_qty']}")
    print(f"Coca-Cola Stock after approval: {coke['available_qty']}")
    assert burger['available_qty'] == 13, "Stock of Veg Burger should decrease by 2 to 13"
    assert coke['available_qty'] == 29, "Stock of Coca-Cola should decrease by 1 to 29"
    print("Test 4 Passed: Stock is correctly deducted on order approval.")

    # 5. Modify Approved Order (Restores old stock, resets to PENDING_APPROVAL)
    print("\n[Test 5] Modifying approved order...")
    # Change items to: 1 Veg Burger, 2 Coca-Cola (Replaces 2 Veg Burgers and 1 Coca-Cola)
    res_modify = modify_order.invoke({"order_id": order_id, "new_items_json": '[{"name": "Veg Burger", "qty": 1}, {"name": "Coca-Cola", "qty": 2}]'})
    print("Modify response:", res_modify)
    
    order = get_order_by_id(order_id)
    print(f"Order status after modification: {order['status']}")
    assert order['status'] == 'PENDING_APPROVAL', "Status should reset to PENDING_APPROVAL"
    
    # Stock should be restored (since it went back to PENDING_APPROVAL)
    burger = get_item_by_name("Veg Burger")
    coke = get_item_by_name("Coca-Cola")
    print(f"Veg Burger Stock after modification (restored): {burger['available_qty']}")
    print(f"Coca-Cola Stock after modification (restored): {coke['available_qty']}")
    assert burger['available_qty'] == 15, "Veg Burger stock should restore back to 15"
    assert coke['available_qty'] == 30, "Coca-Cola stock should restore back to 30"
    print("Test 5 Passed: Stock restored correctly on modification.")

    # 6. Re-approve Modified Order (Deducts new stock)
    print("\n[Test 6] Re-approving modified order...")
    res_approve2 = update_order_status.invoke({"order_id": order_id, "decision": "approve", "note": "Re-approved!"})
    print("Re-approve response:", res_approve2)
    
    order = get_order_by_id(order_id)
    print(f"Order status after re-approval: {order['status']}")
    assert order['status'] == 'APPROVED', "Status should be APPROVED again"
    
    # Stock should be deducted for new items (1 Veg Burger, 2 Cokes)
    burger = get_item_by_name("Veg Burger")
    coke = get_item_by_name("Coca-Cola")
    print(f"Veg Burger Stock after re-approval: {burger['available_qty']}")
    print(f"Coca-Cola Stock after re-approval: {coke['available_qty']}")
    assert burger['available_qty'] == 14, "Veg Burger stock should be 14 (15 - 1)"
    assert coke['available_qty'] == 28, "Coca-Cola stock should be 28 (30 - 2)"
    print("Test 6 Passed: New stock quantities deducted correctly on re-approval.")

    # 7. Reject Order (Rejection Path)
    print("\n[Test 7] Rejecting order modification and testing rejection path...")
    # Modify again
    modify_order.invoke({"order_id": order_id, "new_items_json": '[{"name": "Veg Burger", "qty": 3}, {"name": "Coca-Cola", "qty": 3}]'})
    
    # Stocks should be restored again
    burger = get_item_by_name("Veg Burger")
    coke = get_item_by_name("Coca-Cola")
    assert burger['available_qty'] == 15, "Veg Burger stock restored to 15"
    assert coke['available_qty'] == 30, "Coca-Cola stock restored to 30"
    
    # Manager rejects it
    res_reject = update_order_status.invoke({"order_id": order_id, "decision": "reject", "note": "Too many items!"})
    print("Reject response:", res_reject)
    
    order = get_order_by_id(order_id)
    print(f"Order status after rejection: {order['status']}")
    assert order['status'] == 'REJECTED', "Status should be REJECTED"
    
    # Stock should NOT be deducted (remains at restored/initial level since order was rejected)
    burger = get_item_by_name("Veg Burger")
    coke = get_item_by_name("Coca-Cola")
    print(f"Veg Burger Stock after rejection: {burger['available_qty']}")
    print(f"Coca-Cola Stock after rejection: {coke['available_qty']}")
    assert burger['available_qty'] == 15, "Stock remains at 15"
    assert coke['available_qty'] == 30, "Stock remains at 30"
    print("Test 7 Passed: Rejected orders leave stock untouched and update status correctly.")

    print("\n[Test 8] Testing newly added menu item can be understood from chat-style request...")
    reset_db_db()
    add_menu_item_db("Spicy Fries", 120, 8)
    parsed = understand_order_request.invoke({"message": "Please order 2 spicy fries"}, config={"configurable": {"thread_id": "test_thread_new_item"}})
    print("New item parsing:", parsed)
    assert "Order created" in parsed or "pending approval" in parsed.lower(), "Newly added menu items should be orderable from chat"
    orders = get_all_orders_db()
    assert orders, "An order should have been created for the new item"
    assert orders[-1]['items'][0]['name'] == "Spicy Fries", "The newly added menu item should be recognized by the parser"
    print("Test 8 Passed: Newly added menu items are recognized in chat-style requests.")

    print("\n=== ALL CORE VERIFICATION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_tests()
