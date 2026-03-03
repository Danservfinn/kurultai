# Security Rules - Kublai

## API Keys & Secrets
- NEVER commit API keys to git
- Use environment variables
- Store in .env files (gitignored)
- Rotate keys periodically

## Data Handling
- Never log sensitive data
- Sanitize user inputs
- Validate all external data
- Use parameterized queries for Neo4j

## Access Control
- Minimum necessary permissions
- Validate authentication before actions
- Log all access attempts
- Rate limit sensitive operations

## Common Vulnerabilities to Avoid
- SQL/Neo4j injection (use parameters)
- Command injection (sanitize shell inputs)
- Path traversal (validate file paths)
- Information disclosure (don't leak errors)

## Incident Response
1. Detect and log the incident
2. Contain the impact
3. Eradicate the root cause
4. Recover and restore
5. Learn and improve
