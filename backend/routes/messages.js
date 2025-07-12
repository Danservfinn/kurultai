const express = require('express');
const { getMessages, generateReply } = require('../controllers/messagesController.js');
const router = express.Router();

router.get('/', getMessages);
router.post('/reply', generateReply);

module.exports = router; 