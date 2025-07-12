require('dotenv').config();
const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const cron = require('node-cron');
const routes = require('./routes/index.js');
const { startScanner } = require('./cron/scanner.js');
const { supabase } = require('./services/supabaseService.js');

// Auth middleware
async function authMiddleware(req, res, next) {
  const token = req.headers.authorization?.split('Bearer ')[1];
  if (!token) return res.status(401).json({ error: 'No token provided' });
  const { data: { user }, error } = await supabase.auth.getUser(token);
  if (error) return res.status(401).json({ error: 'Invalid token' });
  req.user = user;
  next();
}

const app = express();
const port = process.env.PORT || 3000;

app.use(cors());
app.use(bodyParser.json());
app.use('/api', authMiddleware, routes);

// Error handling middleware
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).send('Something broke!');
});

// Start cron jobs
cron.schedule('*/15 * * * *', startScanner); // Every 15 min

app.listen(port, () => {
  console.log(`Server running on port ${port}`);
}); 