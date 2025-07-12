const { scrapeBookings } = require('../services/turoScraper.js');

// Placeholder userId from auth; in real, use middleware
async function getBookings(req, res) {
  try {
    const userId = req.user.id;
    // Fetch from DB or scrape
    res.json([{ id: '1', status: 'pending', rating: 4.6 }]);
  } catch (err) {
    res.status(500).json({ error: 'Failed to get bookings' });
  }
}

async function scanBookings(req, res) {
  try {
    const userCredentials = { email: 'test', password: 'test' }; // Fetch from DB
    const bookings = await scrapeBookings(userCredentials);
    res.json(bookings);
  } catch (err) {
    res.status(500).json({ error: 'Scan failed' });
  }
}

module.exports = { getBookings, scanBookings }; 