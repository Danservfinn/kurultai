/**
 * Discord Transport Layer - Replaces Browser Webchat
 * Implements the Transport interface for agent-collaboration
 * Integrates with Kublai's DelegationProtocol
 */

const { KurultaiDiscordClient } = require('./client');
const { DiscordCommandHandlers, registerCommands } = require('./handlers');

class DiscordTransport {
  constructor(logger = console) {
    this.logger = logger;
    this.client = null;
    this.handlers = null;
    this.responseHandlers = new Map();
    this.bridge = null; // OpenClaw bridge reference

    // Callbacks for integration with DelegationProtocol
    this.onHandback = null;
    this.onStatusUpdate = null;
    this.onAssistanceRequest = null;
  }

  async initialize() {
    this.logger.info('Initializing Discord transport...');

    // Initialize Discord client
    this.client = new KurultaiDiscordClient(this.logger);
    await this.client.connect();

    // Register slash commands
    await registerCommands(this.logger);

    // Set up command handlers
    this.handlers = new DiscordCommandHandlers(this, this.logger);
    this.handlers.setup();

    // Set up agent response listener
    this.client.onAgentMessage = (message) => this.handleAgentResponse(message);

    this.logger.info('Discord transport initialized successfully');
    return this;
  }

  async sendPlanHandoff(planData) {
    this.logger.info(`Sending plan handoff: ${planData.planId}`);
    const content = this.formatPlanHandoff(planData);

    // Send to Discord channel
    const message = await this.client.sendMessage(content);

    // If bridge is available, also send via OpenClaw
    if (this.bridge && this.bridge.connected) {
      await this.bridge.sendToKublai(content, {
        planId: planData.planId,
        type: 'plan-handoff',
        priority: planData.priority
      });
    }

    return {
      messageId: message.id || message[0]?.id,
      timestamp: new Date(),
      transport: 'discord',
      planId: planData.planId
    };
  }

  async sendStatusRequest(planId, agent = 'kublai') {
    this.logger.info(`Sending status request for ${planId} to ${agent}`);
    const content = `---STATUS-REQUEST---
Plan ID: ${planId}
To: @${agent}

Requesting status update.
---END-REQUEST---`;

    await this.client.sendMessage(content);

    if (this.bridge && this.bridge.connected) {
      await this.bridge.sendToKublai(content, {
        planId,
        type: 'status-request',
        targetAgent: agent
      });
    }

    return { sent: true, planId, agent };
  }

  async sendCourseCorrection(planId, issue, recommendation) {
    this.logger.info(`Sending course correction for ${planId}`);
    const content = `---COURSE-CORRECTION---
Plan ID: ${planId}
Severity: moderate

## Issue
${issue}

## Recommended Fix
${recommendation}
---END-CORRECTION---`;

    await this.client.sendMessage(content);

    if (this.bridge && this.bridge.connected) {
      await this.bridge.sendToKublai(content, {
        planId,
        type: 'course-correction'
      });
    }

    return { sent: true, planId };
  }

  async sendHandback(handbackData) {
    this.logger.info(`Sending handback for ${handbackData.planId}`);
    const content = this.formatHandback(handbackData);

    await this.client.sendMessage(content);

    if (this.bridge && this.bridge.connected) {
      await this.bridge.sendToKublai(content, {
        planId: handbackData.planId,
        type: 'handback',
        status: handbackData.status
      });
    }

    return { sent: true, planId: handbackData.planId };
  }

  formatPlanHandoff(planData) {
    const target = planData.targetAgent ? `@${planData.targetAgent}` : '@kublai';

    return `---PLAN-HANDOFF---
Plan ID: ${planData.planId}
Priority: ${planData.priority || 'medium'}
To: ${target}
From: ${planData.requestedBy}

## Objective
${planData.objective}

## Context
${planData.context || 'No additional context provided.'}

## Suggested Approach
${planData.approach || 'Please analyze and delegate to appropriate specialist.'}

## Success Criteria
- [ ] Task completed successfully
- [ ] Deliverables verified

## Constraints
${planData.constraints || '- None specified'}
---END-PLAN---`;
  }

  formatHandback(handbackData) {
    const emoji = handbackData.status === 'completed' ? '✅' :
                  handbackData.status === 'blocked' ? '🔴' : '⚠️';

    return `---HANDBACK-REPORT---
Plan ID: ${handbackData.planId}
From: ${handbackData.submittedBy}
Status: ${handbackData.status}

${emoji} **${handbackData.status.toUpperCase()}**

${handbackData.deliverables ? `## Deliverables
${handbackData.deliverables}` : ''}
---END-HANDBACK---`;
  }

  handleAgentResponse(message) {
    const content = message.content;

    // Check for response markers
    if (content.includes('---HANDBACK-REPORT---')) {
      this.processHandback(message);
    } else if (content.includes('---STATUS-UPDATE---')) {
      this.processStatusUpdate(message);
    } else if (content.includes('---ASSISTANCE-REQUEST---')) {
      this.processAssistanceRequest(message);
    }

    // Notify any waiting response handlers
    for (const [key, handler] of this.responseHandlers) {
      if (content.includes(key) || message.content.includes(key)) {
        handler(message);
        this.responseHandlers.delete(key);
      }
    }
  }

  processHandback(message) {
    this.logger.info(`Received handback report: ${message.id}`);
    const handback = this.parseHandback(message.content);

    if (this.onHandback) {
      this.onHandback({ ...handback, messageId: message.id });
    }
  }

  processStatusUpdate(message) {
    this.logger.info(`Received status update: ${message.id}`);
    const update = this.parseStatusUpdate(message.content);

    if (this.onStatusUpdate) {
      this.onStatusUpdate({ ...update, messageId: message.id });
    }
  }

  processAssistanceRequest(message) {
    this.logger.info(`Received assistance request: ${message.id}`);

    if (this.onAssistanceRequest) {
      this.onAssistanceRequest(message.content);
    }
  }

  parseHandback(content) {
    const planIdMatch = content.match(/Plan ID:\s*(.+)/i);
    const statusMatch = content.match(/Status:\s*(.+)/i);
    const fromMatch = content.match(/From:\s*(.+)/i);

    return {
      planId: planIdMatch ? planIdMatch[1].trim() : null,
      status: statusMatch ? statusMatch[1].trim().toLowerCase() : 'unknown',
      from: fromMatch ? fromMatch[1].trim() : 'unknown',
      rawContent: content,
      timestamp: new Date()
    };
  }

  parseStatusUpdate(content) {
    const planIdMatch = content.match(/Plan ID:\s*(.+)/i);
    const agentMatch = content.match(/Agent:\s*@?(\w+)/i);

    return {
      planId: planIdMatch ? planIdMatch[1].trim() : null,
      agent: agentMatch ? agentMatch[1].trim() : 'unknown',
      rawContent: content,
      timestamp: new Date()
    };
  }

  async createThread(name, options = {}) {
    return this.client.createThread(name, options);
  }

  async waitForResponse(planId, timeoutMs = 300000) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.responseHandlers.delete(planId);
        reject(new Error(`Timeout waiting for response to plan ${planId}`));
      }, timeoutMs);

      this.responseHandlers.set(planId, (message) => {
        clearTimeout(timeout);
        resolve(message);
      });
    });
  }

  setBridge(bridge) {
    this.bridge = bridge;
  }

  async disconnect() {
    if (this.client) {
      await this.client.disconnect();
    }
    this.logger.info('Discord transport disconnected');
  }
}

module.exports = { DiscordTransport };
