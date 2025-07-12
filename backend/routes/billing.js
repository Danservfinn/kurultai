const express = require('express');
const { upgradeTier } = require('../controllers/billingController.js');
const router = express.Router();

router.post('/upgrade', upgradeTier);

module.exports = router; 