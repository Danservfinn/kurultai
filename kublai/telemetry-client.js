'use strict';

const net = require('net');

function call(method, params = {}, options = {}) {
  const socketPath = options.socketPath || process.env.BRAIN_SERVICE_SOCKET || '/tmp/brain-service.sock';
  const timeoutMs = options.timeoutMs || 5000;

  return new Promise((resolve, reject) => {
    const client = net.createConnection(socketPath);
    let buffer = '';
    const timer = setTimeout(() => {
      client.destroy();
      reject(new Error(`brain-service RPC timed out after ${timeoutMs}ms`));
    }, timeoutMs);

    client.on('connect', () => {
      client.write(`${JSON.stringify({ method, params })}\n`);
    });

    client.on('data', chunk => {
      buffer += chunk.toString('utf8');
      if (buffer.includes('\n')) {
        clearTimeout(timer);
        client.end();
        const line = buffer.split('\n')[0];
        const response = JSON.parse(line);
        if (!response.ok) {
          const error = new Error(response.message || response.error || 'brain-service RPC failed');
          error.code = response.error;
          reject(error);
          return;
        }
        resolve(response.result);
      }
    });

    client.on('error', error => {
      clearTimeout(timer);
      reject(error);
    });
  });
}

module.exports = {
  call,
  createTask: params => call('telemetry.create_task', params),
  claimTask: params => call('telemetry.claim_task', params),
  renewClaim: params => call('telemetry.renew_claim', params),
  completeTask: params => call('telemetry.complete_task', params),
  heartbeat: params => call('telemetry.heartbeat', params),
};
