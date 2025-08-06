// MemoScan v2 Client-Side Application Logic

// Global variables
let socket = null;
let csrfToken = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY_BASE = 1000; // 1 second base delay

// Initialize CSRF token
async function initializeCsrf() {
    try {
        const response = await fetch('/csrf-token');
        const data = await response.json();
        csrfToken = data.csrf_token;
        console.log('CSRF token initialized');
    } catch (error) {
        console.error('Failed to get CSRF token:', error);
    }
}

// WebSocket connection management
function connectWebSocket() {
    if (socket && socket.connected) {
        return;
    }
    
    socket = io({
        reconnection: true,
        reconnectionAttempts: MAX_RECONNECT_ATTEMPTS,
        reconnectionDelay: RECONNECT_DELAY_BASE,
        reconnectionDelayMax: 10000,
        timeout: 20000
    });
    
    socket.on('connect', () => {
        console.log('WebSocket connected');
        reconnectAttempts = 0;
        showStatus('Connected to server', 'success');
        
        // Re-enable scan button
        const scanButton = document.querySelector('button[onclick*="startScan"]');
        if (scanButton) {
            scanButton.disabled = false;
        }
    });
    
    socket.on('disconnect', (reason) => {
        console.log('WebSocket disconnected:', reason);
        showStatus('Disconnected from server. Attempting to reconnect...', 'warning');
        
        // Disable scan button while disconnected
        const scanButton = document.querySelector('button[onclick*="startScan"]');
        if (scanButton) {
            scanButton.disabled = true;
        }
    });
    
    socket.on('connect_error', (error) => {
        console.error('Connection error:', error);
        reconnectAttempts++;
        
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            showStatus('Failed to connect to server. Please refresh the page.', 'error');
        } else {
            const delay = Math.min(RECONNECT_DELAY_BASE * Math.pow(2, reconnectAttempts), 10000);
            showStatus(`Connection failed. Retrying in ${delay/1000}s... (Attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`, 'warning');
        }
    });
    
    socket.on('reconnect', (attemptNumber) => {
        console.log('Reconnected after', attemptNumber, 'attempts');
        showStatus('Reconnected to server', 'success');
    });
    
    socket.on('reconnect_failed', () => {
        console.error('Failed to reconnect after maximum attempts');
        showStatus('Failed to reconnect. Please refresh the page.', 'error');
    });
    
    // Handle scan updates
    socket.on('scan_update', handleScanUpdate);
}

// Show status messages
function showStatus(message, type = 'info') {
    // Look for existing status element or create one
    let statusEl = document.getElementById('connection-status');
    if (!statusEl) {
        statusEl = document.createElement('div');
        statusEl.id = 'connection-status';
        statusEl.style.cssText = `
            position: fixed;
            top: 10px;
            right: 10px;
            padding: 10px 20px;
            border-radius: 5px;
            z-index: 1000;
            transition: opacity 0.3s;
        `;
        document.body.appendChild(statusEl);
    }
    
    // Set colors based on type
    const colors = {
        success: '#28a745',
        warning: '#ffc107',
        error: '#dc3545',
        info: '#17a2b8'
    };
    
    statusEl.style.backgroundColor = colors[type] || colors.info;
    statusEl.style.color = type === 'warning' ? '#000' : '#fff';
    statusEl.textContent = message;
    statusEl.style.opacity = '1';
    
    // Auto-hide success messages
    if (type === 'success') {
        setTimeout(() => {
            statusEl.style.opacity = '0';
        }, 3000);
    }
}

// Enhanced feedback submission with CSRF
async function submitFeedback(analysisId, keyName, feedbackType, aiScore, userScore = null, confidence = null) {
    if (!csrfToken) {
        await initializeCsrf();
    }
    
    const feedbackData = {
        analysis_id: analysisId,
        key_name: keyName,
        feedback_type: feedbackType,
        ai_score: aiScore,
        user_score: userScore,
        confidence: confidence,
        csrf_token: csrfToken
    };
    
    try {
        const response = await fetch('/feedback', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            body: JSON.stringify(feedbackData)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        console.log('Feedback submitted successfully:', result);
        
        // Show success message
        showFeedbackSuccess(keyName);
        
    } catch (error) {
        console.error('Error submitting feedback:', error);
        showStatus('Failed to submit feedback. Please try again.', 'error');
    }
}

// Show feedback success message
function showFeedbackSuccess(keyName) {
    const feedbackButtons = document.querySelectorAll(`[data-key="${keyName}"] .feedback-button`);
    feedbackButtons.forEach(button => {
        const originalText = button.textContent;
        button.textContent = '✓ Feedback sent';
        button.style.backgroundColor = '#28a745';
        
        setTimeout(() => {
            button.textContent = originalText;
            button.style.backgroundColor = '';
        }, 2000);
    });
}

// Load user history
async function loadUserHistory() {
    try {
        const response = await fetch('/user/history');
        const data = await response.json();
        
        // Update UI with scan count
        const scanCountEl = document.getElementById('scan-count');
        if (scanCountEl) {
            scanCountEl.textContent = `Scans today: ${data.last_24h}/${MAX_SCANS_PER_USER} (${data.remaining_24h} remaining)`;
        }
        
        return data;
    } catch (error) {
        console.error('Failed to load user history:', error);
    }
}

// Enhanced scan start with better error handling
async function startScan() {
    const urlInput = document.getElementById('url-input');
    const url = urlInput.value.trim();
    
    if (!url) {
        showStatus('Please enter a URL', 'warning');
        return;
    }
    
    if (!socket || !socket.connected) {
        showStatus('Not connected to server. Please wait...', 'error');
        connectWebSocket();
        return;
    }
    
    // Check user limits
    const history = await loadUserHistory();
    if (history && history.remaining_24h <= 0) {
        showStatus('Daily scan limit reached. Please try again tomorrow.', 'warning');
        return;
    }
    
    // Emit scan request
    socket.emit('start_scan', { url: url });
    
    // Update UI
    document.getElementById('scan-button').disabled = true;
    showStatus('Starting scan...', 'info');
}

// Handle scan updates
function handleScanUpdate(data) {
    console.log('Scan update:', data);
    
    // Update UI based on update type
    switch (data.type) {
        case 'error':
            showStatus(`Error: ${data.message}`, 'error');
            document.getElementById('scan-button').disabled = false;
            break;
        case 'complete':
            showStatus('Scan completed successfully!', 'success');
            document.getElementById('scan-button').disabled = false;
            loadUserHistory(); // Update scan count
            break;
        // Handle other update types...
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await initializeCsrf();
    connectWebSocket();
    loadUserHistory();
    
    // Add event listeners
    const urlInput = document.getElementById('url-input');
    if (urlInput) {
        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                startScan();
            }
        });
    }
    
    // Periodically check connection status
    setInterval(() => {
        if (!socket || !socket.connected) {
            connectWebSocket();
        }
    }, 30000); // Check every 30 seconds
});

// Export for use in HTML
window.startScan = startScan;
window.submitFeedback = submitFeedback;
window.loadUserHistory = loadUserHistory;