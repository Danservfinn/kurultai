const express = require('express');
const { getBookings, scanBookings } = require('../controllers/bookingsController.js');
const router = express.Router();

router.get('/', getBookings);
router.post('/scan', scanBookings);

module.exports = router; 