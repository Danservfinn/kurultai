const express = require('express');
const { saveCredentials } = require('../controllers/settingsController.js');
const router = express.Router();

router.post('/credentials', saveCredentials);

module.exports = router; 