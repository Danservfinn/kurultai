/**
 * Kublai Self-Awareness Module Index
 *
 * Exports all modules for Kublai's proactive architecture
 * introspection and improvement proposal workflow.
 */

const { ArchitectureIntrospection } = require('./architecture-introspection');
const { ProactiveReflection } = require('./proactive-reflection');
const { ScheduledReflection } = require('./scheduled-reflection');

module.exports = {
  ArchitectureIntrospection,
  ProactiveReflection,
  ScheduledReflection
};
