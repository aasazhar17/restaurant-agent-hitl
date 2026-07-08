# Restaurant Bot Demo Transcript

## 1. Happy path with inventory deduction
- User: "I want 2 Veg Burgers and 1 Coca-Cola."
- Assistant: Checks stock and creates an order in PENDING_APPROVAL.
- Manager: Approves the order.
- Result: Status becomes APPROVED and inventory is deducted immediately.

## 2. Rejection path without deduction
- User: "Please order 1 Margherita Pizza."
- Manager: Rejects the order with a note.
- Result: Status becomes REJECTED and stock remains unchanged.

## 3. Infeasible order blocked before approval
- User: "I need 10 Mango Shakes."
- Assistant: Rejects the request as infeasible because only 5 are in stock.
- Result: No order is created and no manager approval is triggered.

## 4. Status check mid-flow
- User: "What is the status of my order?"
- Assistant: Reports the current state (PENDING_APPROVAL, APPROVED, or REJECTED) from the database.

## 5. Modification triggers re-approval
- User: "Actually change my order to 1 Veg Burger and 2 Coca-Colas."
- Assistant: Restores the previous approved stock, re-checks feasibility, and resets the order to PENDING_APPROVAL.
- Manager: Approves again.
- Result: Inventory is deducted for the new quantities.
