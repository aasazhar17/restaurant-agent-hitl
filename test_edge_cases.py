# test_edge_cases.py
from db import reset_db_db, get_item_by_name
from tools import create_order
from graph import get_clarification_prompt


def test_clarification_for_generic_menu_requests():
    prompt = get_clarification_prompt("I want pizza")
    assert prompt is not None
    assert "Margherita Pizza" in prompt
    assert "Pepperoni Pizza" in prompt
    assert "flavor" in prompt.lower() or "quantity" in prompt.lower()


def test_specific_menu_request_does_not_need_clarification():
    prompt = get_clarification_prompt("I want 2 Margherita Pizza")
    assert prompt is None


def test_mixed_specific_and_generic_request_asks_for_missing_details():
    prompt = get_clarification_prompt("I want 2 Margherita Pizza and 1 coke")
    assert prompt is not None
    assert "flavor" in prompt.lower() or "drink" in prompt.lower()


def test_specific_order_can_be_created_for_manager_approval():
    reset_db_db()
    result = create_order.invoke(
        {"items_json": '[{"name": "Margherita Pizza", "qty": 1}]'},
        config={"configurable": {"thread_id": "manager-test"}}
    )
    assert "Order created with ID" in result
    assert "PENDING_APPROVAL" in result
    assert get_item_by_name("Margherita Pizza") is not None


def run_edge_cases():
    test_clarification_for_generic_menu_requests()
    test_specific_menu_request_does_not_need_clarification()
    test_specific_order_can_be_created_for_manager_approval()
    print("All edge-case checks passed.")


if __name__ == "__main__":
    run_edge_cases()
