/**
 * Bridge between Discord and OpenClaw Gateway
 * Routes Discord messages to OpenClaw WebSocket for Kublai processing
 */

const WebSocket = require('ws');

class DiscordOpenClawBridge {
  constructor(discordTransport, logger = console) {
    this.discord = discordTransport;
    this.logger = logger;
    this.ws = null;
    this.gatewayUrl = process.env.OPENCLAW_WS_URL || 'ws://localhost:18789/ws';
    this.token = process.env.OPENCLAW_GATEWAY_TOKEN;
    this.sessionId = null;
    this.connected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 5000;
  }

  async connect() {
    if (!this.token) {
      this.logger.warn('OPENCLAW_GATEWAY_TOKEN not set, skipping OpenClaw bridge');
      return false;
    }

    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.gatewayUrl);

        this.ws.on('open', () => {
          this.logger.info('Connected to OpenClaw gateway');
          this.reconnectAttempts = 0;
        });

        this.ws.on('message', (data) => {
          try {
            const msg = JSON.parse(data);
            this.handleOpenClawMessage(msg);
          } catch (error) {
            this.logger.error('Failed to parse OpenClaw message:', error);
          }
        });

        this.ws.on('error', (error) => {
          this.logger.error('OpenClaw WebSocket error:', error);
          if (!this.connected) {
            reject(error);
          }
        });

        this.ws.on('close', (code, reason) => {
          this.logger.warn(`OpenClaw WebSocket closed: ${code} ${reason}`);
          this.connected = false;
          this.attemptReconnection();
        });

        // Resolve on successful connection
        setTimeout(() => {
          if (this.ws.readyState === WebSocket.OPEN) {
            resolve(true);
          }
        }, 2000);

      } catch (error) {
        this.logger.error('Failed to create WebSocket:', error);
        reject(error);
      }
    });
  }

  handleOpenClawMessage(msg) {
    // Handle authentication challenge
    if (msg.method === 'connect.challenge') {
      this.respondToChallenge(msg.params.nonce);
      return;
    }

    // Handle connection response
    if (msg.method === 'connect.response') {
      if (msg.params.success) {
        this.connected = true;
        this.sessionId = msg.params.sessionId;
        this.logger.info('Authenticated with OpenClaw, session:', this.sessionId);
      } else {
        this.logger.error('OpenClaw authentication failed:', msg.params.error);
      }
      return;
    }

    // Handle agent responses
    if (msg.event === 'agent') {
      this.handleAgentEvent(msg.payload);
      return;
    }

    // Handle other messages
    if (msg.event === 'status' || msg.event === 'health') {
      this.logger.debug('OpenClaw status event:', msg.event);
    }
  }

  respondToChallenge(nonce) {
    const connectMessage = {
      type: 'req',
      id: this.generateId(),
      method: 'connect',
      params: {
        minProtocol: 3,
        maxProtocol: 3,
        role: 'operator',
        scopes: ['operator.admin', 'operator.approvals', 'operator.pairing'],
        auth: { token: this.token },
        client: {
          id: 'discord-bridge',
          version: '0.4.0',
          platform: 'linux',
          mode: 'backend'
        },
        challenge: { nonce }
      }
    };

    this.ws.send(JSON.stringify(connectMessage));
  }

  handleAgentEvent(payload) {
    if (!payload) return;

    // Handle streaming assistant responses
    if (payload.stream === 'assistant' && payload.data?.delta) {
      this.forwardToDiscord(payload.data.delta, payload.sessionKey);
      return;
    }

    // Handle lifecycle events
    if (payload.stream === 'lifecycle') {
      this.logger.info(`Agent lifecycle: ${payload.data?.phase}`);
      return;
    }

    // Handle chat responses
    if (payload.content || payload.message) {
      this.forwardToDiscord(payload.content || payload.message, payload.sessionKey);
    }
  }

  async forwardToDiscord(content, sessionKey) {
    if (!content) return;

    try {
      await this.discord.client.sendMessage(content);
      this.logger.debug(`Forwarded message to Discord: ${content.slice(0, 50)}...`);
    } catch (error) {
      this.logger.error('Failed to forward to Discord:', error);
    }
  }

  async sendToKublai(message, context = {}) {
    if (!this.connected) {
      this.logger.warn('Not connected to OpenClaw gateway, skipping send');
      return false;
    }

    const request = {
      type: 'req',
      id: this.generateId(),
      method: 'chat.send',
      params: {
        sessionKey: 'main', // Kublai is the 'main' agent
        message: message,
        deliver: true,
        idempotencyKey: this.generateId(),
        context: {
          ...context,
          transport: 'discord',
          timestamp: new Date().toISOString()
        }
      }
    };

    try {
      this.ws.send(JSON.stringify(request));
      this.logger.debug('Sent message to Kublai via OpenClaw');
      return true;
    } catch (error) {
      this.logger.error('Failed to send to Kublai:', error);
      return false;
    }
  }

  attemptReconnection() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.logger.error('Max reconnection attempts reached, giving up');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * this.reconnectAttempts;

    this.logger.info(`Attempting reconnection ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`);

    setTimeout(() => {
      this.connect().catch(error => {
        this.logger.error('Reconnection failed:', error);
      });
    }, delay);
  }

  generateId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  async disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
    this.logger.info('OpenClaw bridge disconnected');
  }
}

module.exports = { DiscordOpenClawBridge };
