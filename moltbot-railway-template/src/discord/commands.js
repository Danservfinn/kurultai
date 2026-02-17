/**
 * Discord Slash Commands for Kurultai Agent Collaboration
 */

const { SlashCommandBuilder } = require('discord.js');

const commands = [
  new SlashCommandBuilder()
    .setName('plan')
    .setDescription('Send a plan handoff to Kublai')
    .addStringOption(option =>
      option.setName('objective')
        .setDescription('What should be accomplished')
        .setRequired(true))
    .addStringOption(option =>
      option.setName('context')
        .setDescription('Background information')
        .setRequired(false))
    .addStringOption(option =>
      option.setName('approach')
        .setDescription('Suggested approach')
        .setRequired(false))
    .addStringOption(option =>
      option.setName('priority')
        .setDescription('Plan priority')
        .setRequired(false)
        .addChoices(
          { name: 'High', value: 'high' },
          { name: 'Medium', value: 'medium' },
          { name: 'Low', value: 'low' }
        )),

  new SlashCommandBuilder()
    .setName('status')
    .setDescription('Request status update from an agent')
    .addStringOption(option =>
      option.setName('plan_id')
        .setDescription('Plan ID to check status for')
        .setRequired(true))
    .addStringOption(option =>
      option.setName('agent')
        .setDescription('Agent to query (default: @kublai)')
        .setRequired(false)
        .addChoices(
          { name: 'Kublai', value: 'kublai' },
          { name: 'Möngke', value: 'mongke' },
          { name: 'Temüjin', value: 'temujin' },
          { name: 'Jochi', value: 'jochi' },
          { name: 'Chagatai', value: 'chagatai' },
          { name: 'Ögedei', value: 'ogedei' }
        ))
    .addBooleanOption(option =>
      option.setName('private')
        .setDescription('Show response only to you')
        .setRequired(false)),

  new SlashCommandBuilder()
    .setName('agents')
    .setDescription('List all available agents and their status'),

  new SlashCommandBuilder()
    .setName('handback')
    .setDescription('Submit a completion report (for agents)')
    .addStringOption(option =>
      option.setName('plan_id')
        .setDescription('Plan ID that was completed')
        .setRequired(true))
    .addStringOption(option =>
      option.setName('status')
        .setDescription('Completion status')
        .setRequired(true)
        .addChoices(
          { name: 'Completed', value: 'completed' },
          { name: 'Partial', value: 'partial' },
          { name: 'Blocked', value: 'blocked' }
        ))
    .addStringOption(option =>
      option.setName('deliverables')
        .setDescription('Summary of what was accomplished')
        .setRequired(false)),

  new SlashCommandBuilder()
    .setName('delegate')
    .setDescription('Delegate a specific task to an agent')
    .addStringOption(option =>
      option.setName('agent')
        .setDescription('Agent to delegate to')
        .setRequired(true)
        .addChoices(
          { name: 'Möngke (Research)', value: 'mongke' },
          { name: 'Temüjin (Developer)', value: 'temujin' },
          { name: 'Jochi (Analyst)', value: 'jochi' },
          { name: 'Chagatai (Writer)', value: 'chagatai' },
          { name: 'Ögedei (Ops)', value: 'ogedei' }
        ))
    .addStringOption(option =>
      option.setName('task')
        .setDescription('Task description')
        .setRequired(true))
    .addStringOption(option =>
      option.setName('context')
        .setDescription('Additional context')
        .setRequired(false))
];

module.exports = { commands };
