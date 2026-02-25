const express = require('express');
const neo4j = require('neo4j-driver');
require('dotenv').config();

const app = express();
app.use(express.json());

// Neo4j driver
const driver = neo4j.driver(
  process.env.NEO4J_URI || 'bolt://localhost:7687',
  neo4j.auth.basic(
    process.env.NEO4J_USER || 'neo4j',
    process.env.NEO4J_PASSWORD || 'myStrongPassword123'
  )
);

// Health endpoints
app.get('/health', (req, res) => res.json({ status: 'ok', service: 'kublai-self-awareness' }));

// Architecture introspection
app.get('/api/architecture/overview', async (req, res) => {
  const session = driver.session();
  try {
    const result = await session.run('MATCH (s:ArchitectureSection) RETURN s.title as title, s.order as order ORDER BY s.order');
    res.json(result.records.map(r => ({ title: r.get('title'), order: r.get('order') })));
  } finally {
    await session.close();
  }
});

app.get('/api/architecture/search', async (req, res) => {
  const { q } = req.query;
  const session = driver.session();
  try {
    const result = await session.run(`
      CALL db.index.fulltext.queryNodes('architecture_search_index', $query)
      YIELD node, score
      RETURN node.title as title, score
      ORDER BY score DESC
      LIMIT 10
    `, { query: q });
    res.json(result.records.map(r => ({ title: r.get('title'), score: r.get('score') })));
  } finally {
    await session.close();
  }
});

// Proposal management
app.get('/api/proposals', async (req, res) => {
  const { status } = req.query;
  const session = driver.session();
  try {
    let query = 'MATCH (p:ArchitectureProposal)';
    if (status) query += ' WHERE p.status = $status';
    query += ' RETURN p.id as id, p.title as title, p.status as status, p.created_at as created_at ORDER BY p.created_at DESC';
    const result = await session.run(query, { status });
    res.json(result.records.map(r => ({
      id: r.get('id'),
      title: r.get('title'),
      status: r.get('status'),
      created_at: r.get('created_at')
    })));
  } finally {
    await session.close();
  }
});

// Workflow control
app.post('/api/workflow/process', async (req, res) => {
  res.json({ message: 'Workflow processing triggered', timestamp: new Date().toISOString() });
});

app.get('/api/workflow/status/:id', async (req, res) => {
  const { id } = req.params;
  const session = driver.session();
  try {
    const result = await session.run(`
      MATCH (p:ArchitectureProposal {id: $id})
      RETURN p.status as status, p.implementation_status as impl_status
    `, { id });
    if (result.records.length === 0) {
      return res.status(404).json({ error: 'Proposal not found' });
    }
    res.json({
      id,
      status: result.records[0].get('status'),
      implementation_status: result.records[0].get('impl_status')
    });
  } finally {
    await session.close();
  }
});

const PORT = process.env.PORT || 8082;
app.listen(PORT, () => {
  console.log(`Kublai Self-Awareness API running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('Shutting down...');
  await driver.close();
  process.exit(0);
});
