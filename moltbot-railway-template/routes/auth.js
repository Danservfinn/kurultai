/**
 * Auth Routes - Exposes Authentik user info from proxy headers
 *
 * The Caddy forward_auth proxy injects X-Authentik-* headers after
 * successful authentication. This endpoint exposes that info to the
 * frontend via a simple API call.
 */

const express = require('express');
const router = express.Router();

/**
 * GET /api/auth/me
 * Returns the authenticated user's info from Authentik headers.
 */
router.get('/me', (req, res) => {
  const username = req.headers['x-authentik-username'];
  const email = req.headers['x-authentik-email'];
  const name = req.headers['x-authentik-name'];
  const uid = req.headers['x-authentik-uid'];
  const groups = req.headers['x-authentik-groups'];

  if (!username) {
    return res.status(401).json({
      authenticated: false,
      error: 'No authentication headers present',
    });
  }

  res.json({
    authenticated: true,
    user: {
      username,
      email: email || '',
      name: name || '',
      uid: uid || '',
      groups: groups ? groups.split('|').filter(Boolean) : [],
    },
  });
});

module.exports = router;
