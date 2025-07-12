const express = require('express');
const { getAnalytics } = require('../controllers/analyticsController.js');
const router = express.Router();

router.get('/', getAnalytics);

module.exports = router; 