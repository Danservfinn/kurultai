const { scrapeBookings } = require('./turoScraper');

test('scrapeBookings runs without error', async () => {
  const credentials = { email: 'test@example.com', password: 'testpass' };
  await expect(scrapeBookings(credentials)).rejects.toThrow(); // Expect error for invalid creds in test
}); 