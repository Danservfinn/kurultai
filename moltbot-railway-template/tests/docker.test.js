/**
 * Docker Build Tests
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

describe('Docker Configuration', () => {
  const dockerfilePath = path.join(__dirname, '..', 'Dockerfile');

  test('Dockerfile should exist', () => {
    expect(fs.existsSync(dockerfilePath)).toBe(true);
  });

  test('Dockerfile should contain signal-cli installation', () => {
    const dockerfile = fs.readFileSync(dockerfilePath, 'utf8');
    expect(dockerfile).toContain('signal-cli');
    expect(dockerfile).toContain('SIGNAL_CLI_VERSION');
  });

  test('Dockerfile should install Java', () => {
    const dockerfile = fs.readFileSync(dockerfilePath, 'utf8');
    expect(dockerfile).toContain('openjdk-17');
  });

  test('Dockerfile should create Signal data directory', () => {
    const dockerfile = fs.readFileSync(dockerfilePath, 'utf8');
    expect(dockerfile).toContain('/data/.signal');
  });

  test('Dockerfile should extract Signal data', () => {
    const dockerfile = fs.readFileSync(dockerfilePath, 'utf8');
    expect(dockerfile).toContain('signal-data.tar.gz');
  });

  test('Dockerfile should use non-root user', () => {
    const dockerfile = fs.readFileSync(dockerfilePath, 'utf8');
    expect(dockerfile).toContain('USER 1000:1000');
  });

  test('Dockerfile should have health check', () => {
    const dockerfile = fs.readFileSync(dockerfilePath, 'utf8');
    expect(dockerfile).toContain('HEALTHCHECK');
  });

  test('Dockerfile should expose correct port', () => {
    const dockerfile = fs.readFileSync(dockerfilePath, 'utf8');
    expect(dockerfile).toContain('EXPOSE 8080');
  });

  test('Dockerfile should set environment variables', () => {
    const dockerfile = fs.readFileSync(dockerfilePath, 'utf8');
    expect(dockerfile).toContain('SIGNAL_ENABLED');
    expect(dockerfile).toContain('SIGNAL_DATA_DIR');
    expect(dockerfile).toContain('SIGNAL_CLI_PATH');
  });
});

describe('Railway Configuration', () => {
  const railwayConfigPath = path.join(__dirname, '..', 'railway.toml');

  test('railway.toml should exist', () => {
    expect(fs.existsSync(railwayConfigPath)).toBe(true);
  });

  test('railway.toml should configure Docker build', () => {
    const config = fs.readFileSync(railwayConfigPath, 'utf8');
    expect(config).toContain('builder = "DOCKERFILE"');
  });

  test('railway.toml should configure health check', () => {
    const config = fs.readFileSync(railwayConfigPath, 'utf8');
    expect(config).toContain('healthcheckPath = "/health"');
  });

  test('railway.toml should set Signal environment variables', () => {
    const config = fs.readFileSync(railwayConfigPath, 'utf8');
    expect(config).toContain('SIGNAL_ENABLED');
    expect(config).toContain('SIGNAL_ACCOUNT');
  });
});
