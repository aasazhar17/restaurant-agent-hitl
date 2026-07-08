# test_edge_cases.py
import sys
import os
import json
from db import (
    init_db,
    reset_db_db,
    get_item_by_name,
    get_order_by_id,
    approve_order_and_deduct_stock_db,
    partial_approve_order_db,
    modify_order_in_db,
    cancel_order_db,
    deliver_order_db
)
from tools import cancel_order, create_order
from graph import tools_node
from langchain_core.messages import AIMessage

def run_edge_cases():
    print("\n[Test 0] Natural-language order creation should enter pending approval state...")
    reset_db_db()
    state = {
        "messages": [AIMessage(content="", tool_calls=[{"id": "1", "name": "understand_order_request", "args": {"message": "buy 2 Veg Burgers"}}])],
        "current_order_id": None,
        "pending_approval": False,
    }
    result = tools_node(state, {"configurable": {"thread_id": "approval-debug"}})
    print("Pending approval state after parsing order:", result.get("pending_approval"), result.get("current_order_id"))
    assert result.get("pending_approval") is True, "Natural-language order parsing must trigger pending approval"
    assert result.get("current_order_id") is not None, "The resulting order ID should be captured"
    print("-> Test 0 Passed!")
    print("=== STARTING EDGE CASE CONSTRAINT TESTS ===")
    
    # Reset DB
    reset_db_db()
    
    # 1. Create a dummy order manually in DB
    # We will simulate the transition steps
    from db import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    
    # Insert order #1: PENDING_APPROVAL
    cursor.execute(
        "INSERT INTO orders (order_id, customer_thread_id, items, status) VALUES (1, 't1', ?, 'PENDING_APPROVAL')",
        (json.dumps([{"name": "Veg Burger", "qty": 2}]),)
    )
    
    # Insert order #2: DELIVERED
    cursor.execute(
        "INSERT INTO orders (order_id, customer_thread_id, items, status) VALUES (2, 't1', ?, 'DELIVERED')",
        (json.dumps([{"name": "Veg Burger", "qty": 1}]),)
    )
    
    # Insert order #3: CANCELLED
    cursor.execute(
        "INSERT INTO orders (order_id, customer_thread_id, items, status) VALUES (3, 't1', ?, 'CANCELLED')",
        (json.dumps([{"name": "Veg Burger", "qty": 1}]),)
    )
    
    # Insert order #4: REJECTED
    cursor.execute(
        "INSERT INTO orders (order_id, customer_thread_id, items, status) VALUES (4, 't1', ?, 'REJECTED')",
        (json.dumps([{"name": "Veg Burger", "qty": 1}]),)
    )
    
    conn.commit()
    conn.close()
    
    # --- TEST 1: Cancel delivered order block ---
    print("\n[Test 1] Attempting to cancel a DELIVERED order...")
    success, msg = cancel_order_db(2)
    print(f"Result: success={success}, message={msg}")
    assert not success, "Should fail to cancel a delivered order"
    assert "delivered" in msg.lower(), "Should output error about delivered status"
    print("-> Test 1 Passed!")
    
    # --- TEST 2: Approve non-pending order block ---
    print("\n[Test 2] Attempting to approve a DELIVERED/REJECTED/CANCELLED order...")
    # Delivered
    success, msg = approve_order_and_deduct_stock_db(2, "Approve delivered")
    print(f"Delivered approval result: success={success}, msg={msg}")
    assert not success, "Should fail to approve delivered order"
    
    # Cancelled
    success, msg = approve_order_and_deduct_stock_db(3, "Approve cancelled")
    print(f"Cancelled approval result: success={success}, msg={msg}")
    assert not success, "Should fail to approve cancelled order"
    
    # Rejected
    success, msg = approve_order_and_deduct_stock_db(4, "Approve rejected")
    print(f"Rejected approval result: success={success}, msg={msg}")
    assert not success, "Should fail to approve rejected order"
    print("-> Test 2 Passed!")
    
    # --- TEST 3: Partial approve non-pending order block ---
    print("\n[Test 3] Attempting to partially approve a DELIVERED/REJECTED/CANCELLED order...")
    # Delivered
    success, msg = partial_approve_order_db(2, ["Veg Burger"], "Partial delivered")
    print(f"Delivered partial approval: success={success}, msg={msg}")
    assert not success, "Should fail"
    
    # Cancelled
    success, msg = partial_approve_order_db(3, ["Veg Burger"], "Partial cancelled")
    print(f"Cancelled partial approval: success={success}, msg={msg}")
    assert not success, "Should fail"
    
    # Rejected
    success, msg = partial_approve_order_db(4, ["Veg Burger"], "Partial rejected")
    print(f"Rejected partial approval: success={success}, msg={msg}")
    assert not success, "Should fail"
    print("-> Test 3 Passed!")
    
    # --- TEST 4: Modify cancelled order block ---
    print("\n[Test 4] Attempting to modify a CANCELLED order...")
    success, msg = modify_order_in_db(3, [{"name": "Veg Burger", "qty": 2}])
    print(f"Modify cancelled: success={success}, msg={msg}")
    assert not success, "Should fail to modify a cancelled order"
    assert "cancelled" in msg.lower(), "Should output error about cancelled status"
    print("-> Test 4 Passed!")
    
    # --- TEST 5: Normal approval of pending order ---
    print("\n[Test 5] Approving order #1 (PENDING_APPROVAL)...")
    initial_stock = get_item_by_name("Veg Burger")["available_qty"]
    success, msg = approve_order_and_deduct_stock_db(1, "Approve order 1")
    new_stock = get_item_by_name("Veg Burger")["available_qty"]
    print(f"Approval result: success={success}, msg={msg}, stock: {initial_stock} -> {new_stock}")
    assert success, "Should succeed"
    assert new_stock == initial_stock - 2, "Stock should decrease by 2"
    print("-> Test 5 Passed!")

    print("\n[Test 6] Infeasible create order should be blocked before approval...")
    reset_db_db()
    result = create_order.invoke({"items_json": '[{"name": "Mango Shake", "qty": 10}]'}, config={"configurable": {"thread_id": "infeasible-thread"}})
    print("Infeasible create order response:", result)
    assert "INFEASIBLE" in result, "Infeasible orders should be rejected before manager approval"
    assert "Order created" not in result, "An infeasible order should not be created"
    print("-> Test 6 Passed!")

    print("\n=== ALL EDGE CASE CONSTRAINT TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_edge_cases()
