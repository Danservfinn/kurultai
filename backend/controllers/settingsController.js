const { supabase } = require('../services/supabaseService.js');

async function saveCredentials(req, res) {
  try {
    const { turoEmail, turoPassword } = req.body;
    const userId = 'placeholder'; // From auth
    await supabase.from('users').update({ turoCredentials: { email: turoEmail, password: turoPassword } }).eq('id', userId);
    res.json({ success: true });
  } catch (err) {
    console.error('Save credentials error:', err);
    res.status(500).json({ error: 'Failed to save credentials' });
  }
}

module.exports = { saveCredentials }; 