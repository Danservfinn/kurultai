/**
 * Workflow Module Index
 *
 * Exports all workflow modules for the proposal
 * state machine, mapping, and validation.
 */

const { ProposalStateMachine, proposalStates, implementationStates } = require('./proposal-states');
const { ProposalMapper } = require('./proposal-mapper');
const { ValidationHandler } = require('./validation');

module.exports = {
  ProposalStateMachine,
  ProposalMapper,
  ValidationHandler,
  proposalStates,
  implementationStates
};
