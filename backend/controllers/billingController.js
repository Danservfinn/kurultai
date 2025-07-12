const { createSubscription } = require('../services/stripeService.js');

async function upgradeTier(req, res) {
  try {
    const { tier } = req.body;
    const userId = 'placeholder';
    const subscription = await createSubscription(userId, tier);
    res.json({ url: subscription.url }); // For checkout
  } catch (err) {
    res.status(500).json({ error: 'Upgrade failed' });
  }
}

module.exports = { upgradeTier }; 