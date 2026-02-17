/**
 * Discord Slash Command Handlers
 * Integrates with Kublai's DelegationProtocol
 */

const { REST, Routes } = require('discord.js');
const { commands } = require('./commands');

class DiscordCommandHandlers {
  constructor(discordTransport, logger = console) {
    this.transport = discordTransport;
    this.logger = logger;
    this.client = discordTransport.client;
  }

  setup() {
    this.client.onInteraction = (interaction) => this.handleInteraction(interaction);
    this.logger.info('Discord command handlers registered');
  }

  async handleInteraction(interaction) {
    if (!interaction.isChatInputCommand()) return;

    try {
      switch (interaction.commandName) {
        case 'plan':
          await this.handlePlanCommand(interaction);
          break;
        case 'status':
          await this.handleStatusCommand(interaction);
          break;
        case 'agents':
          await this.handleAgentsCommand(interaction);
          break;
        case 'handback':
          await this.handleHandbackCommand(interaction);
          break;
        case 'delegate':
          await this.handleDelegateCommand(interaction);
          break;
        default:
          this.logger.warn(`Unknown command: ${interaction.commandName}`);
      }
    } catch (error) {
      this.logger.error('Command handler error:', error);
      const replyOptions = { content: 'Error processing command: ' + error.message };
      if (interaction.deferred) {
        await interaction.editReply(replyOptions);
      } else {
        await interaction.reply({ ...replyOptions, ephemeral: true });
      }
    }
  }

  async handlePlanCommand(interaction) {
    const ephemeral = false; // Plans are public by default
    await interaction.deferReply({ ephemeral });

    const planData = {
      planId: `plan-${Date.now()}`,
      objective: interaction.options.getString('objective'),
      context: interaction.options.getString('context') || '',
      approach: interaction.options.getString('approach') || '',
      priority: interaction.options.getString('priority') || 'medium',
      requestedBy: interaction.user.tag,
      userId: interaction.user.id
    };

    // Create a thread for this plan
    const thread = await this.transport.createThread(
      `${planData.planId}: ${planData.objective.slice(0, 50)}...`,
      { reason: `Plan discussion for ${planData.planId}` }
    );

    // Send initial message in thread
    await thread.send(`📋 **Plan Discussion Thread**
**Plan ID:** ${planData.planId}
**Requested by:** ${planData.requestedBy}
**Priority:** ${planData.priority}

Agent updates and discussion will be posted here.`);

    // Send plan to Kublai via transport
    const result = await this.transport.sendPlanHandoff(planData);

    await interaction.editReply({
      content: `📋 **Plan submitted to Kublai**
**Plan ID:** ${planData.planId}
**Priority:** ${planData.priority}
**Discussion:** ${thread.url}

Kublai will review and delegate to the appropriate specialist.`
    });

    this.logger.info(`Plan ${planData.planId} submitted by ${planData.requestedBy}`);
  }

  async handleStatusCommand(interaction) {
    const planId = interaction.options.getString('plan_id');
    const agent = interaction.options.getString('agent') || 'kublai';
    const ephemeral = interaction.options.getBoolean('private') || false;

    await interaction.deferReply({ ephemeral });
    await this.transport.sendStatusRequest(planId, agent);

    // Wait for response (with timeout)
    try {
      const response = await this.transport.waitForResponse(planId, 60000);
      const content = response.content || response;
      await interaction.editReply({
        content: `📊 **Status for ${planId}:**\n${content.slice(0, 1900)}`
      });
    } catch (error) {
      await interaction.editReply({
        content: `⏱️ **Status request sent to ${agent}**

Response will appear in the channel when ready. Use \`/status\` again later or check the plan thread.`
      });
    }
  }

  async handleAgentsCommand(interaction) {
    const agents = [
      { name: 'Kublai', id: 'kublai', role: 'Squad Lead', status: '🟢 Active', description: 'Orchestrator and task router' },
      { name: 'Möngke', id: 'mongke', role: 'Researcher', status: '🟢 Active', description: 'Information search and analysis' },
      { name: 'Temüjin', id: 'temujin', role: 'Developer', status: '🟢 Active', description: 'Code implementation and architecture' },
      { name: 'Jochi', id: 'jochi', role: 'Analyst', status: '🟢 Active', description: 'Security review and performance analysis' },
      { name: 'Ögedei', id: 'ogedei', role: 'Ops', status: '🟢 Active', description: 'Operations and failover management' },
      { name: 'Chagatai', id: 'chagatai', role: 'Writer', status: '🟢 Active', description: 'Documentation and content creation' }
    ];

    const agentList = agents.map(a =>
      `**${a.name}** (\`@${a.id}\`) - ${a.role} ${a.status}\n└ ${a.description}`
    ).join('\n');

    await interaction.reply({
      content: `🤖 **Kurultai Agent Network**\n\n${agentList}\n\nUse \`/delegate\` to assign tasks to specific agents, or \`/plan\` to let Kublai route automatically.`
    });
  }

  async handleHandbackCommand(interaction) {
    // This would primarily be used by agents, but humans can use it too
    const planId = interaction.options.getString('plan_id');
    const status = interaction.options.getString('status');
    const deliverables = interaction.options.getString('deliverables') || '';

    const handbackData = {
      planId,
      status,
      deliverables,
      submittedBy: interaction.user.tag,
      isAgent: interaction.user.bot
    };

    // Send handback via transport
    await this.transport.sendHandback(handbackData);

    await interaction.reply({
      content: `✅ **Handback received for ${planId}**\n**Status:** ${status}\n${deliverables ? `**Deliverables:** ${deliverables.slice(0, 500)}` : ''}`,
      ephemeral: true
    });

    this.logger.info(`Handback for ${planId} submitted by ${interaction.user.tag}`);
  }

  async handleDelegateCommand(interaction) {
    const agent = interaction.options.getString('agent');
    const task = interaction.options.getString('task');
    const context = interaction.options.getString('context') || '';

    await interaction.deferReply();

    const planData = {
      planId: `plan-${Date.now()}`,
      objective: task,
      context,
      approach: `Direct delegation to @${agent}`,
      priority: 'medium',
      requestedBy: interaction.user.tag,
      targetAgent: agent
    };

    await this.transport.sendPlanHandoff(planData);

    await interaction.editReply({
      content: `🎯 **Task delegated to ${agent}**\n\n${task}\n\nPlan ID: ${planData.planId}`
    });

    this.logger.info(`Direct delegation to ${agent} by ${interaction.user.tag}`);
  }
}

/**
 * Register slash commands with Discord
 */
async function registerCommands(logger = console) {
  const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_BOT_TOKEN);

  try {
    logger.info('Registering Discord slash commands...');

    const clientId = process.env.DISCORD_CLIENT_ID || process.env.DISCORD_BOT_CLIENT_ID;
    const guildId = process.env.DISCORD_GUILD_ID;

    if (!clientId) {
      throw new Error('DISCORD_CLIENT_ID or DISCORD_BOT_CLIENT_ID environment variable required');
    }
    if (!guildId) {
      throw new Error('DISCORD_GUILD_ID environment variable required');
    }

    await rest.put(
      Routes.applicationGuildCommands(clientId, guildId),
      { body: commands.map(cmd => cmd.toJSON()) }
    );

    logger.info(`Registered ${commands.length} slash commands`);
  } catch (error) {
    logger.error('Failed to register commands:', error);
    throw error;
  }
}

module.exports = { DiscordCommandHandlers, registerCommands };
