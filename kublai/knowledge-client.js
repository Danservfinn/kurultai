'use strict';

const { call } = require('./telemetry-client');

module.exports = {
  recordReflection: params => call('knowledge.record_reflection', params),
  get: params => call('knowledge.get', params),
  list: params => call('knowledge.list', params),
  search: params => call('knowledge.search', params),
  health: () => call('health', {}),
};
