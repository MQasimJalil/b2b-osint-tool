/**
 * WebSocket Client for Real-Time Updates
 *
 * Handles WebSocket connection, reconnection, and event listening
 */

class WebSocketClient {
  constructor(token) {
    this.token = token;
    this.ws = null;
    this.listeners = {};
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // Start with 1 second
    this.isIntentionalClose = false;
    this.heartbeatInterval = null;
  }

  /**
   * Connect to WebSocket server
   */
  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected');
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = process.env.REACT_APP_WS_URL || 'localhost:8000';
    const wsUrl = `${protocol}//${host}/api/v1/ws?token=${this.token}`;

    console.log('Connecting to WebSocket...');
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.reconnectDelay = 1000;
      this.startHeartbeat();
      this.emit('connected', { status: 'connected' });
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.emit('error', { error });
    };

    this.ws.onclose = (event) => {
      console.log('WebSocket disconnected', event.code, event.reason);
      this.stopHeartbeat();
      this.emit('disconnected', { code: event.code, reason: event.reason });

      // Attempt to reconnect if not intentional
      if (!this.isIntentionalClose) {
        this.reconnect();
      }
    };
  }

  /**
   * Reconnect with exponential backoff
   */
  reconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      this.emit('max_reconnect_attempts', {});
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * Start heartbeat to keep connection alive
   */
  startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 30000); // Send ping every 30 seconds
  }

  /**
   * Stop heartbeat
   */
  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Handle incoming messages
   */
  handleMessage(message) {
    const { event, data } = message;

    // Ignore heartbeat messages
    if (event === 'heartbeat') {
      return;
    }

    console.log('WebSocket message received:', event, data);

    // Emit to specific event listeners
    this.emit(event, data);

    // Emit to global listeners
    this.emit('message', message);
  }

  /**
   * Register event listener
   *
   * @param {string} eventType - Event type to listen for
   * @param {function} callback - Callback function
   */
  on(eventType, callback) {
    if (!this.listeners[eventType]) {
      this.listeners[eventType] = [];
    }
    this.listeners[eventType].push(callback);

    // Return unsubscribe function
    return () => {
      this.off(eventType, callback);
    };
  }

  /**
   * Remove event listener
   *
   * @param {string} eventType - Event type
   * @param {function} callback - Callback function to remove
   */
  off(eventType, callback) {
    if (!this.listeners[eventType]) return;

    this.listeners[eventType] = this.listeners[eventType].filter(
      cb => cb !== callback
    );
  }

  /**
   * Emit event to listeners
   *
   * @param {string} eventType - Event type
   * @param {object} data - Event data
   */
  emit(eventType, data) {
    if (!this.listeners[eventType]) return;

    this.listeners[eventType].forEach(callback => {
      try {
        callback(data);
      } catch (error) {
        console.error(`Error in ${eventType} listener:`, error);
      }
    });
  }

  /**
   * Send message to server
   *
   * @param {object} message - Message to send
   */
  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.error('WebSocket not connected');
    }
  }

  /**
   * Close WebSocket connection
   */
  close() {
    this.isIntentionalClose = true;
    this.stopHeartbeat();

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.listeners = {};
  }

  /**
   * Check if WebSocket is connected
   */
  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }
}

export default WebSocketClient;


/**
 * Example usage:
 *
 * import WebSocketClient from './api/websocket';
 *
 * const token = localStorage.getItem('token');
 * const ws = new WebSocketClient(token);
 *
 * // Connect
 * ws.connect();
 *
 * // Listen for specific events
 * ws.on('job_progress', (data) => {
 *   console.log('Job progress:', data);
 *   updateUI(data);
 * });
 *
 * ws.on('company_updated', (data) => {
 *   console.log('Company updated:', data);
 *   refreshCompanyData(data.company_id);
 * });
 *
 * ws.on('notification', (data) => {
 *   showNotification(data.title, data.message);
 * });
 *
 * // Clean up on unmount
 * ws.close();
 */
