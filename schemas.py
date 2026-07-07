# schemas.py
from pydantic import BaseModel
from typing import List, Optional

class ItemInput(BaseModel):
    name: str
    qty: int

class OrderCreateRequest(BaseModel):
    thread_id: str
    items: List[ItemInput]

class ChatRequest(BaseModel):
    thread_id: str
    message: str

class ApproveRequest(BaseModel):
    order_id: int
    decision: str  # "approve" or "reject"
    note: Optional[str] = ""

class OrderStatusResponse(BaseModel):
    order_id: int
    status: str
    items: List[dict]
    manager_note: Optional[str]