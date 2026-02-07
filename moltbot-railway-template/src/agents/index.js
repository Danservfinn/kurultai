/**
 * Agents Module Index
 *
 * Exports all agent handlers for Ögedei (Operations)
 * and Temüjin (Development).
 */

const { OgedeiVetHandler } = require('./ogedei/vet-handler');
const { TemujinImplHandler } = require('./temujin/impl-handler');

module.exports = {
  OgedeiVetHandler,
  TemujinImplHandler
};
