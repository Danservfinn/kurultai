/**
 * Gateway API Endpoint Tests
 */

// Set required environment variables before importing app
process.env.SIGNAL_ACCOUNT = '+15165643945';
process.env.SIGNAL_DATA_DIR = '/data/.signal';
process.env.SIGNAL_CLI_PATH = '/usr/local/bin/signal-cli';

const request = require('supertest');
const { app } = require('../src/index');

describe('Gateway API Endpoints', () => {
  describe('GET /', () => {
    test('should return gateway information', async () => {
      const response = await request(app)
        .get('/')
        .expect('Content-Type', /json/)
        .expect(200);

      expect(response.body).toHaveProperty('name');
      expect(response.body).toHaveProperty('description');
      expect(response.body).toHaveProperty('version');
      expect(response.body).toHaveProperty('channels');
      expect(response.body).toHaveProperty('endpoints');
    });

    test('should indicate Signal channel status', async () => {
      const response = await request(app).get('/');
      expect(response.body.channels).toHaveProperty('signal');
      expect(['enabled', 'disabled']).toContain(response.body.channels.signal);
    });
  });

  describe('GET /health', () => {
    test('should return health status', async () => {
      const response = await request(app)
        .get('/health')
        .expect('Content-Type', /json/);

      expect(response.body).toHaveProperty('status');
      expect(response.body).toHaveProperty('timestamp');
      expect(response.body).toHaveProperty('uptime');
      expect(response.body).toHaveProperty('version');
      expect(response.body).toHaveProperty('signal');
    });

    test('should include Signal health information', async () => {
      const response = await request(app).get('/health');
      expect(response.body.signal).toHaveProperty('enabled');
      expect(response.body.signal).toHaveProperty('ready');
      expect(typeof response.body.signal.enabled).toBe('boolean');
      expect(typeof response.body.signal.ready).toBe('boolean');
    });
  });

  describe('GET /signal/status', () => {
    test('should return Signal configuration when enabled', async () => {
      const response = await request(app)
        .get('/signal/status')
        .expect('Content-Type', /json/)
        .expect(200);

      expect(response.body).toHaveProperty('enabled');
      expect(response.body).toHaveProperty('ready');
      expect(response.body).toHaveProperty('policies');
      expect(response.body.policies).toHaveProperty('dmPolicy');
      expect(response.body.policies).toHaveProperty('groupPolicy');
    });
  });
});
