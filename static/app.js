// static/app.js

let currentThreadId = 'cust_session_1';
let isVisualizerOpen = false;

// DOM Elements
const chatArea = document.getElementById('chatArea');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const threadIdSelect = document.getElementById('threadIdSelect');
const resetDbBtn = document.getElementById('resetDbBtn');
const inventoryBody = document.getElementById('inventoryBody');
const hitlQueue = document.getElementById('hitlQueue');
const ordersList = document.getElementById('ordersList');
const pendingCount = document.getElementById('pendingCount');
const refreshMenuBtn = document.getElementById('refreshMenuBtn');
const refreshOrdersBtn = document.getElementById('refreshOrdersBtn');
const visualizerHeader = document.getElementById('visualizerHeader');
const visualizerContent = document.getElementById('visualizerContent');
const visualizerToggleIcon = document.getElementById('visualizerToggleIcon');
const mermaidDiagram = document.getElementById('mermaidDiagram');

// Initialize Mermaid
if (window.mermaid) {
    mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        securityLevel: 'loose',
        flowchart: { useMaxWidth: true, htmlLabels: true }
    });
}

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
    currentThreadId = threadIdSelect.value;
    refreshMenu();
    refreshOrders();

    // Event Listeners
    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    threadIdSelect.addEventListener('change', (e) => {
        currentThreadId = e.target.value;
        // Clear chat area and insert welcome message for new thread context
        chatArea.innerHTML = `
            <div class="message bot-message">
                <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
                <div class="msg-content-wrapper">
                    <div class="msg-sender">GourmetBot</div>
                    <div class="msg-text">Switched to session <strong>${currentThreadId}</strong>. I have loaded this thread's conversational history. How can I help you?</div>
                </div>
            </div>
        `;
    });

    resetDbBtn.addEventListener('click', resetSystem);
    refreshMenuBtn.addEventListener('click', refreshMenu);
    refreshOrdersBtn.addEventListener('click', refreshOrders);
    
    // Toggle Flow Visualizer
    visualizerHeader.addEventListener('click', toggleVisualizer);
});

// Toggle LangGraph Visualizer
function toggleVisualizer() {
    isVisualizerOpen = !isVisualizerOpen;
    if (isVisualizerOpen) {
        visualizerContent.style.display = 'block';
        visualizerToggleIcon.textContent = 'Hide';
        visualizerToggleIcon.className = 'badge badge-approved';
        renderDiagram();
    } else {
        visualizerContent.style.display = 'none';
        visualizerToggleIcon.textContent = 'Show';
        visualizerToggleIcon.className = 'badge badge-draft';
    }
}

// Render Mermaid Diagram
async function renderDiagram() {
    if (!window.mermaid) return;
    try {
        const response = await fetch('/diagram');
        const data = await response.json();
        
        if (data.mermaid) {
            // Clear previous rendering states
            mermaidDiagram.removeAttribute('data-processed');
            mermaidDiagram.textContent = data.mermaid;
            
            // Re-render
            await mermaid.parse(data.mermaid);
            await mermaid.run({
                nodes: [mermaidDiagram]
            });
        }
    } catch (err) {
        console.error("Error rendering diagram:", err);
        mermaidDiagram.innerHTML = `<span style="color: var(--danger)">Failed to render flow visualizer diagram.</span>`;
    }
}

// Apply quick prompt chips
function applyQuickPrompt(text) {
    userInput.value = text;
    userInput.focus();
}

// Format prices
function formatPrice(amount) {
    return `₹${amount}`;
}

// Refresh Menu Stock Table
async function refreshMenu() {
    try {
        const response = await fetch('/menu');
        const data = await response.json();
        const menu = data.menu;

        inventoryBody.innerHTML = '';
        if (!menu || menu.length === 0) {
            inventoryBody.innerHTML = '<tr><td colspan="4" class="text-center">Menu is empty.</td></tr>';
            return;
        }

        menu.forEach(item => {
            let stockBadge = '';
            if (item.available_qty > 5) {
                stockBadge = `<span class="stock-badge stock-normal">${item.available_qty} In Stock</span>`;
            } else if (item.available_qty > 0) {
                stockBadge = `<span class="stock-badge stock-low" style="box-shadow: 0 0 10px rgba(245, 158, 11, 0.4);">${item.available_qty} Low Stock</span>`;
            } else {
                stockBadge = `<span class="stock-badge stock-empty" style="box-shadow: 0 0 10px rgba(239, 68, 68, 0.4);">Out of Stock</span>`;
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${item.name}</strong></td>
                <td>${formatPrice(item.price)}</td>
                <td>${stockBadge}</td>
                <td><span style="color: ${item.available_qty > 0 ? 'var(--success)' : 'var(--danger)'}; font-weight: 600;">
                    ${item.available_qty > 0 ? 'Active' : 'Inactive'}
                </span></td>
            `;
            inventoryBody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error refreshing menu:", err);
    }
}

// Refresh Orders and HITL queue
async function refreshOrders() {
    try {
        const response = await fetch('/orders');
        const data = await response.json();
        const orders = data.orders;

        // Render Lifecycle Tracker
        ordersList.innerHTML = '';
        if (!orders || orders.length === 0) {
            ordersList.innerHTML = `
                <div class="no-pending">
                    <i class="fa-solid fa-receipt"></i>
                    <p>No orders found in the database. Place one in the chat!</p>
                </div>
            `;
        } else {
            orders.forEach(order => {
                const card = document.createElement('div');
                card.className = 'order-tracker-card';
                
                const itemsStr = order.items.map(i => `${i.name} (x${i.qty})`).join(', ');
                const statusBadge = getStatusBadge(order.status);
                
                let actionBtns = '';
                if (order.status === 'APPROVED') {
                    actionBtns += `<button class="btn btn-small btn-success" onclick="deliverOrder(${order.order_id})" style="margin-top: 5px;">
                        <i class="fa-solid fa-truck"></i> Mark Delivered
                    </button> `;
                }
                
                if (order.status === 'APPROVED' || order.status === 'PENDING_APPROVAL') {
                    actionBtns += `<button class="btn btn-small btn-danger" onclick="cancelOrder(${order.order_id})" style="margin-top: 5px; background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.3);">
                        <i class="fa-solid fa-ban"></i> Cancel Order
                    </button>`;
                }

                let noteHtml = order.manager_note ? `<div class="order-note"><i class="fa-solid fa-quote-left"></i> Note: ${order.manager_note}</div>` : '';

                card.innerHTML = `
                    <div class="order-tracker-row">
                        <span class="order-number">Order #${order.order_id}</span>
                        ${statusBadge}
                    </div>
                    <div class="order-items-desc">${itemsStr}</div>
                    <div class="order-tracker-row" style="margin-top: 5px;">
                        <span class="order-time"><i class="fa-solid fa-clock"></i> ${new Date(order.created_at).toLocaleString()}</span>
                        <span class="order-time" style="font-weight: 500; color: #a855f7;">Session: ${order.customer_thread_id}</span>
                    </div>
                    ${noteHtml}
                    ${actionBtns ? `<div class="hitl-actions" style="margin-top: 8px;">${actionBtns}</div>` : ''}
                `;
                ordersList.appendChild(card);
            });
        }

        // Render Manager HITL Queue
        const pendingOrders = orders ? orders.filter(o => o.status === 'PENDING_APPROVAL') : [];
        pendingCount.textContent = `${pendingOrders.length} Pending`;

        hitlQueue.innerHTML = '';
        if (pendingOrders.length === 0) {
            hitlQueue.innerHTML = `
                <div class="no-pending">
                    <i class="fa-solid fa-check-circle" style="color: var(--success); opacity: 0.8;"></i>
                    <p>No orders pending manager approval at this moment.</p>
                </div>
            `;
        } else {
            pendingOrders.forEach(order => {
                const card = document.createElement('div');
                card.className = 'hitl-card';
                
                // Add checkboxes next to items for partial approvals!
                const listItems = order.items.map(i => `
                    <li style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                        <input type="checkbox" class="hitl-item-check-${order.order_id}" value="${i.name}" checked style="cursor: pointer; width: 16px; height: 16px; accent-color: var(--primary);">
                        <span>${i.name} <strong>x${i.qty}</strong></span>
                    </li>
                `).join('');

                card.innerHTML = `
                    <div class="hitl-card-header">
                        <span class="order-title">Approval Request: Order #${order.order_id}</span>
                        <span class="badge badge-pending">Pending Approval</span>
                    </div>
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 8px;">Session Context: <strong>${order.customer_thread_id}</strong></p>
                    <ul class="hitl-items-list" style="list-style: none; padding-left: 0; margin-bottom: 10px;">
                        ${listItems}
                    </ul>
                    <input type="text" class="hitl-note-input" id="note-${order.order_id}" placeholder="Optional manager note (e.g. 'extra chili sauce added')...">
                    <div class="hitl-actions">
                        <button class="btn btn-danger" onclick="submitDecision(${order.order_id}, 'reject')">
                            <i class="fa-solid fa-times"></i> Reject All
                        </button>
                        <button class="btn btn-success" style="background: var(--success); color:#fff;" onclick="approveOrderDecision(${order.order_id})">
                            <i class="fa-solid fa-check"></i> Process Approval
                        </button>
                    </div>
                `;
                hitlQueue.appendChild(card);
            });
        }

    } catch (err) {
        console.error("Error refreshing orders:", err);
    }
}

// Get Badge Markup based on status
function getStatusBadge(status) {
    switch (status.toUpperCase()) {
        case 'DRAFT': return `<span class="badge badge-draft">Draft</span>`;
        case 'PENDING_APPROVAL': return `<span class="badge badge-pending">Pending</span>`;
        case 'APPROVED': return `<span class="badge badge-approved">Approved (cooking)</span>`;
        case 'REJECTED': return `<span class="badge badge-rejected">Rejected</span>`;
        case 'CANCELLED': return `<span class="badge badge-rejected" style="background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.4); color: var(--danger)">Cancelled</span>`;
        case 'DELIVERED': return `<span class="badge badge-delivered">Delivered</span>`;
        default: return `<span class="badge badge-draft">${status}</span>`;
    }
}

// Send Customer Message
async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    // Add user bubble
    appendMessage('user', text);
    userInput.value = '';

    // Add bot typing indicator
    const typingId = appendTypingIndicator();
    chatArea.scrollTop = chatArea.scrollHeight;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                thread_id: currentThreadId,
                message: text
            })
        });

        const data = await response.json();
        removeTypingIndicator(typingId);

        // Add bot bubble
        appendMessage('bot', data.response);

        // Check if manager is required
        if (data.requires_manager) {
            appendMessage('bot', `<i class="fa-solid fa-circle-exclamation" style="color: var(--warning);"></i> <strong>System Alert:</strong> Your Order #${data.order_id} has been submitted for manager approval. Please wait for the manager to review the stock levels.`);
        }

        // Refresh UI
        refreshMenu();
        refreshOrders();
        if (isVisualizerOpen) renderDiagram();

    } catch (err) {
        removeTypingIndicator(typingId);
        appendMessage('bot', "❌ Error: Failed to communicate with the restaurant backend.");
        console.error(err);
    }
}

// Resolve and submit manager approval (supporting partial approvals!)
async function approveOrderDecision(orderId) {
    const noteInput = document.getElementById(`note-${orderId}`);
    const note = noteInput ? noteInput.value.trim() : '';

    // Retrieve checked items
    const checkboxes = document.querySelectorAll(`.hitl-item-check-${orderId}`);
    const approvedItems = [];
    const allItemsCount = checkboxes.length;
    
    checkboxes.forEach(cb => {
        if (cb.checked) approvedItems.push(cb.value);
    });

    if (approvedItems.length === 0) {
        alert("Cannot approve with 0 items! Please click 'Reject All' instead.");
        return;
    }

    try {
        let response, data;
        
        if (approvedItems.length === allItemsCount) {
            // Full approval
            response = await fetch('/approve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    order_id: orderId,
                    decision: 'approve',
                    note: note
                })
            });
            data = await response.json();
        } else {
            // Partial approval
            response = await fetch('/partial-approve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    order_id: orderId,
                    approved_items: approvedItems,
                    note: note
                })
            });
            data = await response.json();
        }

        // Post results back to conversational context
        appendMessage('bot', `📢 <strong>Manager Decision on Order #${orderId}:</strong> APPROVED. ${data.message || data.result}`);
        
        // Refresh UI
        refreshMenu();
        refreshOrders();
        if (isVisualizerOpen) renderDiagram();
    } catch (err) {
        alert("Error during approval execution.");
        console.error(err);
    }
}

// Submit Manager HITL Decision (Reject)
async function submitDecision(orderId, decision) {
    const noteInput = document.getElementById(`note-${orderId}`);
    const note = noteInput ? noteInput.value.trim() : '';

    try {
        const response = await fetch('/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                order_id: orderId,
                decision: decision,
                note: note
            })
        });
        const data = await response.json();
        
        // Post decision results back in client chat to simulate system updates
        appendMessage('bot', `📢 <strong>Manager Decision on Order #${orderId}:</strong> ${decision.toUpperCase()}. Details: ${data.result}`);
        
        // Refresh UI
        refreshMenu();
        refreshOrders();
        if (isVisualizerOpen) renderDiagram();
    } catch (err) {
        alert("Error rejecting order.");
        console.error(err);
    }
}

// Cancel Order & Restore stock
async function cancelOrder(orderId) {
    if (!confirm(`Are you sure you want to cancel Order #${orderId}? Stock will be restored.`)) return;

    try {
        const response = await fetch('/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order_id: orderId })
        });
        const data = await response.json();
        
        appendMessage('bot', `🚫 <strong>Order #${orderId} Cancelled!</strong> ${data.message}`);
        
        refreshMenu();
        refreshOrders();
        if (isVisualizerOpen) renderDiagram();
    } catch (err) {
        alert("Error cancelling order.");
        console.error(err);
    }
}

// Deliver an Approved Order
async function deliverOrder(orderId) {
    try {
        const response = await fetch('/deliver', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order_id: orderId })
        });
        const data = await response.json();
        
        appendMessage('bot', `📦 <strong>Order #${orderId} Delivered!</strong> Hope the customer enjoys their hot meal.`);
        
        refreshOrders();
        if (isVisualizerOpen) renderDiagram();
    } catch (err) {
        alert("Error delivering order.");
        console.error(err);
    }
}

// Reset Database and UI
async function resetSystem() {
    if (!confirm("Are you sure you want to reset the database menu stock and all order states?")) return;

    try {
        const response = await fetch('/reset', { method: 'POST' });
        const data = await response.json();

        chatArea.innerHTML = `
            <div class="message bot-message">
                <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
                <div class="msg-content-wrapper">
                    <div class="msg-sender">GourmetBot</div>
                    <div class="msg-text">Database reset and seeded successfully! All stocks are restored and orders cleared. Ready for a fresh scenario!</div>
                </div>
            </div>
        `;
        
        refreshMenu();
        refreshOrders();
        if (isVisualizerOpen) renderDiagram();
    } catch (err) {
        alert("Error resetting database.");
        console.error(err);
    }
}

// Append Chat Bubbles
function appendMessage(sender, text) {
    const isBot = sender === 'bot';
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${isBot ? 'bot-message' : 'user-message'}`;

    const avatarHtml = isBot ? '<i class="fa-solid fa-robot"></i>' : '<i class="fa-solid fa-user"></i>';
    const senderName = isBot ? 'GourmetBot' : 'Customer';

    msgDiv.innerHTML = `
        <div class="msg-avatar">${avatarHtml}</div>
        <div class="msg-content-wrapper">
            <div class="msg-sender">${senderName}</div>
            <div class="msg-text">${text}</div>
        </div>
    `;
    chatArea.appendChild(msgDiv);
    chatArea.scrollTop = chatArea.scrollHeight;
}

// Append Typing indicator
function appendTypingIndicator() {
    const id = 'typing_' + Date.now();
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message bot-message';
    msgDiv.id = id;

    msgDiv.innerHTML = `
        <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="msg-content-wrapper">
            <div class="msg-sender">GourmetBot</div>
            <div class="msg-text">
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        </div>
    `;
    chatArea.appendChild(msgDiv);
    chatArea.scrollTop = chatArea.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}
