async function getAnalytics(req, res) {
  try {
    // Assume scraped data fetched
    const bookings = []; // Fetch from DB or scrape
    const occupancy = (bookings.filter(b => b.status === 'booked').length / bookings.length) * 100 || 0;
    const suggestions = occupancy < 50 ? 'Lower rates to increase bookings' : 'Good performance';
    res.json({ occupancy, suggestions });
  } catch (err) {
    res.status(500).json({ error: 'Analytics failed' });
  }
}

module.exports = { getAnalytics }; 