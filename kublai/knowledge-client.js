'use strict';

const { call } = require('./telemetry-client');

module.exports = {
  recordReflection: params => call('knowledge.record_reflection', params),
  health: () => call('health', {}),
};
