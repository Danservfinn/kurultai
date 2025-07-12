const OpenAI = require('openai');
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

async function generateReply(messageHistory) {
  try {
    const completion = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [{ role: 'system', content: 'Generate human-like reply for Turo host.' }, ...messageHistory],
    });
    return completion.choices[0].message.content;
  } catch (err) {
    console.error('AI error:', err);
    throw err;
  }
}

module.exports = { generateReply }; 