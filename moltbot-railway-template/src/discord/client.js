/**
 * Discord Bot Client for Kurultai Agent Communication
 * Replaces browser-based webchat for agent-collaboration
 */

const { Client, GatewayIntentBits, Partials } = require('discord.js');

class KurultaiDiscordClient {
  constructor(logger = console) {
    this.logger = logger;
    this.client = new Client({
      intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.DirectMessages
      ],
      partials: [Partials.Channel, Partials.Message]
    });

    this.channelId = process.env.DISCORD_CHANNEL_ID;
    this.guildId = process.env.DISCORD_GUILD_ID;
    this.targetChannel = null;

    this.setupEventHandlers();
  }

  setupEventHandlers() {
    this.client.on('ready', () => {
      this.logger.info(`Discord bot logged in as ${this.client.user.tag}`);
      this.targetChannel = this.client.channels.cache.get(this.channelId);
      if (this.targetChannel) {
        this.logger.info(`Target channel resolved: ${this.targetChannel.name}`);
      } else {
        this.logger.warn(`Target channel ${this.channelId} not found in cache, will fetch on first use`);
      }
    });

    this.client.on('error', (error) => {
      this.logger.error('Discord client error:', error);
    });

    this.client.on('messageCreate', (message) => {
      // Handle incoming messages from Kublai/agents (only from bots in target channel)
      if (message.channel.id === this.channelId && message.author.bot) {
        this.handleIncomingMessage(message);
      }
    });

    this.client.on('interactionCreate', (interaction) => {
      // Forward interactions to external handler
      if (this.onInteraction) {
        this.onInteraction(interaction);
      }
    });
  }

  async connect() {
    const token = process.env.DISCORD_BOT_TOKEN;
    if (!token) {
      throw new Error('DISCORD_BOT_TOKEN environment variable required');
    }
    await this.client.login(token);
    return this;
  }

  async handleIncomingMessage(message) {
    // Route to OpenClaw/Kublai for processing
    this.logger.info(`Received message from ${message.author.tag}: ${message.content.slice(0, 100)}`);
    if (this.onAgentMessage) {
      this.onAgentMessage(message);
    }
  }

  async fetchTargetChannel() {
    if (!this.targetChannel) {
      this.targetChannel = await this.client.channels.fetch(this.channelId);
    }
    return this.targetChannel;
  }

  async sendMessage(content, options = {}) {
    const channel = await this.fetchTargetChannel();

    // Discord has 2000 char limit for regular messages, 4000 for nitro
    if (content.length > 2000) {
      return this.sendChunkedMessage(content, options);
    }

    return channel.send({ content, ...options });
  }

  async sendChunkedMessage(content, options = {}) {
    const chunks = this.chunkMessage(content, 1900);
    const messages = [];

    for (let i = 0; i < chunks.length; i++) {
      const prefix = i === 0 ? '' : `(continued ${i + 1}/${chunks.length})\n`;
      const chunkOptions = i === chunks.length - 1 ? options : {};
      const message = await this.sendMessage(prefix + chunks[i], chunkOptions);
      messages.push(message);
    }

    return messages;
  }

  chunkMessage(content, maxLength = 1900) {
    const chunks = [];
    let remaining = content;

    while (remaining.length > 0) {
      if (remaining.length <= maxLength) {
        chunks.push(remaining);
        break;
      }

      // Find a good breaking point (newline preferred)
      let breakPoint = remaining.lastIndexOf('\n', maxLength);
      if (breakPoint === -1 || breakPoint < maxLength * 0.5) {
        // No good newline, try space
        breakPoint = remaining.lastIndexOf(' ', maxLength);
      }
      if (breakPoint === -1 || breakPoint < maxLength * 0.5) {
        // Force break at maxLength
        breakPoint = maxLength;
      }

      chunks.push(remaining.slice(0, breakPoint));
      remaining = remaining.slice(breakPoint).trim();
    }

    return chunks;
  }

  async createThread(name, options = {}) {
    const channel = await this.fetchTargetChannel();
    return channel.threads.create({
      name: name.slice(0, 100), // Discord thread name limit
      autoArchiveDuration: options.autoArchiveDuration || 1440, // 24 hours default
      reason: options.reason || 'Kurultai plan discussion'
    });
  }

  async disconnect() {
    await this.client.destroy();
    this.logger.info('Discord client disconnected');
  }
}

module.exports = { KurultaiDiscordClient };
