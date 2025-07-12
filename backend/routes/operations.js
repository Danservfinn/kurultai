const express = require('express');
const { scheduleCleaning } = require('../controllers/operationsController.js');
const router = express.Router();

router.post('/schedule', scheduleCleaning);

module.exports = router; 