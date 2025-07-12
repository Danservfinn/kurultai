const express = require('express');
const router = express.Router();

router.use('/auth', require('./auth.js'));
router.use('/bookings', require('./bookings.js'));
router.use('/messages', require('./messages.js'));
router.use('/operations', require('./operations.js'));
router.use('/analytics', require('./analytics.js'));
router.use('/billing', require('./billing.js'));
router.use('/settings', require('./settings.js'));

module.exports = router; 