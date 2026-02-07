/**
 * Audit Logger
 * Logs deployments to Neo4j for traceability
 */

const neo4j = require('neo4j-driver');
const constants = require('../config/constants');

class AuditLogger {
  constructor(options = {}) {
    this.uri = options.uri || constants.NEO4J_URI;
    this.user = options.user || constants.NEO4J_USER;
    this.password = options.password || constants.NEO4J_PASSWORD;
    this.logger = options.logger || console;
    this.driver = null;
    this.connected = false;
  }

  /**
   * Connect to Neo4j
   */
  async connect() {
    try {
      this.driver = neo4j.driver(
        this.uri,
        neo4j.auth.basic(this.user, this.password)
      );

      await this.driver.verifyConnectivity();
      this.connected = true;

      // Create constraints if they don't exist
      await this.ensureSchema();

      this.logger.info('Audit logger connected to Neo4j');
    } catch (e) {
      this.logger.error(`Failed to connect to Neo4j: ${e.message}`);
      this.connected = false;
    }
  }

  /**
   * Ensure schema exists
   */
  async ensureSchema() {
    const session = this.driver.session();
    try {
      // SkillDeployment node
      await session.run(`
        CREATE CONSTRAINT skill_deployment_id IF NOT EXISTS
        FOR (sd:SkillDeployment) REQUIRE sd.id IS UNIQUE
      `);

      // SkillVersion node
      await session.run(`
        CREATE CONSTRAINT skill_version_name IF NOT EXISTS
        FOR (sv:SkillVersion) REQUIRE sv.name IS UNIQUE
      `);

      // PollState node
      await session.run(`
        CREATE CONSTRAINT poll_state_key IF NOT EXISTS
        FOR (ps:PollState) REQUIRE ps.key IS UNIQUE
      `);

    } finally {
      await session.close();
    }
  }

  /**
   * Log a deployment
   */
  async logDeployment(deployment) {
    if (!this.connected) {
      this.logger.warn('Not connected to Neo4j, skipping audit log');
      return;
    }

    const session = this.driver.session();
    try {
      const result = await session.run(`
        MERGE (sd:SkillDeployment {id: $id})
        SET sd.timestamp = datetime($timestamp),
            sd.status = $status,
            sd.commit_sha = $commitSha,
            sd.previous_sha = $previousSha,
            sd.trigger = $trigger,
            sd.delivery_id = $deliveryId,
            sd.skills_count = $skillsCount,
            sd.branch = $branch
        RETURN sd
      `, {
        id: deployment.id,
        timestamp: deployment.timestamp || new Date().toISOString(),
        status: deployment.status || 'success',
        commitSha: deployment.metadata?.commitSha,
        previousSha: deployment.metadata?.previousSha,
        trigger: deployment.metadata?.trigger || 'unknown',
        deliveryId: deployment.metadata?.deliveryId,
        skillsCount: deployment.deployed?.length || 0,
        branch: deployment.metadata?.branch
      });

      // Log each deployed skill version
      for (const skill of deployment.deployed || []) {
        await session.run(`
          MATCH (sd:SkillDeployment {id: $deploymentId})
          MERGE (sv:SkillVersion {name: $name})
          SET sv.version = $version,
              sv.path = $path,
              sv.deployed_at = datetime($timestamp)
          MERGE (sd)-[:DEPLOYED]->(sv)
        `, {
          deploymentId: deployment.id,
          name: skill.name,
          version: skill.version,
          path: skill.path,
          timestamp: deployment.timestamp || new Date().toISOString()
        });
      }

      this.logger.debug(`Audit log: deployment ${deployment.id}`);

    } catch (e) {
      this.logger.error(`Audit log failed: ${e.message}`);
    } finally {
      await session.close();
    }
  }

  /**
   * Log a poll result
   */
  async logPollResult(result) {
    if (!this.connected) return;

    const session = this.driver.session();
    try {
      await session.run(`
        CREATE (pr:PollResult {
          timestamp: datetime(),
          sha: $sha,
          status: $status,
          error: $error,
          deployment_id: $deploymentId
        })
      `, {
        sha: result.sha || '',
        status: result.status,
        error: result.error || null,
        deploymentId: result.deploymentId || null
      });
    } finally {
      await session.close();
    }
  }

  /**
   * Update last processed SHA
   */
  async updateLastSha(sha) {
    if (!this.connected) return;

    const session = this.driver.session();
    try {
      await session.run(`
        MERGE (ps:PollState {key: 'last_sha'})
        SET ps.sha = $sha,
            ps.updated_at = datetime()
      `, { sha });
    } finally {
      await session.close();
    }
  }

  /**
   * Get last processed SHA
   */
  async getLastSha() {
    if (!this.connected) return null;

    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (ps:PollState {key: 'last_sha'})
        RETURN ps.sha as sha
      `);

      if (result.records.length > 0) {
        return result.records[0].get('sha');
      }
      return null;
    } finally {
      await session.close();
    }
  }

  /**
   * Get recent deployments
   */
  async getRecentDeployments(limit = 10) {
    if (!this.connected) return [];

    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (sd:SkillDeployment)
        RETURN sd
        ORDER BY sd.timestamp DESC
        LIMIT $limit
      `, { limit });

      return result.records.map(r => {
        const props = r.get('sd').properties;
        return {
          id: props.id,
          timestamp: props.timestamp,
          status: props.status,
          commitSha: props.commit_sha,
          trigger: props.trigger,
          skillsCount: props.skills_count
        };
      });
    } finally {
      await session.close();
    }
  }

  /**
   * Close connection
   */
  async close() {
    if (this.driver) {
      await this.driver.close();
      this.connected = false;
    }
  }
}

module.exports = { AuditLogger };
