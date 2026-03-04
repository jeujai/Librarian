/**
 * Enhanced WebSocket connection manager for real-time chat communication
 * Supports typing indicators, message routing, and advanced session management
 */

class WebSocketManager {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.isConnecting = false;
        this.messageQueue = [];
        this.eventHandlers = new Map();
        this.sessionInfo = null;
        this.typingTimer = null;
        this.heartbeatInterval = null;

        // Enhanced features
        this.features = {
            typing_indicators: false,
            message_routing: false,
            multi_session: false,
            conversation_memory: false
        };

        // Bind methods
        this.connect = this.connect.bind(this);
        this.disconnect = this.disconnect.bind(this);
        this.send = this.send.bind(this);
        this.sendTypingStart = this.sendTypingStart.bind(this);
        this.sendTypingStop = this.sendTypingStop.bind(this);
        this.requestSessionInfo = this.requestSessionInfo.bind(this);
        this.clearHistory = this.clearHistory.bind(this);
        this.getSuggestions = this.getSuggestions.bind(this);
        this.onOpen = this.onOpen.bind(this);
        this.onMessage = this.onMessage.bind(this);
        this.onClose = this.onClose.bind(this);
        this.onError = this.onError.bind(this);
    }

    /**
     * Connect to WebSocket server with enhanced features
     */
    connect() {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            return;
        }

        this.isConnecting = true;
        this.updateConnectionStatus('connecting', 'Connecting to enhanced chat...');

        try {
            // Determine WebSocket URL - use the inline chat endpoint from main.py
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/chat`;

            this.ws = new WebSocket(wsUrl);

            // Set up event listeners
            this.ws.addEventListener('open', this.onOpen);
            this.ws.addEventListener('message', this.onMessage);
            this.ws.addEventListener('close', this.onClose);
            this.ws.addEventListener('error', this.onError);

        } catch (error) {
            console.error('Failed to create enhanced WebSocket connection:', error);
            this.isConnecting = false;
            this.updateConnectionStatus('disconnected', 'Enhanced connection failed');
            this.scheduleReconnect();
        }
    }

    /**
     * Disconnect from WebSocket server with cleanup
     */
    disconnect() {
        this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnection

        // Clear timers
        if (this.typingTimer) {
            clearTimeout(this.typingTimer);
            this.typingTimer = null;
        }

        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }

        if (this.ws) {
            this.ws.removeEventListener('open', this.onOpen);
            this.ws.removeEventListener('message', this.onMessage);
            this.ws.removeEventListener('close', this.onClose);
            this.ws.removeEventListener('error', this.onError);

            if (this.ws.readyState === WebSocket.OPEN) {
                this.ws.close();
            }

            this.ws = null;
        }

        this.isConnecting = false;
        this.sessionInfo = null;
        this.updateConnectionStatus('disconnected', 'Disconnected');
    }

    /**
     * Send message through WebSocket with enhanced routing
     */
    send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            try {
                // Ensure message has proper type
                if (typeof message === 'string') {
                    message = { type: 'user_message', content: message };
                }

                this.ws.send(JSON.stringify(message));
                return true;
            } catch (error) {
                console.error('Failed to send message:', error);
                return false;
            }
        } else {
            // Queue message for when connection is restored
            this.messageQueue.push(message);
            console.warn('WebSocket not connected, message queued');
            return false;
        }
    }

    /**
     * Send typing start indicator
     */
    sendTypingStart() {
        if (this.features.typing_indicators) {
            this.send({ type: 'typing_start' });
        }
    }

    /**
     * Send typing stop indicator
     */
    sendTypingStop() {
        if (this.features.typing_indicators) {
            this.send({ type: 'typing_stop' });
        }
    }

    /**
     * Request session information
     */
    requestSessionInfo() {
        this.send({ type: 'session_info' });
    }

    /**
     * Clear conversation history
     */
    clearHistory() {
        this.send({ type: 'clear_history' });
    }

    /**
     * Get conversation suggestions
     */
    getSuggestions() {
        this.send({ type: 'get_suggestions' });
    }

    /**
     * Set conversation context
     */
    setContext(context) {
        this.send({ type: 'set_context', context: context });
    }

    /**
     * Send heartbeat/ping
     */
    sendHeartbeat() {
        this.send({ type: 'heartbeat' });
    }

    /**
     * Add event handler
     */
    on(event, handler) {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, []);
        }
        this.eventHandlers.get(event).push(handler);
    }

    /**
     * Remove event handler
     */
    off(event, handler) {
        if (this.eventHandlers.has(event)) {
            const handlers = this.eventHandlers.get(event);
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }
    }

    /**
     * Emit event to handlers
     */
    emit(event, data) {
        if (this.eventHandlers.has(event)) {
            this.eventHandlers.get(event).forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`Error in event handler for ${event}:`, error);
                }
            });
        }
    }

    /**
     * Handle WebSocket open event with enhanced features
     */
    onOpen(event) {
        console.log('Enhanced WebSocket connected');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.updateConnectionStatus('connected', 'Enhanced chat connected');

        // Start heartbeat
        this.heartbeatInterval = setInterval(() => {
            this.sendHeartbeat();
        }, 30000); // Every 30 seconds

        // Send queued messages
        while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            this.send(message);
        }

        // Request session info to get features
        setTimeout(() => {
            this.requestSessionInfo();
        }, 1000);

        this.emit('connected', event);
    }

    /**
     * Handle WebSocket message event with enhanced routing
     */
    onMessage(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('Received enhanced message:', data);

            // Handle enhanced message types
            switch (data.type) {
                case 'session_started':
                    this.sessionInfo = data;
                    this.features = data.features || {};
                    this.updateConnectionStatus('connected', 'Enhanced features enabled');
                    break;

                case 'session_info':
                    this.sessionInfo = data.data;
                    console.log('Session info updated:', this.sessionInfo);
                    break;

                case 'typing_indicator':
                    this.emit('typing_indicator', data);
                    break;

                case 'suggestions':
                    this.emit('suggestions', data.suggestions);
                    break;

                case 'history_cleared':
                    this.emit('history_cleared', data);
                    break;

                case 'context_set':
                    this.emit('context_set', data);
                    break;

                case 'heartbeat_response':
                    // Heartbeat acknowledged
                    break;

                default:
                    // Handle standard message types
                    break;
            }

            // Emit specific event based on message type
            if (data.type) {
                this.emit(data.type, data);
            }

            // Always emit generic message event
            this.emit('message', data);

        } catch (error) {
            console.error('Failed to parse enhanced WebSocket message:', error);
        }
    }

    /**
     * Handle WebSocket close event with enhanced cleanup
     */
    onClose(event) {
        console.log('Enhanced WebSocket disconnected:', event.code, event.reason);
        this.isConnecting = false;
        this.ws = null;
        this.sessionInfo = null;

        // Clear timers
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }

        if (event.code !== 1000) { // Not a normal closure
            this.updateConnectionStatus('disconnected', 'Enhanced connection lost');
            this.scheduleReconnect();
        } else {
            this.updateConnectionStatus('disconnected', 'Disconnected');
        }

        this.emit('disconnected', event);
    }

    /**
     * Handle WebSocket error event
     */
    onError(event) {
        console.error('WebSocket error:', event);
        this.emit('error', event);
    }

    /**
     * Schedule reconnection attempt
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('Max reconnection attempts reached');
            this.updateConnectionStatus('disconnected', 'Connection failed');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff

        console.log(`Scheduling reconnection attempt ${this.reconnectAttempts} in ${delay}ms`);
        this.updateConnectionStatus('connecting', `Reconnecting in ${Math.ceil(delay / 1000)}s...`);

        setTimeout(() => {
            if (this.reconnectAttempts <= this.maxReconnectAttempts) {
                this.connect();
            }
        }, delay);
    }

    /**
     * Update connection status in UI
     */
    updateConnectionStatus(status, text) {
        const statusIndicator = document.getElementById('statusIndicator');
        const statusText = document.getElementById('statusText');

        if (statusIndicator && statusText) {
            statusIndicator.className = `status-indicator ${status}`;
            statusText.textContent = text;
        }

        this.emit('statusChange', { status, text });
    }

    /**
     * Get current connection state
     */
    getState() {
        if (!this.ws) return 'disconnected';

        switch (this.ws.readyState) {
            case WebSocket.CONNECTING:
                return 'connecting';
            case WebSocket.OPEN:
                return 'connected';
            case WebSocket.CLOSING:
                return 'disconnecting';
            case WebSocket.CLOSED:
                return 'disconnected';
            default:
                return 'unknown';
        }
    }

    /**
     * Check if WebSocket is connected
     */
    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }

    /**
     * Get enhanced session information
     */
    getSessionInfo() {
        return this.sessionInfo;
    }

    /**
     * Get available features
     */
    getFeatures() {
        return this.features;
    }

    /**
     * Check if specific feature is enabled
     */
    hasFeature(feature) {
        return this.features[feature] === true;
    }
}

// Export for use in other modules
window.WebSocketManager = WebSocketManager;