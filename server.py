# server.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import json
import os
import uuid

# Import schemas and db functions
from schemas import ChatRequest, ApproveRequest
from db import (
    get_connection, 
    init_db, 
    get_order_by_id, 
    create_order_db, 
    get_all_orders_db, 
    reset_db_db,
    deliver_order_db,
    cancel_order_db,
    partial_approve_order_db,
    add_menu_item_db,
    update_menu_item_db
)
from graph import graph, get_graph_diagram
from langgraph.types import Command

app = FastAPI(title="Restaurant Agent API with HITL", version="2.0")
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# Request schemas for new endpoints
class DeliverRequest(BaseModel):
    order_id: int

class CancelRequest(BaseModel):
    order_id: int

class PartialApproveRequest(BaseModel):
    order_id: int
    approved_items: list
    note: Optional[str] = ""

class AddMenuItemRequest(BaseModel):
    name: str
    price: float
    stock: int

class UpdateMenuItemRequest(BaseModel):
    item_id: int
    name: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None

@app.get("/menu")
async def get_menu():
    """Fetch all active menu items."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT item_id, name, price, available_qty FROM menu WHERE is_active = 1")
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"menu": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/menu/add")
async def admin_add_menu_item(request: AddMenuItemRequest):
    """Allow the admin to add a new menu item."""
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Item name is required")
    if request.price < 0 or request.stock < 0:
        raise HTTPException(status_code=400, detail="Price and stock cannot be negative")

    item_id = add_menu_item_db(name, float(request.price), int(request.stock))
    return {"success": True, "item_id": item_id, "message": "Item added successfully"}

@app.post("/admin/menu/update")
async def admin_update_menu_item(request: UpdateMenuItemRequest):
    """Allow the admin to update an existing menu item."""
    if request.name is not None:
        request.name = request.name.strip()
        if not request.name:
            raise HTTPException(status_code=400, detail="Item name cannot be empty")

    if request.price is not None and request.price < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative")
    if request.stock is not None and request.stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")

    success = update_menu_item_db(
        request.item_id,
        name=request.name,
        price=float(request.price) if request.price is not None else None,
        stock=int(request.stock) if request.stock is not None else None,
    )
    if not success:
        raise HTTPException(status_code=400, detail="No valid fields were provided for update")

    return {"success": True, "message": "Item updated successfully"}

@app.get("/orders")
async def get_orders():
    """Fetch all orders for the dashboard."""
    try:
        orders = get_all_orders_db()
        return {"orders": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/summary")
async def get_summary():
    """Return dashboard summary metrics for manager/admin views."""
    try:
        orders = get_all_orders_db()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, available_qty FROM menu WHERE is_active = 1")
        menu_rows = cursor.fetchall()
        conn.close()

        pending_orders = [order for order in orders if order['status'] == 'PENDING_APPROVAL']
        approved_orders = [order for order in orders if order['status'] == 'APPROVED']
        low_stock_items = [
            {"name": row[0], "available_qty": row[1]}
            for row in menu_rows
            if row[1] <= 5
        ]

        return {
            "total_orders": len(orders),
            "pending_orders": len(pending_orders),
            "approved_orders": len(approved_orders),
            "low_stock_count": len(low_stock_items),
            "low_stock_items": low_stock_items,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Main entry point for customer chat.
    Invokes/streams LangGraph and returns the agent response.
    """
    thread_id = request.thread_id
    user_message = request.message

    # Configuration for LangGraph memory thread
    config = {"configurable": {"thread_id": thread_id}}
    input_messages = {"messages": [("user", user_message)]}
    
    try:
        events = []
        # Stream the graph execution
        async for event in graph.astream(input_messages, config=config, stream_mode="values"):
            if "messages" in event:
                last_msg = event["messages"][-1]
                if hasattr(last_msg, "content"):
                    events.append(last_msg.content)
        
        # Check if the graph is paused at an interrupt (manager_review_node)
        state_snapshot = graph.get_state(config)
        next_nodes = state_snapshot.next
        
        if "manager_review_node" in next_nodes:
            # Retrieve the most recent order_id created in this thread
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT order_id FROM orders WHERE customer_thread_id = ? ORDER BY created_at DESC LIMIT 1", 
                (thread_id,)
            )
            row = cursor.fetchone()
            conn.close()
            order_id = row[0] if row else None
            
            final_response = events[-1] if events else "Order sent for manager approval."
            
            return {
                "response": final_response,
                "order_id": order_id,
                "status": "PENDING_APPROVAL",
                "requires_manager": True,
                "message": "Order requires manager approval before cooking."
            }
        else:
            final_response = events[-1] if events else "I couldn't process that. Please try again."
            return {
                "response": final_response,
                "requires_manager": False
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/approve")
async def manager_approve(request: ApproveRequest):
    """
    Resumes the LangGraph interrupt with the manager's decision.
    """
    order = get_order_by_id(request.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    thread_id = order['customer_thread_id']
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        # Resume using Command(resume=...)
        result = await graph.ainvoke(
            Command(resume={"decision": request.decision, "note": request.note}),
            config=config
        )
        final_msg = result["messages"][-1].content if result.get("messages") else "Order processed."
        
        # Reload order to get updated status and items
        updated_order = get_order_by_id(request.order_id)
        
        return {
            "result": final_msg,
            "order_id": request.order_id,
            "status": updated_order["status"] if updated_order else "UNKNOWN"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cancel")
async def cancel_order(request: CancelRequest):
    """Cancel an order and restore stock if approved."""
    success, message = cancel_order_db(request.order_id)
    if success:
        return {"message": message}
    else:
        raise HTTPException(status_code=400, detail=message)

@app.post("/partial-approve")
async def partial_approve(request: PartialApproveRequest):
    """Resumes the LangGraph interrupt with a partial approval decision."""
    order = get_order_by_id(request.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    thread_id = order['customer_thread_id']
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        # 1. Apply partial approval stock deduction in DB first
        success, message = partial_approve_order_db(request.order_id, request.approved_items, request.note)
        if not success:
            raise HTTPException(status_code=400, detail=message)
            
        # 2. Resume the graph with 'approve' and note
        result = await graph.ainvoke(
            Command(resume={"decision": "approve", "note": f"{request.note} (Partial Approval)"}),
            config=config
        )
        final_msg = result["messages"][-1].content if result.get("messages") else "Order processed."
        
        return {
            "result": final_msg,
            "order_id": request.order_id,
            "status": "APPROVED",
            "message": message
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/deliver")
async def deliver_order(request: DeliverRequest):
    """Deliver an approved order."""
    success = deliver_order_db(request.order_id)
    if success:
        return {"message": f"Order #{request.order_id} has been delivered successfully!"}
    else:
        raise HTTPException(status_code=400, detail="Order could not be delivered (must be in APPROVED status).")

@app.post("/reset")
async def reset_database():
    """Resets the DB to seed state."""
    try:
        reset_db_db()
        return {"message": "Database reset and seeded successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/diagram")
async def get_diagram():
    """Returns the LangGraph Mermaid flowchart schema."""
    try:
        mermaid_code = get_graph_diagram()
        return {"mermaid": mermaid_code}
    except Exception as e:
        return {"mermaid": ""}

# Serve static directory (mount frontend files)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def serve_index():
    """Serve the root index page."""
    return FileResponse(STATIC_DIR / "index.html")

@app.on_event("startup")
async def startup_event():
    init_db()
    print("FastAPI Server with HITL & Static Assets is running!")

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)