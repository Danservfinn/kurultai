const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

async function createSubscription(userId, plan) {
  const customer = await stripe.customers.create({ metadata: { userId } });
  const subscription = await stripe.subscriptions.create({
    customer: customer.id,
    items: [{ price: plan === 'basic' ? 'price_1YourBasicPriceIdHere' : 'price_1YourProPriceIdHere' }],
  });
  return subscription;
}

module.exports = { createSubscription }; 