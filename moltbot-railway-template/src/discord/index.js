/**
 * Discord Integration Module for Kurultai Agent Collaboration
 *
 * Replaces browser-based webchat with Discord bot integration.
 * Provides slash commands and bidirectional messaging with OpenClaw gateway.
 */

const { KurultaiDiscordClient } = require('./client');
const { commands } = require('./commands');
const { DiscordCommandHandlers, registerCommands } = require('./handlers');
const { DiscordTransport } = require('./transport');
const { DiscordOpenClawBridge } = require('./openclaw-bridge');

module.exports = {
  // Core client
  KurultaiDiscordClient,

  // Commands
  commands,
  DiscordCommandHandlers,
  registerCommands,

  // Transport layer
  DiscordTransport,

  // OpenClaw bridge
  DiscordOpenClawBridge
};
