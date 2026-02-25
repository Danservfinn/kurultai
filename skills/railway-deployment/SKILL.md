# Railway Deployment Skill

**Name:** railway-deployment  
**Version:** 1.0.0  
**Description:** Manage deployments for the parse project on Railway, including updating dev environment and promoting to production.

---

## 1. OVERVIEW

### Purpose
This skill provides comprehensive instructions for managing Railway deployments for the parse project, with clear workflows for updating the dev environment and safely promoting changes to production.

### When to Use
- Deploying new code to dev environment
- Updating environment variables
- Promoting dev changes to production
- Debugging deployment issues
- Rolling back problematic deployments

### Prerequisites
- Railway CLI installed and authenticated
- Access to parse project (danservfinn@gmail.com)
- Both dev and production environment access

---

## 2. ENVIRONMENTS

| Environment | ID | Purpose |
|-------------|-----|---------|
| **Dev** | `6eeb0167-dc20-4cba-bff9-2ba6195f4ced` | Development, testing, staging |
| **Production** | `ddffb290-bd85-46bf-afaf-a9fedc9b4545` | Live production environment |
| **Project** | `fca280f7-9d85-4fc4-afee-2856f7ec619b` | Parse project identifier |

### Quick Environment Switch

```bash
# To Dev
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment 6eeb0167-dc20-4cba-bff9-2ba6195f4ced

# To Production
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment ddffb290-bd85-46bf-afaf-a9fedc9b4545
```

---

## 3. WORKFLOWS

### WORKFLOW A: Update Dev Environment

#### Step 1: Link to Dev
```bash
cd ~/kurultai/kublai-repo
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment 6eeb0167-dc20-4cba-bff9-2ba6195f4ced
railway status
```

#### Step 2: Check Current Status
```bash
# View current deployment
railway deployment list

# View recent logs
railway logs --lines 50

# Check environment variables
railway variable list
```

#### Step 3: Update Code (if needed)
```bash
# Pull latest changes
git pull origin main

# Or checkout specific branch
git checkout feature-branch
```

#### Step 4: Update Environment Variables (if needed)
```bash
# Set a new variable
railway variable set KEY=value

# Update existing variable
railway variable set EXISTING_KEY=new_value

# Remove a variable
railway variable delete OLD_KEY
```

#### Step 5: Deploy to Dev
```bash
# Deploy current directory
railway up

# Or deploy specific service
railway up --service service-name
```

#### Step 6: Verify Deployment
```bash
# Check deployment status
railway deployment list

# View live logs
railway logs --follow

# Verify environment variables
railway variable list
```

---

### WORKFLOW B: Promote Dev to Production

⚠️ **CRITICAL: This workflow requires human confirmation before production deployment.**

#### Step 1: Verify Dev is Working
```bash
# Link to dev
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment 6eeb0167-dc20-4cba-bff9-2ba6195f4ced

# Check dev deployment status
railway deployment list
railway logs --lines 100

# Verify all tests pass
# (Run your test suite here)
```

**CHECKPOINT: Confirm with human that dev is stable before proceeding.**

#### Step 2: Link to Production
```bash
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment ddffb290-bd85-46bf-afaf-a9fedc9b4545
railway status
```

#### Step 3: Backup Current Production
```bash
# Backup environment variables
railway variable list > prod-backup-$(date +%Y%m%d-%H%M%S).env

# Document current deployment
railway deployment list | head -5 > prod-deployment-backup.txt
```

#### Step 4: Sync Environment Variables
```bash
# Get dev variables
dev_vars=$(railway variable list --json)

# Set production variables to match dev (BE CAREFUL)
# Only sync safe variables, not secrets
railway variable set SAFE_VAR=value
```

**CHECKPOINT: Confirm variable sync with human before deployment.**

#### Step 5: Deploy to Production
```bash
# Deploy current code (should match dev)
railway up
```

#### Step 6: Verify Production
```bash
# Check deployment status
railway deployment list

# Monitor logs for errors
railway logs --follow

# Verify health checks pass
# (Run your health check endpoint)
```

#### Step 7: Rollback Plan (if needed)
If issues detected:
```bash
# Get previous deployment ID
railway deployment list

# Rollback to previous deployment
railway deployment rollback DEPLOYMENT_ID

# Or restore variables from backup
# (Manual process using backup file)
```

---

## 4. COMMANDS REFERENCE

### Environment Management
```bash
# Check current status
railway status

# List all projects
railway list

# Link to specific project/environment
railway link --project PROJECT_ID --environment ENV_ID
```

### Variable Management
```bash
# List all variables
railway variable list

# Set a variable
railway variable set KEY=value

# Delete a variable
railway variable delete KEY

# Get specific variable
railway variable get KEY
```

### Deployment Management
```bash
# Deploy current directory
railway up

# List deployments
railway deployment list

# View deployment logs
railway logs

# View specific deployment logs
railway logs DEPLOYMENT_ID

# Follow logs in real-time
railway logs --follow

# View last N lines
railway logs --lines 100

# Rollback deployment
railway deployment rollback DEPLOYMENT_ID

# Redeploy without rebuilding
railway redeploy

# Restart service
railway restart
```

### Service Management
```bash
# List services
railway service list

# View service logs
railway logs --service SERVICE_NAME

# Scale service
railway scale --service SERVICE_NAME --replicas 2
```

---

## 5. SAFETY CHECKS

### Pre-Deployment Checklist (Production)

Before deploying to production, verify:

- [ ] Dev environment is stable and tested
- [ ] All automated tests pass
- [ ] Environment variables are correctly configured
- [ ] Database migrations are safe (if applicable)
- [ ] Rollback plan is documented
- [ ] Human approval obtained

### Human Confirmation Triggers

**ALWAYS ask for human confirmation before:**
- Deploying to production
- Deleting or modifying production environment variables
- Executing rollback procedures
- Scaling production services

### Rollback Procedure

If production deployment fails:

1. **Immediate:** Stop the deployment if still in progress
   ```bash
   railway deployment cancel
   ```

2. **Identify last good deployment:**
   ```bash
   railway deployment list
   ```

3. **Rollback:**
   ```bash
   railway deployment rollback DEPLOYMENT_ID
   ```

4. **Verify rollback:**
   ```bash
   railway logs
   railway status
   ```

5. **Restore variables (if needed):**
   ```bash
   # From backup file
   source prod-backup-DATE.env
   railway variable set KEY=value
   ```

---

## 6. EXAMPLES

### Example 1: Quick Dev Update
```bash
# Link to dev
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment 6eeb0167-dc20-4cba-bff9-2ba6195f4ced

# Pull latest
git pull origin main

# Deploy
railway up

# Check logs
railway logs --follow
```

### Example 2: Add Environment Variable to Dev
```bash
# Link to dev
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment 6eeb0167-dc20-4cba-bff9-2ba6195f4ced

# Set new variable
railway variable set NEW_API_KEY=secret_value

# Verify
railway variable list | grep NEW_API_KEY

# Deploy to apply
railway up
```

### Example 3: Promote Dev to Production (Full)
```bash
# Step 1: Verify dev
cd ~/kurultai/kublai-repo
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment 6eeb0167-dc20-4cba-bff9-2ba6195f4ced
railway deployment list
railway logs --lines 50

# HUMAN: Confirm dev is stable

# Step 2: Backup production
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment ddffb290-bd85-46bf-afaf-a9fedc9b4545
railway variable list > prod-backup-$(date +%Y%m%d).env

# Step 3: Deploy to production
railway up

# Step 4: Verify
railway deployment list
railway logs --follow

# HUMAN: Confirm production is working
```

### Example 4: Rollback Production
```bash
# Link to production
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment ddffb290-bd85-46bf-afaf-a9fedc9b4545

# List deployments to find last good one
railway deployment list

# Rollback (replace with actual deployment ID)
railway deployment rollback DEPLOYMENT_ID

# Verify rollback
railway logs --follow
railway status
```

---

## 7. TROUBLESHOOTING

### Common Issues

**Issue: "No linked project found"**
```bash
# Solution: Link to project
railway link --project fca280f7-9d85-4fc4-afee-2856f7ec619b --environment ENV_ID
```

**Issue: Deployment fails**
```bash
# Check logs for errors
railway logs --lines 100

# Verify environment variables
railway variable list

# Check if service is running
railway status
```

**Issue: Variables not updating**
```bash
# Verify variable is set
railway variable get KEY

# Redeploy to apply changes
railway up
```

---

## 8. NOTES

- Always verify which environment you're linked to before making changes
- Production deployments require human confirmation
- Keep backups of production environment variables
- Monitor logs after every deployment
- Use `railway status` frequently to verify state

