const { generateReply: aiGenerateReply } = require('../services/aiService.js');

async function getMessages(req, res) {
  try {
    // Scrape or from DB
    res.json([{ id: '1', content: 'Where is pickup?' }]);
  } catch (err) {
    res.status(500).json({ error: 'Failed to get messages' });
  }
}

async function generateReply(req, res) {
  try {
    const { messageId } = req.body;
    const history = [{ role: 'user', content: 'Where is pickup?' }]; // From scrape
    const reply = await aiGenerateReply(history);
    // Send via scraper
    res.json({ reply });
  } catch (err) {
    res.status(500).json({ error: 'Reply generation failed' });
  }
}

module.exports = { getMessages, generateReply }; 