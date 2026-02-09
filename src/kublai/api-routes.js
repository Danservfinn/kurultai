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

  return router;
}

module.exports = { createRoutes };
