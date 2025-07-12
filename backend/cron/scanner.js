const { supabase } = require('../services/supabaseService.js');
const { scrapeBookings } = require('../services/turoScraper.js');

async function startScanner() {
  console.log('Running scan...');
  const { data: users } = await supabase.from('users').select('*');
  for (let user of users) {
    if (user.tier === 'free' && user.scansToday >= 4) continue;
    try {
      await scrapeBookings(user.turoCredentials);
      await supabase.from('users').update({ scansToday: user.scansToday + 1 }).eq('id', user.id);
    } catch (err) {
      console.error(`Scan failed for user ${user.id}:`, err);
    }
  }
}

module.exports = { startScanner }; 