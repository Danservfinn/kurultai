# FinVault Pro - Threat Model Documentation

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Web App     │  │ Mobile App   │  │  API Clients │  │   Partners   │    │
│  │  (React)     │  │ (iOS/Android)│  │   (SDK)      │  │   (B2B)      │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
└─────────┼─────────────────┼─────────────────┼─────────────────┼────────────┘
          │                 │                 │                 │
          └─────────────────┴────────┬────────┴─────────────────┘
                                     │
┌────────────────────────────────────┴────────────────────────────────────────┐
│                           EDGE SECURITY LAYER                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  CDN (DDoS Protection)  →  WAF  →  Load Balancer  →  Rate Limiter   │   │
│  │  • AWS CloudFront       • AWS WAF   • ALB            • Redis        │   │
│  │  • DDoS Shield          • OWASP CRS • Health checks  • Token bucket │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┴────────────────────────────────────────┐
│                           APPLICATION LAYER                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Kubernetes Cluster (EKS)                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │  API Gateway │  │ Auth Service │  │  Transaction │               │   │
│  │  │  (Kong/AWS)  │  │   (OAuth2)   │  │   Service    │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │   Payment    │  │ Notification │  │   Reporting  │               │   │
│  │  │   Service    │  │   Service    │  │   Service    │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┴────────────────────────────────────────┐
│                            DATA LAYER                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ PostgreSQL   │  │    Redis     │  │ Elasticsearch│  │   Kafka      │    │
│  │ (Encrypted)  │  │   (Cache)    │  │   (Search)   │  │  (Events)    │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │
│  │     S3       │  │   DynamoDB   │  │   HSM        │                       │
│  │  (Documents) │  │  (Sessions)  │  │ (Key Mgmt)   │                       │
│  └──────────────┘  └──────────────┘  └──────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┴────────────────────────────────────────┐
│                         EXTERNAL INTEGRATIONS                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   SWIFT      │  │    ACH       │  │   Card       │  │   KYC/AML    │    │
│  │   Network    │  │   Network    │  │  Networks    │  │  Providers   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## STRIDE Threat Analysis

### 1. SPOOFING (Identity Spoofing)

| Threat ID | Description | Attack Vector | Impact | Likelihood | Risk |
|-----------|-------------|---------------|--------|------------|------|
| S-001 | Credential stuffing attack | Automated login attempts with stolen credentials | Account takeover | High | Critical |
| S-002 | Session hijacking | Theft of session tokens via XSS or network sniffing | Unauthorized access | Medium | High |
| S-003 | JWT algorithm confusion | alg:none token injection | Authentication bypass | Low | Critical |
| S-004 | OAuth redirect manipulation | Malicious redirect_uri exploitation | Account takeover | Medium | High |
| S-005 | API key theft | Extraction from logs or client-side storage | API abuse | Medium | High |

**Mitigation Controls:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    SPOOFING DEFENSE LAYERS                       │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Strong Authentication                                   │
│   • MFA required for all accounts                               │
│   • Password policy: 16+ chars, complexity, breach check        │
│   • Biometric authentication for mobile                         │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Session Security                                        │
│   • Short-lived JWTs (15 min access, 7 day refresh)             │
│   • Secure, httpOnly, SameSite cookies                          │
│   • Device fingerprinting                                       │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Token Validation                                        │
│   • Explicit algorithm whitelist                                │
│   • Signature verification mandatory                            │
│   • Issuer/audience validation                                  │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Behavioral Analysis                                     │
│   • Anomaly detection on login patterns                         │
│   • Impossible travel detection                                 │
│   • Risk-based step-up authentication                           │
└─────────────────────────────────────────────────────────────────┘
```

---

### 2. TAMPERING (Data Modification)

| Threat ID | Description | Attack Vector | Impact | Likelihood | Risk |
|-----------|-------------|---------------|--------|------------|------|
| T-001 | Transaction amount manipulation | Intercept and modify API requests | Financial loss | Medium | Critical |
| T-002 | Database tampering | Direct database access or SQL injection | Data integrity loss | Low | Critical |
| T-003 | Audit log modification | Unauthorized access to logging systems | Repudiation | Low | Critical |
| T-004 | Configuration tampering | Unauthorized changes to security settings | System compromise | Medium | High |
| T-005 | Man-in-the-middle attacks | Network interception | Data modification | Low | Medium |

**Mitigation Controls:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    TAMPERING DEFENSE LAYERS                      │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Input Validation                                        │
│   • Strict schema validation on all inputs                      │
│   • Parameterized queries (no SQL injection)                    │
│   • Digital signatures on critical fields                       │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Integrity Protection                                    │
│   • HMAC on all transaction records                             │
│   • Immutable audit logs (WORM storage)                         │
│   • Blockchain anchoring for critical events                    │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Encryption                                              │
│   • TLS 1.3 for all communications                              │
│   • Field-level encryption for sensitive data                   │
│   • Certificate pinning for mobile apps                         │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Access Controls                                         │
│   • Principle of least privilege                                │
│   • Just-in-time access for sensitive operations                │
│   • Dual control for critical changes                           │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3. REPUDIATION (Denial of Actions)

| Threat ID | Description | Attack Vector | Impact | Likelihood | Risk |
|-----------|-------------|---------------|--------|------------|------|
| R-001 | Transaction denial | User claims they didn't initiate transfer | Dispute resolution cost | High | Medium |
| R-002 | Admin action denial | Administrator denies making changes | Accountability gap | Medium | Medium |
| R-003 | System modification denial | Attacker covers tracks | Forensic difficulty | Medium | High |
| R-004 | Audit gap exploitation | Missing logs for critical events | Compliance violation | Low | High |

**Mitigation Controls:**
```
┌─────────────────────────────────────────────────────────────────┐
│                   REPUDIATION DEFENSE LAYERS                     │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Comprehensive Logging                                   │
│   • All actions logged with user, timestamp, IP                 │
│   • Before/after state for modifications                        │
│   • Non-repudiation via digital signatures                      │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Immutable Storage                                       │
│   • Write-Once-Read-Many (WORM) storage                         │
│   • Append-only log databases                                   │
│   • Cross-site log replication                                  │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: User Acknowledgment                                     │
│   • Explicit confirmation for transactions                      │
│   • Email/SMS receipts for all actions                          │
│   • Digital signatures on high-value transactions               │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: External Validation                                     │
│   • Third-party audit trails                                    │
│   • Regulatory reporting integration                            │
│   • Blockchain notarization                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

### 4. INFORMATION DISCLOSURE (Data Leakage)

| Threat ID | Description | Attack Vector | Impact | Likelihood | Risk |
|-----------|-------------|---------------|--------|------------|------|
| I-001 | PAN data exposure | Unencrypted database storage | PCI violation | High | Critical |
| I-002 | API response over-exposure | Verbose error messages | Information leakage | High | High |
| I-003 | Log data exposure | Sensitive data in logs | Credential exposure | Medium | High |
| I-004 | IDOR attacks | Sequential IDs allowing enumeration | Unauthorized data access | Medium | High |
| I-005 | Backup exposure | Unencrypted backup storage | Mass data breach | Low | Critical |
| I-006 | Side-channel attacks | Timing analysis, error differentiation | Cryptographic key exposure | Low | Medium |

**Mitigation Controls:**
```
┌─────────────────────────────────────────────────────────────────┐
│                 INFORMATION DISCLOSURE DEFENSE                   │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Data Classification                                     │
│   • Automatic data classification                               │
│   • Labeling: Public, Internal, Confidential, Restricted        │
│   • Handling rules per classification                           │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Encryption                                              │
│   • AES-256 for data at rest                                    │
│   • TLS 1.3 for data in transit                                 │
│   • Tokenization for PAN data                                   │
│   • Field-level encryption for PII                              │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Access Controls                                         │
│   • Need-to-know data access                                    │
│   • Field-level permissions in APIs                             │
│   • Data masking in non-production                              │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Secure Development                                      │
│   • No sensitive data in logs                                   │
│   • Generic error messages                                      │
│   • Secure code review                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

### 5. DENIAL OF SERVICE (Availability Attacks)

| Threat ID | Description | Attack Vector | Impact | Likelihood | Risk |
|-----------|-------------|---------------|--------|------------|------|
| D-001 | DDoS attack | Volumetric network flood | Service outage | High | High |
| D-002 | Application layer DoS | Resource exhaustion attacks | Degraded performance | Medium | Medium |
| D-003 | Database overload | Expensive query attacks | Database unavailability | Medium | High |
| D-004 | Account lockout abuse | Intentional lockouts of victims | User denial of service | Medium | Medium |
| D-005 | Payment processing flood | Rapid transaction submission | Financial system overload | Low | High |

**Mitigation Controls:**
```
┌─────────────────────────────────────────────────────────────────┐
│                 DENIAL OF SERVICE DEFENSE                        │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Network Protection                                      │
│   • DDoS mitigation service (AWS Shield)                        │
│   • CDN for static content distribution                         │
│   • Geographic traffic distribution                             │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Application Protection                                  │
│   • Rate limiting per IP/user/endpoint                          │
│   • Circuit breakers for dependent services                     │
│   • Request size limits and timeouts                            │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Resource Management                                     │
│   • Auto-scaling based on load                                  │
│   • Database connection pooling                                 │
│   • Query complexity limits                                     │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Operational Response                                    │
│   • 24/7 SOC monitoring                                         │
│   • Automated incident response                                 │
│   • Failover to disaster recovery                               │
└─────────────────────────────────────────────────────────────────┘
```

---

### 6. ELEVATION OF PRIVILEGE (Unauthorized Access)

| Threat ID | Description | Attack Vector | Impact | Likelihood | Risk |
|-----------|-------------|---------------|--------|------------|------|
| E-001 | Role self-elevation | Mass assignment vulnerability | Admin access | Medium | Critical |
| E-002 | Horizontal privilege escalation | Access other users' data | Data breach | Medium | High |
| E-003 | Vertical privilege escalation | User to admin escalation | Full system compromise | Low | Critical |
| E-004 | Service account abuse | Compromised service credentials | Internal access | Medium | High |
| E-005 | Supply chain compromise | Malicious dependency | Backdoor installation | Low | Critical |

**Mitigation Controls:**
```
┌─────────────────────────────────────────────────────────────────┐
│              ELEVATION OF PRIVILEGE DEFENSE                      │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Strict Authorization                                    │
│   • Deny-by-default access control                              │
│   • Role-based access control (RBAC)                            │
│   • Attribute-based access control (ABAC)                       │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Input Validation                                        │
│   • Whitelist allowed fields in requests                        │
│   • Server-side authorization checks                            │
│   • No mass assignment vulnerabilities                          │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Privilege Management                                    │
│   • Just-in-time access elevation                               │
│   • Regular access reviews                                      │
│   • Automated privilege revocation                              │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Monitoring                                              │
│   • Privileged access monitoring                                │
│   • Anomaly detection for admin actions                         │
│   • Real-time alerting on elevation attempts                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Attack Scenarios

### Scenario 1: Account Takeover via Credential Stuffing

```
┌─────────────────────────────────────────────────────────────────┐
│ ATTACK FLOW: Credential Stuffing → Account Takeover              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. RECONNAISSANCE                                               │
│     └── Attacker obtains breached credentials from dark web     │
│         (email:password combinations)                           │
│                                                                  │
│  2. AUTOMATED ATTACK                                             │
│     └── Botnet attempts login with credential pairs             │
│         └── Rate: 1000 attempts/minute from distributed IPs     │
│                                                                  │
│  3. SUCCESSFUL COMPROMISE                                        │
│     └── Valid credentials found: user@company.com               │
│         └── No MFA required → Immediate access                  │
│                                                                  │
│  4. PRIVILEGE ESCALATION                                         │
│     └── Attacker modifies profile to add admin role             │
│         └── Mass assignment vulnerability allows elevation      │
│                                                                  │
│  5. DATA EXFILTRATION                                            │
│     └── Admin access to 50,000 customer records                 │
│         └── Bulk export to attacker-controlled server           │
│                                                                  │
│  6. FINANCIAL FRAUD                                              │
│     └── Wire transfers to mule accounts                         │
│         └── $2.3M transferred before detection                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

MITIGATION:
├── Rate limiting: 5 attempts per account per hour
├── CAPTCHA after 3 failed attempts
├── MFA mandatory for all accounts
├── Mass assignment prevention
├── Admin action alerting
└── Transaction anomaly detection
```

### Scenario 2: Insider Threat - Database Administrator

```
┌─────────────────────────────────────────────────────────────────┐
│ ATTACK FLOW: Malicious Insider Data Theft                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. ACCESS ACQUISITION                                           │
│     └── DBA has legitimate production database access           │
│         └── Access granted for performance tuning               │
│                                                                  │
│  2. PRIVILEGE ABUSE                                              │
│     └── DBA queries customer PII table directly                 │
│         └── No query logging or anomaly detection               │
│         └── SELECT * FROM customers LIMIT 100000                │
│                                                                  │
│  3. DATA EXTRACTION                                              │
│     └── Data exported to personal cloud storage                 │
│         └── No DLP controls on outbound traffic                 │
│                                                                  │
│  4. SALE ON DARK WEB                                             │
│     └── 100,000 customer records sold                           │
│         └── Includes SSNs, account numbers, addresses           │
│                                                                  │
│  5. DETECTION                                                    │
│     └── Discovered via external breach notification             │
│         └── 6 months after initial exfiltration                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

MITIGATION:
├── Just-in-time database access (temporary elevation)
├── Query logging and behavioral analysis
├── Data masking in production for non-essential roles
├── DLP on all outbound channels
├── Database activity monitoring (DAM)
└── Regular access reviews and recertification
```

### Scenario 3: Supply Chain Attack - Malicious Dependency

```
┌─────────────────────────────────────────────────────────────────┐
│ ATTACK FLOW: Supply Chain Compromise                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. TARGET IDENTIFICATION                                        │
│     └── Attacker identifies popular npm package                 │
│         └── Package: lodash-utils (2M downloads/week)           │
│                                                                  │
│  2. COMPROMISE                                                   │
│     └── Maintainer account compromised via phishing             │
│         └── Malicious version 4.17.21 published                 │
│                                                                  │
│  3. PAYLOAD DELIVERY                                             │
│     └── CI/CD pipeline pulls latest version                     │
│         └── No dependency pinning or checksum verification      │
│                                                                  │
│  4. EXECUTION                                                    │
│     └── Malicious code executes in production                   │
│         └── Backdoor opens reverse shell                        │
│                                                                  │
│  5. LATERAL MOVEMENT                                             │
│     └── Attacker explores internal network                      │
│         └── Discovers Kubernetes API                            │
│                                                                  │
│  6. DATA ACCESS                                                  │
│     └── Database credentials extracted from environment         │
│         └── Full customer database accessed                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

MITIGATION:
├── Dependency pinning in package files
├── SCA scanning in CI/CD (Snyk, Dependabot)
├── Private artifact repository with approval workflow
├── Network segmentation (zero-trust)
├── Runtime application self-protection (RASP)
└── SBOM generation and verification
```

---

## Data Flow Diagrams

### Authentication Flow

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  User   │────>│   Client    │────>│  API Gateway│────>│Auth Service │
│         │     │             │     │             │     │             │
└─────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                               │
                               ┌───────────────────────────────┘
                               │
                               ▼
                        ┌─────────────┐     ┌─────────────┐
                        │   Redis     │────>│  Database   │
                        │  (Session)  │     │  (Users)    │
                        └─────────────┘     └─────────────┘
                               │
                               │
                               ▼
                        ┌─────────────┐
                        │    MFA      │
                        │  Service    │
                        └─────────────┘

Security Controls:
├── TLS 1.3 for all connections
├── Rate limiting at API Gateway
├── Password hashing (Argon2id)
├── JWT with short expiry (15 min)
├── Refresh token rotation
└── Device fingerprinting
```

### Payment Processing Flow

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  User   │────>│   Client    │────>│  API Gateway│────>│  Payment    │
│         │     │             │     │  (WAF/Rate) │     │  Service    │
└─────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                               │
                               ┌───────────────────────────────┼──────────┐
                               │                               │          │
                               ▼                               ▼          ▼
                        ┌─────────────┐     ┌─────────────┐  ┌────────┐ ┌────────┐
                        │   Fraud     │────>│   Token     │  │  HSM   │ │Payment │
                        │  Detection  │     │   Vault     │  │(Keys)  │ │Network │
                        └─────────────┘     └─────────────┘  └────────┘ └────────┘

Security Controls:
├── Input validation and sanitization
├── Tokenization (PAN never stored)
├── HSM for cryptographic operations
├── Real-time fraud scoring
├── Dual control for high-value
├── Immutable audit logging
└── PCI-DSS compliant architecture
```

---

## Risk Matrix

```
                    IMPACT
           Low      Medium     High      Critical
         ┌─────────┬─────────┬─────────┬─────────┐
    High │ MEDIUM  │  HIGH   │ CRITICAL│ CRITICAL│
         │  D-002  │  I-004  │  S-001  │  T-002  │
         │  E-004  │  D-004  │  D-001  │  I-001  │
         ├─────────┼─────────┼─────────┼─────────┤
  Medium │  LOW    │ MEDIUM  │  HIGH   │ CRITICAL│
LIKELIHOOD│  I-006  │  R-001  │  S-002  │  E-001  │
         │  T-005  │  D-003  │  I-003  │  E-003  │
         ├─────────┼─────────┼─────────┼─────────┤
     Low │  LOW    │  LOW    │ MEDIUM  │  HIGH   │
         │  T-004  │  R-003  │  S-004  │  I-005  │
         │  D-005  │  E-005  │  T-003  │  E-002  │
         └─────────┴─────────┴─────────┴─────────┘
```

---

## Security Control Mapping

| Control Category | Implementation | Coverage |
|-----------------|----------------|----------|
| Authentication | OAuth 2.0 + OIDC, MFA, Biometrics | 85% |
| Authorization | RBAC + ABAC, Policy engine | 70% |
| Encryption | AES-256-GCM, TLS 1.3, HSM | 90% |
| Monitoring | SIEM, UEBA, DLP | 75% |
| Network Security | Zero-trust, Micro-segmentation | 80% |
| Application Security | SAST/DAST, RASP, WAF | 65% |
| Data Protection | Tokenization, Masking, Classification | 60% |
| Incident Response | SOAR, Playbooks, 24/7 SOC | 70% |
