# GourmetBot - Restaurant Ordering System with HITL Approval

A LangGraph-based conversational agent that takes food orders from customers in natural language, validates them against a live database of menu/inventory, and requires manager approval (Human-In-The-Loop) before any order is confirmed for cooking.

## 🛠️ System Components

1. **Database (SQLite)**: Stores the live menu items, available quantities, and order details (including a JSON array of items, current status, manager notes, and timestamps).
2. **LangGraph Agent**: Orchestrates the conversation flow using a MemorySaver checkpointer, validates inventory availability, automatically extracts thread/session IDs, and pauses execution using `interrupt()` for HITL approval.
3. **FastAPI Backend Server**: Hosts API endpoints to converse with the agent, process approvals, retrieve orders, perform deliveries, reset the database, and serve static assets.
4. **Interactive Dashboard Frontend**: A stunning, dark-themed, glassmorphic single-page web app. The left side is a customer chat panel for placing orders, checking status, and requesting modifications. The right side is a manager dashboard showing live menu inventory, pending approvals queue, and an order tracker.

---

## 🔄 Order Status Lifecycle

The system enforces a strict, finite state machine for orders:

```
           [ DRAFT ] (Initial state, if used)
              │
              ▼
    [ PENDING_APPROVAL ]  ◄───────────────────────┐ (on modification)
      /             \                             │
     /               \                            │
    ▼                 ▼                           │
[ APPROVED ]    [ REJECTED ]                      │
 (cooking)            │                           │
    │                 │                           │
    ▼                 │ (if edited & resubmitted) │
[ DELIVERED ] ────────┴───────────────────────────┘
```

### Transition & Inventory Rules:
1. **Creation**: Placing an order inserts it in `PENDING_APPROVAL` status. **No stock is deducted** at this point so that we don't block inventory for orders that may never be approved.
2. **Approval**: When the manager approves an order:
   - The status is updated to `APPROVED` (cooking).
   - Item quantities are **automatically deducted** from the live menu inventory inside a single SQLite transaction.
   - If stock is insufficient for any item at the moment of approval (e.g., due to concurrent approvals), the transaction rolls back, and approval fails.
3. **Rejection**: If the manager rejects the order, status updates to `REJECTED`. **No stock is deducted**.
4. **Modification**: Customers can modify an order at any stage:
   - **If the order was already APPROVED**: Modifying it triggers a transaction that temporarily restores the old items' stock, verifies if the new items are feasible against this restored inventory, updates the items, and resets the status to `PENDING_APPROVAL`. If the check fails, the transaction rolls back, keeping the order `APPROVED` and stock deducted.
   - **If the order was PENDING_APPROVAL or REJECTED**: The items are checked directly against live stock (no stock was deducted yet). If feasible, the items are updated, and status remains/resets to `PENDING_APPROVAL` for review.
5. **Delivery**: The manager can transition an `APPROVED` order to `DELIVERED` to complete the order lifecycle.

---

## 🛠️ Installation & Setup

1. **Virtual Environment**:
   Ensure you have a Python virtual environment set up and activated. If not:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate  # On Windows
   ```

2. **Install Dependencies**:
   Install the required packages:
   ```bash
   pip install fastapi uvicorn langchain-core langgraph langchain-groq python-dotenv aiofiles
   ```

3. **Configure API Key**:
   Create a `.env` file in the root directory (one is already prepared with a valid key for evaluation):
   ```env
   GROQ_API_KEY="your-groq-api-key"
   ```

---

## 🚀 Running the Project

### 1. Run Automated Verification Tests
We have built a test suite (`test_system.py`) that exercises all order lifecycle states, stock deduction, and modification-triggered restorations.
Run it using:
```bash
.\venv\Scripts\python.exe test_system.py
```
*This validates the database transaction integrity and outputs step-by-step confirmation of stock deductions and restorations.*

### 2. Start the Backend Server
Start the FastAPI server:
```bash
.\venv\Scripts\python.exe server.py
```
The server will bind to `http://127.0.0.1:8000` and initialize/seed the database.

### 3. Open the Dashboard Frontend
Open your browser and navigate to:
```
http://127.0.0.1:8000
```
This launches the split-screen UI!

---

## 💬 Conversational Scenario Walkthrough

Use the following suggestions to test the application in the web UI:

1. **Happy Path (Approval & Stock Deduction)**:
   - Ask: *"I want to order 2 Veg Burgers and 1 Coca-Cola."*
   - The bot checks stock and replies that the order is pending manager approval.
   - On the right panel, see the order pop up in the **Manager HITL Deck**.
   - Type a note (optional) and click **Approve & Cook**.
   - Notice the status updates to `APPROVED` and the stock counts for Veg Burger and Coca-Cola decrement immediately.

2. **Infeasible Path (Stock Limit Blocked)**:
   - Ask: *"Can I order 10 Mango Shakes?"*
   - Since only 5 Mango Shakes are in stock, the bot will immediately block the order: *"INFEASIBLE: Only 5 Mango Shakes left in stock"* (no manager approval is requested).

3. **Modification & Re-Approval (Stock Restoration)**:
   - Place an order: *"I want 1 Pepperoni Pizza."*
   - Approve it in the Manager Deck (stock of Pepperoni Pizza drops from 8 to 7).
   - In the chat, ask: *"Please modify my order #1 (or whichever ID was assigned) to have 2 Pepperoni Pizzas."*
   - Notice that during modification:
     - The stock of the original Pepperoni Pizza is restored (back to 8).
     - Feasibility check verifies if 2 Pepperoni Pizzas can be ordered (yes, 2 <= 8).
     - The order resets to `PENDING_APPROVAL`.
   - Click **Approve** again in the manager section. The stock drops from 8 to 6.

4. **Rejection Path**:
   - Ask: *"I want 1 Margherita Pizza."*
   - In the Manager Deck, click **Reject** (write a note like *"Kitchen closed"*).
   - The status updates to `REJECTED`, and stock remains untouched.
