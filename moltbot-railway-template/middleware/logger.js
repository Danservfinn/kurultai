/**
 * Structured Request Logger Middleware
 *
 * Logs every HTTP request in structured JSON format for Railway log aggregation.
 * Captures: method, path, statusCode, duration, ip, user-agent, and auth user.
 */

module.exports = function requestLogger(logger) {
  return (req, res, next) => {
    const start = Date.now();

    // Capture the original end to measure response time
    const originalEnd = res.end;
    res.end = function (...args) {
      const duration = Date.now() - start;

      logger.info('request', {
        method: req.method,
        path: req.path,
        statusCode: res.statusCode,
        duration,
        ip: req.ip || req.headers['x-real-ip'] || req.connection.remoteAddress,
        userAgent: req.get('user-agent'),
        user: req.headers['x-authentik-username'] || undefined,
        contentLength: res.get('content-length') || 0,
      });

      originalEnd.apply(res, args);
    };

    next();
  };
};
