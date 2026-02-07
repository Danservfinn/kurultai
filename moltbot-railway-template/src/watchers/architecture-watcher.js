/**
 * ARCHITECTURE.md Watcher
 *
 * Watches ARCHITECTURE.md for changes and syncs sections to Neo4j in real-time.
 * This is integrated into moltbot for continuous architecture sync when running.
 */

const chokidar = require('chokidar');
const path = require('path');

// Import sync functions
const syncModule = require('../../scripts/sync-architecture-to-neo4j');
const {
  parseArchitectureSections,
  syncSectionsToNeo4j
} = syncModule;

/**
 * Architecture watcher class
 */
class ArchitectureWatcher {
  constructor(options = {}) {
    this.architecturePath = options.architecturePath ||
      path.join(process.cwd(), 'ARCHITECTURE.md');
    this.logger = options.logger || console;
    this.neo4j = options.neo4j; // Neo4j driver instance
    this.watcher = null;
    this.syncTimeout = null;
    this.lastChecksum = null;
  }

  /**
   * Start watching ARCHITECTURE.md for changes
   */
  start() {
    this.logger.info('[ARCH-watcher] Starting ARCHITECTURE.md watcher...');

    // Use chokidar to watch the file
    this.watcher = chokidar.watch(this.architecturePath, {
      persistent: true,
      ignoreInitial: true, // Don't sync on startup (git hook handles that)
      awaitWriteFinish: {
        stabilityThreshold: 2000, // Wait 2s after write before syncing
        pollInterval: 100
      }
    });

    this.watcher.on('change', (filePath) => {
      this.logger.info(`[ARCH-watcher] ARCHITECTURE.md changed, syncing...`);
      this.scheduleSync();
    });

    this.watcher.on('error', (error) => {
      this.logger.error(`[ARCH-watcher] Error: ${error.message}`);
    });

    this.logger.info(`[ARCH-watcher] Watching ${this.architecturePath}`);
  }

  /**
   * Schedule sync with debouncing
   * Multiple rapid changes will only trigger one sync
   */
  scheduleSync() {
    // Clear any pending sync
    if (this.syncTimeout) {
      clearTimeout(this.syncTimeout);
    }

    // Schedule sync in 3 seconds (debounce)
    this.syncTimeout = setTimeout(async () => {
      await this.sync();
    }, 3000);
  }

  /**
   * Parse and sync ARCHITECTURE.md to Neo4j
   */
  async sync() {
    try {
      const fs = require('fs').promises;
      const markdown = await fs.readFile(this.architecturePath, 'utf-8');

      // Calculate checksum to detect if content actually changed
      const crypto = require('crypto');
      const checksum = crypto.createHash('sha256').update(markdown).digest('hex');

      if (this.lastChecksum === checksum) {
        this.logger.info('[ARCH-watcher] Content unchanged, skipping sync');
        return;
      }

      this.lastChecksum = checksum;

      // Parse sections
      const sections = parseArchitectureSections(markdown);

      this.logger.info(`[ARCH-watcher] Parsed ${sections.length} sections`);

      // Sync to Neo4j (use 'live' as commit for real-time updates)
      const commitHash = process.env.GIT_COMMIT || 'live';
      await syncSectionsToNeo4j(sections, commitHash);

      this.logger.info(`[ARCH-watcher] Sync complete`);
    } catch (error) {
      this.logger.error(`[ARCH-watcher] Sync failed: ${error.message}`);
    }
  }

  /**
   * Stop watching
   */
  stop() {
    if (this.watcher) {
      this.watcher.close();
      this.watcher = null;
    }
    if (this.syncTimeout) {
      clearTimeout(this.syncTimeout);
      this.syncTimeout = null;
    }
    this.logger.info('[ARCH-watcher] Stopped');
  }
}

module.exports = { ArchitectureWatcher };
