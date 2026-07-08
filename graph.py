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
from db import get_connection

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

# --- Tools List Definition ---
tools = [
    check_item_availability,
    check_order_feasibility,
    create_order,
    get_order_status,
    modify_order,
    update_order_status,
    cancel_order
]

# --- 3. Initialize Groq Model ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("CRITICAL: GROQ_API_KEY not found in .env file!")
    model_with_tools = None
else:
    try:
        primary_model = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0,
            api_key=GROQ_API_KEY
        )
        fallback_model = ChatGroq(
            model="llama-3.1-8b-instant",
            temperature=0,
            api_key=GROQ_API_KEY
        )
        primary_with_tools = primary_model.bind_tools(tools)
        fallback_with_tools = fallback_model.bind_tools(tools)
        model_with_tools = primary_with_tools.with_fallbacks([fallback_with_tools])
        print("Groq Llama model with tools (and llama-3.1-8b fallback) initialized successfully!")
    except Exception as e:
        print(f"Groq initialization failed: {e}")
        model_with_tools = None

def get_clarification_prompt(user_message: str) -> Optional[str]:
    """Return a clarification question for generic menu requests like 'pizza' or 'burger'."""
    if not user_message or not isinstance(user_message, str):
        return None

    message = user_message.strip().lower()
    if not message:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM menu WHERE is_active = 1")
    menu_items = [row[0] for row in cursor.fetchall()]
    conn.close()

    for item in menu_items:
        if item.lower() in message:
            return None

    category_aliases = {
        "pizza": ["pizza"],
        "burger": ["burger"],
        "shake": ["shake"],
        "fries": ["fries"],
        "drink": ["drink", "coke", "cola", "soda"],
        "food": ["food", "meal"],
        "sandwich": ["sandwich"],
    }

    matched_categories = []
    for category, aliases in category_aliases.items():
        if any(alias in message for alias in aliases):
            matched_categories.append(category)

    if not matched_categories:
        return None

    clarification_parts = []
    for category in matched_categories:
        relevant_items = [item for item in menu_items if category.lower() in item.lower()]
        if not relevant_items:
            continue

        options = ", ".join(relevant_items)
        if category == "pizza":
            clarification_parts.append(
                f"Which pizza flavor/type would you like? We currently have: {options}. Please tell me the exact flavor and quantity."
            )
        elif category == "drink":
            clarification_parts.append(
                f"Which drink would you like? We currently have: {options}. Please tell me the exact drink and quantity."
            )
        else:
            clarification_parts.append(
                f"Which {category} would you like? We currently have: {options}. Please tell me the exact item and quantity."
            )

    if not clarification_parts:
        return None

    return "I can help with that. " + " ".join(clarification_parts)

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
    - If the customer's request is generic or ambiguous (for example: 'pizza', 'burger', 'drink'), do NOT create an order yet. Ask a clarification question first and offer the relevant menu options.
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

    latest_user_message = None
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            latest_user_message = message.content
            break

    if latest_user_message:
        clarification_prompt = get_clarification_prompt(latest_user_message)
        if clarification_prompt:
            return {"messages": [AIMessage(content=clarification_prompt)]}
    
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
                            
                    if tool_name == "cancel_order":
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
    
    # Check if the resume value is a manager decision
    if isinstance(decision_data, dict) and "decision" in decision_data:
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
    else:
        # The interrupt was resumed by a customer chat message, not a manager decision.
        # We route back to the agent without rejecting the order.
        return {
            "pending_approval": True
        }

# --- 9. Routing Functions ---
def should_continue(state: AgentState) -> Literal["tools_node", "manager_review_node", END]:
    messages = state['messages']
    if messages and hasattr(messages[-1], 'tool_calls') and messages[-1].tool_calls:
        return "tools_node"
    # If the order is still pending approval, route back to manager_review_node to interrupt/pause again.
    if state.get('pending_approval', False):
        return "manager_review_node"
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
        "manager_review_node": "manager_review_node",
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