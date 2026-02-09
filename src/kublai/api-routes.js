/**
 * Express API Routes for Kublai Self-Awareness System
 * 
 * Endpoints for proposals, workflow, and architecture introspection
 */

const express = require('express');
const router = express.Router();

// Import modules
const { ArchitectureIntrospection } = require('./architecture-introspection');
const { ProactiveReflection } = require('./proactive-reflection');
const { DelegationProtocol } = require('./delegation-protocol');

function createRoutes(neo4jDriver) {
  const introspection = new ArchitectureIntrospection(neo4jDriver);
  const reflection = new ProactiveReflection(neo4jDriver);
  const delegation = new DelegationProtocol(neo4jDriver);

  // ===========================================
  // Architecture Introspection Routes
  // ===========================================

  router.get('/architecture/overview', async (req, res) => {
    const result = await introspection.getArchitectureOverview();
    res.json(result);
  });

  router.get('/architecture/search', async (req, res) => {
    const { q } = req.query;
    const result = await introspection.searchArchitecture(q);
    res.json(result);
  });

  router.get('/architecture/section/:title', async (req, res) => {
    const result = await introspection.getSection(req.params.title);
    res.json(result);
  });

  router.get('/architecture/last-sync', async (req, res) => {
    const result = await introspection.getLastSyncTimestamp();
    res.json(result);
  });

  router.get('/architecture/gaps', async (req, res) => {
    const result = await introspection.identifyGaps();
    res.json(result);
  });

  // ===========================================
  // Proactive Reflection Routes
  // ===========================================

  router.post('/proposals/reflect', async (req, res) => {
    const result = await reflection.triggerReflection();
    res.json(result);
  });

  router.get('/proposals/opportunities', async (req, res) => {
    const { status = 'proposed' } = req.query;
    const result = await reflection.getOpportunities(status);
    res.json(result);
  });

  // ===========================================
  // Proposal Management Routes
  // ===========================================

  router.post('/proposals', async (req, res) => {
    const { opportunity_id, title, description } = req.body;
    const result = await delegation.createProposal(opportunity_id, {
      title,
      description
    });
    res.json(result);
  });

  router.get('/proposals', async (req, res) => {
    const { status } = req.query;
    
    // Query Neo4j for proposals
    const session = neo4jDriver.session();
    try {
      let query = `
        MATCH (ap:ArchitectureProposal)
        ${status ? 'WHERE ap.status = $status' : ''}
        RETURN ap.id as id,
               ap.title as title,
               ap.status as status,
               ap.implementation_status as impl_status,
               ap.priority as priority,
               ap.proposed_at as proposed_at
        ORDER BY ap.proposed_at DESC
        LIMIT 50
      `;
      
      const result = await session.run(query, { status });
      
      res.json({
        status: 'success',
        proposals: result.records.map(r => ({
          id: r.get('id'),
          title: r.get('title'),
          status: r.get('status'),
          implementation_status: r.get('impl_status'),
          priority: r.get('priority'),
          proposed_at: r.get('proposed_at')
        }))
      });
    } finally {
      await session.close();
    }
  });

  router.get('/proposals/:id', async (req, res) => {
    const { id } = req.params;
    
    const session = neo4jDriver.session();
    try {
      const result = await session.run(`
        MATCH (ap:ArchitectureProposal {id: $id})
        RETURN ap
      `, { id });
      
      if (result.records.length === 0) {
        return res.status(404).json({ status: 'not_found' });
      }
      
      res.json({
        status: 'success',
        proposal: result.records[0].get('ap').properties
      });
    } finally {
      await session.close();
    }
  });

  // ===========================================
  // Workflow Control Routes
  // ===========================================

  router.post('/workflow/process', async (req, res) => {
    // Process all pending workflows
    const result = await delegation.processPendingWorkflows();
    res.json(result);
  });

  router.post('/workflow/vet/:id', async (req, res) => {
    const { id } = req.params;
    const result = await delegation.routeToVetting(id);
    res.json(result);
  });

  router.post('/workflow/approve/:id', async (req, res) => {
    const { id } = req.params;
    const { decision = 'approve', notes = '' } = req.body;
    const result = await delegation.completeVetting(id, decision, notes);
    res.json(result);
  });

  router.post('/workflow/implement/:id', async (req, res) => {
    const { id } = req.params;
    const result = await delegation.startImplementation(id);
    res.json(result);
  });

  router.post('/workflow/complete/:id', async (req, res) => {
    const { id } = req.params;
    const { notes = '' } = req.body;
    const result = await delegation.completeImplementation(id, notes);
    res.json(result);
  });

  router.post('/workflow/sync/:id', async (req, res) => {
    const { id } = req.params;
    const result = await delegation.syncToArchitecture(id);
    res.json(result);
  });

  router.get('/workflow/status/:id', async (req, res) => {
    const { id } = req.params;
    const result = await delegation.getWorkflowStatus(id);
    res.json(result);
  });

  // ===========================================
  // Subscription Management Routes
  // ===========================================

  /**
   * POST /api/subscriptions
   * Create a new subscription
   * Body: { subscriber, topic, filter?, target? }
   */
  router.post('/subscriptions', async (req, res) => {
    const { subscriber, topic, filter, target } = req.body;
    
    if (!subscriber || !topic) {
      return res.status(400).json({
        status: 'error',
        error: 'Missing required fields: subscriber, topic'
      });
    }
    
    const session = neo4jDriver.session();
    try {
      const subscriptionId = require('uuid').v4();
      const filterJson = filter ? JSON.stringify(filter) : null;
      
      // Ensure subscriber agent exists
      await session.run(`
        MERGE (a:Agent {id: $agent_id})
        ON CREATE SET a.created_at = datetime()
      `, { agent_id: subscriber });
      
      if (target) {
        // Subscribe to specific target
        await session.run(`
          MERGE (target:Agent {id: $target_id})
          ON CREATE SET target.created_at = datetime()
          MATCH (sub:Agent {id: $subscriber_id})
          CREATE (sub)-[s:SUBSCRIBES_TO {
            id: $sub_id,
            topic: $topic,
            filter: $filter,
            created_at: datetime(),
            subscriber_id: $subscriber_id,
            target_id: $target_id
          }]->(target)
        `, {
          subscriber_id: subscriber,
          target_id: target,
          sub_id: subscriptionId,
          topic: topic,
          filter: filterJson
        });
      } else {
        // Subscribe to all agents
        await session.run(`
          MATCH (sub:Agent {id: $subscriber_id})
          MERGE (all:AllAgents)
          ON CREATE SET all.created_at = datetime()
          CREATE (sub)-[s:SUBSCRIBES_TO {
            id: $sub_id,
            topic: $topic,
            filter: $filter,
            created_at: datetime(),
            subscriber_id: $subscriber_id,
            target_id: '*'
          }]->(all)
        `, {
          subscriber_id: subscriber,
          sub_id: subscriptionId,
          topic: topic,
          filter: filterJson
        });
      }
      
      res.status(201).json({
        status: 'success',
        subscription_id: subscriptionId,
        subscriber: subscriber,
        target: target || '*',
        topic: topic,
        filter: filter,
        created_at: new Date().toISOString()
      });
    } catch (error) {
      res.status(500).json({
        status: 'error',
        error: error.message
      });
    } finally {
      await session.close();
    }
  });

  /**
   * GET /api/subscriptions
   * List subscriptions for an agent
   * Query: agent (required)
   */
  router.get('/subscriptions', async (req, res) => {
    const { agent } = req.query;
    
    if (!agent) {
      return res.status(400).json({
        status: 'error',
        error: 'Missing required query parameter: agent'
      });
    }
    
    const session = neo4jDriver.session();
    try {
      const result = await session.run(`
        MATCH (sub:Agent {id: $agent_id})-[s:SUBSCRIBES_TO]->(target)
        RETURN s.id as id,
               s.topic as topic,
               s.filter as filter,
               s.created_at as created_at,
               s.target_id as target_id,
               target.id as target_agent_id
      `, { agent_id: agent });
      
      const subscriptions = result.records.map(r => ({
        id: r.get('id'),
        topic: r.get('topic'),
        filter: r.get('filter') ? JSON.parse(r.get('filter')) : null,
        created_at: r.get('created_at'),
        target_id: r.get('target_id') || r.get('target_agent_id')
      }));
      
      res.json({
        status: 'success',
        agent: agent,
        subscriptions: subscriptions
      });
    } catch (error) {
      res.status(500).json({
        status: 'error',
        error: error.message
      });
    } finally {
      await session.close();
    }
  });

  /**
   * DELETE /api/subscriptions/:id
   * Remove a subscription by ID
   */
  router.delete('/subscriptions/:id', async (req, res) => {
    const { id } = req.params;
    
    const session = neo4jDriver.session();
    try {
      const result = await session.run(`
        MATCH ()-[s:SUBSCRIBES_TO {id: $sub_id}]->()
        DELETE s
        RETURN count(s) as removed
      `, { sub_id: id });
      
      const removed = result.single().get('removed');
      
      if (removed === 0) {
        return res.status(404).json({
          status: 'not_found',
          error: 'Subscription not found'
        });
      }
      
      res.json({
        status: 'success',
        removed: removed,
        subscription_id: id
      });
    } catch (error) {
      res.status(500).json({
        status: 'error',
        error: error.message
      });
    } finally {
      await session.close();
    }
  });

  /**
   * POST /api/events/dispatch
   * Trigger event dispatch to subscribers
   * Body: { event_type, payload, publisher?, target? }
   */
  router.post('/events/dispatch', async (req, res) => {
    const { event_type, payload, publisher = 'system', target } = req.body;
    
    if (!event_type) {
      return res.status(400).json({
        status: 'error',
        error: 'Missing required field: event_type'
      });
    }
    
    const session = neo4jDriver.session();
    try {
      const notificationId = require('uuid').v4();
      
      // Find matching subscribers
      let subscriberQuery = `
        MATCH (sub:Agent)-[s:SUBSCRIBES_TO]->(target)
        WHERE s.topic = $topic 
           OR s.topic = '*'
           OR $topic STARTS WITH replace(s.topic, '.*', '.')
      `;
      
      if (target) {
        subscriberQuery += `
          AND (s.target_id = $target OR s.target_id = '*')
        `;
      }
      
      subscriberQuery += `
        RETURN sub.id as subscriber_id,
               s.id as subscription_id,
               s.filter as filter,
               s.topic as subscription_topic
      `;
      
      const subResult = await session.run(subscriberQuery, { 
        topic: event_type,
        target: target
      });
      
      const subscribers = subResult.records.map(r => ({
        agent_id: r.get('subscriber_id'),
        subscription_id: r.get('subscription_id'),
        filter: r.get('filter') ? JSON.parse(r.get('filter')) : null,
        topic: r.get('subscription_topic')
      }));
      
      // Log notification
      await session.run(`
        CREATE (n:NotificationLog {
          id: $id,
          topic: $topic,
          payload: $payload,
          publisher: $publisher,
          timestamp: datetime(),
          subscriber_count: $count,
          status: 'dispatched'
        })
      `, {
        id: notificationId,
        topic: event_type,
        payload: JSON.stringify(payload || {}),
        publisher: publisher,
        count: subscribers.length
      });
      
      // Create delivery relationships
      for (const sub of subscribers) {
        await session.run(`
          MATCH (n:NotificationLog {id: $notif_id})
          MATCH (a:Agent {id: $agent_id})
          CREATE (n)-[:DELIVERED_TO {
            timestamp: datetime(),
            status: 'delivered',
            subscription_id: $sub_id
          }]->(a)
        `, {
          notif_id: notificationId,
          agent_id: sub.agent_id,
          sub_id: sub.subscription_id
        });
      }
      
      res.json({
        status: 'dispatched',
        notification_id: notificationId,
        topic: event_type,
        publisher: publisher,
        timestamp: new Date().toISOString(),
        subscriber_count: subscribers.length,
        subscribers: subscribers.map(s => s.agent_id)
      });
    } catch (error) {
      res.status(500).json({
        status: 'error',
        error: error.message
      });
    } finally {
      await session.close();
    }
  });

  /**
   * GET /api/events/logs
   * Get notification logs
   * Query: topic?, status?, limit?
   */
  router.get('/events/logs', async (req, res) => {
    const { topic, status, limit = 100 } = req.query;
    
    const session = neo4jDriver.session();
    try {
      let query = `
        MATCH (n:NotificationLog)
        WHERE 1=1
      `;
      const params = { limit: parseInt(limit) };
      
      if (topic) {
        query += ` AND n.topic = $topic`;
        params.topic = topic;
      }
      
      if (status) {
        query += ` AND n.status = $status`;
        params.status = status;
      }
      
      query += `
        RETURN n.id as id,
               n.topic as topic,
               n.payload as payload,
               n.publisher as publisher,
               n.timestamp as timestamp,
               n.status as status,
               n.subscriber_count as subscriber_count
        ORDER BY n.timestamp DESC
        LIMIT $limit
      `;
      
      const result = await session.run(query, params);
      
      const logs = result.records.map(r => ({
        id: r.get('id'),
        topic: r.get('topic'),
        payload: r.get('payload') ? JSON.parse(r.get('payload')) : null,
        publisher: r.get('publisher'),
        timestamp: r.get('timestamp'),
        status: r.get('status'),
        subscriber_count: r.get('subscriber_count')
      }));
      
      res.json({
        status: 'success',
        count: logs.length,
        logs: logs
      });
    } catch (error) {
      res.status(500).json({
        status: 'error',
        error: error.message
      });
    } finally {
      await session.close();
    }
  });

  return router;
}

module.exports = { createRoutes };
