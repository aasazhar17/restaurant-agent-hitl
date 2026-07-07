import json
import re
import traceback
from typing import Literal, Optional
from langgraph.graph import StateGraph, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_core.runnables import RunnableConfig
from dotenv import load_dotenv
import os

# Load environment variables (API key)
load_dotenv()

# --- 1. Import our tools from tools.py ---
from tools import (
    check_item_availability,
    check_order_feasibility,
    create_order,
    get_order_status,
    modify_order,
    update_order_status,
    cancel_order
)

# --- 2. Define Extended State ---
class AgentState(MessagesState):
    current_order_id: Optional[int] = None
    pending_approval: bool = False

# --- 3. Initialize Groq Model ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("CRITICAL: GROQ_API_KEY not found in .env file!")
    model = None
else:
    try:
        model = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0,
            api_key=GROQ_API_KEY
        )
        print("Groq Llama 3.3 70B initialized successfully!")
    except Exception as e:
        print(f"Groq initialization failed: {e}")
        model = None

# --- 4. Define Tools List ---
tools = [
    check_item_availability,
    check_order_feasibility,
    create_order,
    get_order_status,
    modify_order,
    update_order_status,
    cancel_order
]

# Bind tools to the model
if model:
    model_with_tools = model.bind_tools(tools)
else:
    model_with_tools = None

# --- 5. System Prompt to guide the Agent ---
SYSTEM_PROMPT = SystemMessage(
    content="""You are a professional restaurant ordering assistant.
    RULES & AVAILABLE TOOLS:
    1. check_item_availability(item_name, qty): Use this to check if a single item is available.
    2. check_order_feasibility(items_json, order_id): Use this to check if the entire cart/combination of items is feasible against live stock. Always call this BEFORE creating or modifying an order. For modifying an order, make sure to pass the optional `order_id` so we can account for currently reserved items.
    3. create_order(items_json): Call this to place a new order. It automatically retrieves the thread context. No thread_id argument is needed.
    4. modify_order(order_id, new_items_json): Call this to modify items in an existing order.
    5. get_order_status(order_id): Call this when the user asks for status.
    6. update_order_status(order_id, decision, note): ONLY for executing approval. (You rarely call this directly unless confirming decision outcome).
    7. cancel_order(order_id): Call this when the user requests to cancel their order.

    IMPORTANT RULES:
    - You must ALWAYS call check_order_feasibility BEFORE calling create_order or modify_order.
    - items_json must be a JSON string of a list. Example: '[{"name": "Veg Burger", "qty": 2}]'
    - Never invent order IDs. If the customer asks for status or modification or cancellation, ask them for the order ID if they haven't provided it, or look it up from the conversation context.
    - Confirm all successfully placed, modified, or cancelled orders with their IDs.
    - If items are out of stock, explain politely and offer alternatives.
    - Do chit-chat politely if needed, but guide the user to complete their order.
    """
)

# --- 6. Agent Node (LLM Call) ---
def agent_node(state: AgentState, config: RunnableConfig):
    if model_with_tools is None:
        return {"messages": [AIMessage(content="❌ System Error: LLM not configured. Please check API key.")]}

    messages = state['messages']
    
    # Ensure System Prompt is always at the beginning
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SYSTEM_PROMPT] + list(messages)
    
    try:
        response = model_with_tools.invoke(messages)
        return {"messages": [response]}
    except Exception as e:
        print("=" * 60)
        print("=== LLM ERROR OCCURRED ===")
        traceback.print_exc()
        print("=" * 60)
        error_msg = f"Sorry, I encountered a technical error ({type(e).__name__}). Please try again."
        return {"messages": [AIMessage(content=error_msg)]}

# --- 7. Tools Node (Executes tool calls and updates state) ---
def tools_node(state: AgentState, config: RunnableConfig):
    messages = state['messages']
    last_message = messages[-1]
    tool_calls = getattr(last_message, 'tool_calls', [])
    
    if not tool_calls:
        return {"messages": []}
    
    outputs = []
    new_order_id = state.get('current_order_id')
    pending_flag = state.get('pending_approval', False)
    
    for tool_call in tool_calls:
        tool_name = tool_call['name']
        tool_args = tool_call['args']
        
        for t in tools:
            if t.name == tool_name:
                try:
                    # Pass the config to the tool in case it requires it
                    result = t.invoke(tool_args, config=config)
                    result_str = str(result)
                    
                    # --- State Management: Extract order ID & set pending flag ---
                    if tool_name in ["create_order", "modify_order"]:
                        # Extract order ID from results (e.g. "Order created with ID: 123" or "Order #123 modified")
                        match = re.search(r"Order (?:created with ID:|#)\s*(\d+)", result_str)
                        if match:
                            new_order_id = int(match.group(1))
                            pending_flag = True  # Resets to PENDING_APPROVAL
                        else:
                            # Fallback extraction
                            nums = re.findall(r'\d+', result_str)
                            if nums:
                                new_order_id = int(nums[0])
                                pending_flag = True
                    
                    if tool_name == "update_order_status":
                        if "APPROVED" in result_str or "REJECTED" in result_str:
                            pending_flag = False
                    
                    outputs.append(ToolMessage(content=result_str, tool_call_id=tool_call['id']))
                    break
                except Exception as e:
                    error_msg = f"Tool {tool_name} failed: {str(e)}"
                    outputs.append(ToolMessage(content=f"Error: {error_msg}", tool_call_id=tool_call['id']))
                    print(f"Tool Error: {error_msg}")
    
    return {
        "messages": outputs,
        "current_order_id": new_order_id,
        "pending_approval": pending_flag
    }

# --- 8. Manager Review Node (HITL Interrupt) ---
def manager_review_node(state: AgentState):
    order_id = state.get('current_order_id')
    if not order_id:
        return {
            "messages": [AIMessage(content="System Error: Order ID missing. Please start over.")],
            "pending_approval": False
        }
    
    from langgraph.types import interrupt
    interrupt_value = {
        "order_id": order_id,
        "message": f"Manager, please approve or reject Order #{order_id}."
    }
    
    # Pause graph execution and await Command(resume=...)
    # IMPORTANT: Do not wrap interrupt() in a try-except block because LangGraph uses a special exception to signal interrupt.
    decision_data = interrupt(interrupt_value)
    
    decision = decision_data.get("decision", "reject")
    note = decision_data.get("note", "")
    
    # Call the update_order_status tool to apply the decision
    try:
        result = update_order_status.invoke({
            "order_id": order_id,
            "decision": decision,
            "note": note
        })
    except Exception as e:
        result = f"Failed to update order: {str(e)}"
    
    return {
        "messages": [AIMessage(content=f"Manager decision processed: {decision.upper()}. Details: {result}")],
        "pending_approval": False
    }

# --- 9. Routing Functions ---
def should_continue(state: AgentState) -> Literal["tools_node", END]:
    messages = state['messages']
    if messages and hasattr(messages[-1], 'tool_calls') and messages[-1].tool_calls:
        return "tools_node"
    return END

def after_tools_router(state: AgentState) -> Literal["manager_review_node", "agent", END]:
    if state.get('pending_approval', False):
        return "manager_review_node"
    
    # Check if there is a ToolMessage that needs agent response
    for msg in reversed(state['messages']):
        if isinstance(msg, ToolMessage):
            return "agent"
            
    return END

# --- 10. Build the StateGraph ---
builder = StateGraph(AgentState)

# Add nodes
builder.add_node("agent", agent_node)
builder.add_node("tools_node", tools_node)
builder.add_node("manager_review_node", manager_review_node)

# Entry point
builder.set_entry_point("agent")

# Conditional edges
builder.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools_node": "tools_node",
        END: END
    }
)

builder.add_conditional_edges(
    "tools_node",
    after_tools_router,
    {
        "manager_review_node": "manager_review_node",
        "agent": "agent",
        END: END
    }
)

# Go back to agent to report outcome after approval resume
builder.add_edge("manager_review_node", "agent")

# --- 11. Compile with Checkpointer ---
memory = MemorySaver()
graph = builder.compile(checkpointer=memory)

def get_graph_diagram():
    return graph.get_graph().draw_mermaid()

if __name__ == "__main__":
    print("Graph compiled successfully with MemorySaver!")