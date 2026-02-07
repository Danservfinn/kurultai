/**
 * Skill Sync Service - Configuration Constants
 */

module.exports = {
  // Paths
  SKILLS_DIR: process.env.SKILLS_DIR || '/data/skills',
  BACKUP_DIR: process.env.BACKUP_DIR || '/data/backups/skills',
  LOCK_FILE: process.env.LOCK_FILE || '/tmp/skill-sync.lock',

  // GitHub
  GITHUB_OWNER: process.env.GITHUB_OWNER || 'Danservfinn',
  GITHUB_REPO: process.env.GITHUB_REPO || 'kurultai-skills',
  GITHUB_WEBHOOK_SECRET: process.env.GITHUB_WEBHOOK_SECRET,
  GITHUB_TOKEN: process.env.GITHUB_TOKEN,
  POLLING_INTERVAL_MIN: parseInt(process.env.POLLING_INTERVAL_MIN || '5', 10),

  // Validation
  MAX_SKILL_SIZE_BYTES: parseInt(process.env.MAX_SKILL_SIZE_BYTES || '102400', 10),
  REQUIRED_FIELDS: ['name', 'version', 'description'],

  // Security patterns for secret detection
  SECRET_PATTERNS: [
    { name: 'anthropic_key', pattern: /sk-ant-[a-zA-Z0-9_-]{48,}/ },
    { name: 'github_token', pattern: /ghp_[a-zA-Z0-9]{36}/ },
    { name: 'github_oauth', pattern: /gho_[a-zA-Z0-9]{36}/ },
    { name: 'aws_access_key', pattern: /AKIA[0-9A-Z]{16}/ },
    { name: 'aws_secret', pattern: /[0-9a-zA-Z/+]{40}/ },
    { name: 'private_key', pattern: /-----BEGIN[A-Z]+ PRIVATE KEY-----/ },
    { name: 'api_key', pattern: /(?:api[_-]?key|apikey)["':\s]*["']?([a-zA-Z0-9_\-]{20,})/i },
    { name: 'slack_token', pattern: /xox[baprs]-[a-zA-Z0-9-]{10,}/ },
    { name: 'slack_webhook', pattern: /hooks\.slack\.com\/services\/[A-Z0-9]{9}\/[A-Z0-9]{9}\/[a-zA-Z0-9]{24}/ },
    { name: 'railway_token', pattern: /[a-f0-9]{32}/ },
  ],

  // Neo4j
  NEO4J_URI: process.env.NEO4J_URI,
  NEO4J_USER: process.env.NEO4J_USER || 'neo4j',
  NEO4J_PASSWORD: process.env.NEO4J_PASSWORD,

  // Deployment
  DEPLOYMENT_LOCK_TTL: parseInt(process.env.DEPLOYMENT_LOCK_TTL || '300', 10),
  HEALTH_CHECK_TIMEOUT_MS: 10000,
  MAX_RETRIES: 3,

  // Logging
  LOG_LEVEL: process.env.LOG_LEVEL || 'info',
};
