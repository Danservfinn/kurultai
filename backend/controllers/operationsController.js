const { sendSMS } = require('../services/twilioService.js');

async function scheduleCleaning(req, res) {
  try {
    const { tripId, cleanerPhone } = req.body;
    const message = `Prep car for trip ${tripId} at 2PM`; // From scrape
    await sendSMS(cleanerPhone, message);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Scheduling failed' });
  }
}

module.exports = { scheduleCleaning }; 