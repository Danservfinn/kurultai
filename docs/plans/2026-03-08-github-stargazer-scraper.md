# GitHub Stargazer Scraper for Claude Code Community Discovery

## Objective
Build a Python script to scrape stargazers of `anthropics/claude-code`, extract social links from profiles, identify active contributors, and output structured data to CSV.

## Phase 1: Script Development

### Task 1.1: Create Core Scraper Script
Create `/Users/kublai/.openclaw/scripts/github_stargazer_scraper.py` with:
- GitHub API client (REST API v3)
- Stargazer fetcher with pagination
- Profile data extractor (Twitter, blog, location)
- Rate limit handling
- CSV output writer

### Task 1.2: Implement Data Collection
- Fetch stargazers list with pagination (100 per page)
- For each stargazer, fetch profile details
- Extract: username, twitter_handle, blog_url, location, bio
- Optional: Check for recent activity (commits, issues, PRs)

### Task 1.3: Add Rate Limit Respect
- Detect rate limit from API headers
- Sleep when approaching limit
- Support both authenticated (5000/hr) and unauthenticated (60/hr) modes
- Resume capability with checkpoint

### Exit Criteria Phase 1
- [ ] Script created at target location
- [ ] Script runs without errors
- [ ] Handles pagination correctly
- [ ] Respects rate limits

## Phase 2: Testing and Execution

### Task 2.1: Test with Limited Sample
- Run script with `--limit 100` to test functionality
- Verify CSV output format
- Check data quality (Twitter handles, blog URLs)

### Task 2.2: Execute Full Collection
- Run for initial batch of 100+ users
- Save to `/Users/kublai/.openclaw/data/claude-code-community.csv`

### Exit Criteria Phase 2
- [ ] Initial dataset of 100+ users collected
- [ ] CSV file created with all required columns
- [ ] Twitter handles extracted where available
- [ ] Script documented with usage instructions

## Technical Approach

### GitHub API Endpoints
- `GET /repos/{owner}/{repo}/stargazers` - List stargazers
- `GET /users/{username}` - Get user profile
- `GET /users/{username}/repos` - Check recent activity (optional)

### Rate Limits
- Unauthenticated: 60 requests/hour
- Authenticated (GITHUB_TOKEN): 5000 requests/hour

### Output Format (CSV)
```
github_username,twitter_handle,blog_url,location,bio,recent_activity,last_fetched
```

### Error Handling
- Graceful failure on individual user fetch errors
- Log errors but continue processing
- Checkpoint every 100 users for resume capability

## Success Metrics
- 100+ users collected
- Twitter handle extraction rate >10% (where available)
- Script reusable for other repositories
