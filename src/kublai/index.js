/**
 * Kublai Self-Awareness Module Index
 *
 * Exports all modules for Kublai's proactive architecture
 * introspection and improvement proposal workflow.
 */

const { ArchitectureIntrospection } = require('./architecture-introspection');
const { ProactiveReflection } = require('./proactive-reflection');
const { ScheduledReflection } = require('./scheduled-reflection');
const { DelegationProtocol } = require('./delegation-protocol');

module.exports = {
  ArchitectureIntrospection,
  ProactiveReflection,
  ScheduledReflection,
  DelegationProtocol
};
