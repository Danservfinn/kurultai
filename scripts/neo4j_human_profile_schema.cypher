// =============================================================================
// Human Profile Storage System — Neo4j Schema Extension
// =============================================================================
//
// Extends the Signal Calendar Person node with rich profile information.
// Integrates with existing Kurultai Neo4j infrastructure.
//
// Design principles:
//   - HumanProfile extends Person (does not replace)
//   - Privacy-first with consent categories and privacy levels
//   - Dual storage: Neo4j for structured data, files for narrative context
//   - Natural language query support
//
// Run this after: signal-calendar-neo4j-schema.cypher
// Author: Chagatai
// Date: 2026-03-07
// =============================================================================


// ─────────────────────────────────────────────────────────────────────────────
// SECTION 1: CONSTRAINTS
// ─────────────────────────────────────────────────────────────────────────────

// HumanProfile — UUID-based primary key
CREATE CONSTRAINT human_profile_id_unique IF NOT EXISTS
FOR (h:HumanProfile) REQUIRE h.profile_id IS UNIQUE;

// ConsentCategory — name is unique
CREATE CONSTRAINT consent_category_name_unique IF NOT EXISTS
FOR (c:ConsentCategory) REQUIRE c.name IS UNIQUE;

// Tag — name is unique
CREATE CONSTRAINT tag_name_unique IF NOT EXISTS
FOR (t:Tag) REQUIRE t.name IS UNIQUE;


// ─────────────────────────────────────────────────────────────────────────────
// SECTION 2: INDEXES
// ─────────────────────────────────────────────────────────────────────────────

// HumanProfile: link to Person
CREATE INDEX human_profile_phone_e164_idx IF NOT EXISTS
FOR (h:HumanProfile) ON (h.phone_e164);

// HumanProfile: quick name lookup
CREATE INDEX human_profile_display_name_idx IF NOT EXISTS
FOR (h:HumanProfile) ON (h.display_name);

// HumanProfile: privacy-filtered queries
CREATE INDEX human_profile_privacy_idx IF NOT EXISTS
FOR (h:HumanProfile) ON (h.privacy_level);

// HumanProfile: consent-based queries
CREATE INDEX human_profile_consent_idx IF NOT EXISTS
FOR (h:HumanProfile) ON (h.consent_categories);

// HumanProfile: fulltext for natural language queries
CREATE FULLTEXT INDEX human_profile_search IF NOT EXISTS
FOR (h:HumanProfile) ON EACH [h.display_name, h.what_to_call, h.notes];


// ─────────────────────────────────────────────────────────────────────────────
// SECTION 3: NODE TYPE DEFINITIONS
// ─────────────────────────────────────────────────────────────────────────────

// ── HumanProfile ─────────────────────────────────────────────────────────────
// Extended profile information for humans the Kurultai interacts with.
// Linked to Person node via phone_e164 (which equals Person.phone_number).
//
// Properties:
//   profile_id          : String    (UUID, e.g., "hp-a1b2c3d4") — PRIMARY KEY
//   phone_e164          : String    (E.164 phone, links to Person.phone_number)
//   display_name        : String    (preferred display name)
//   what_to_call        : String    (how they want to be addressed)
//   pronouns            : String    (optional: "they/them", "she/her", etc.)
//   timezone            : String    (IANA: "America/New_York")
//   communication_style : Map       (JSON object with preferences)
//   preferences         : Map       (JSON object with user preferences)
//   projects            : Map       (JSON object with project context)
//   privacy_level       : String    ("public" | "contacts" | "private")
//   consent_categories  : [String]  (["calendar", "tasks", "research", ...])
//   source              : String    ("signal", "manual", "inferred")
//   confidence          : Float     (0.0-1.0, accuracy of profile data)
//   last_verified       : DateTime  (when human last confirmed info)
//   notes               : String    (free-form notes)
//   status              : String    ("active" | "anonymized" | "deleted")
//   created_at          : DateTime
//   updated_at          : DateTime
//
// Example:
// CREATE (h:HumanProfile {
//     profile_id: "hp-" + randomUUID(),
//     phone_e164: "+19194133445",
//     display_name: "Danny",
//     what_to_call: "Danny",
//     pronouns: "he/him",
//     timezone: "America/New_York",
//     communication_style: {
//         preferred_channel: "signal",
//         preferred_time: "morning",
//         response_style: "direct",
//         emoji_friendly: true,
//         detail_level: "brief",
//         formality: "casual"
//     },
//     preferences: {
//         response_time: "fast",
//         detail_level: "concise",
//         formatting: "markdown",
//         notifications: {signal: true, email: false}
//     },
//     projects: {
//         active: [{name: "Parse for Agents", role: "founder", priority: "high"}]
//     },
//     privacy_level: "contacts",
//     consent_categories: ["calendar", "tasks", "research"],
//     source: "signal",
//     confidence: 0.95,
//     last_verified: datetime(),
//     notes: "Coffee enthusiast, likes hiking",
//     status: "active",
//     created_at: datetime(),
//     updated_at: datetime()
// })


// ── ConsentCategory ──────────────────────────────────────────────────────────
// Tracks what a human has explicitly consented to.
//
// Properties:
//   name        : String ("calendar", "tasks", "research", "social", "marketing")
//   description : String (human-readable description)
//   created_at  : DateTime
//
// Example:
// CREATE (c:ConsentCategory {
//     name: "calendar",
//     description: "Store event preferences and availability",
//     created_at: datetime()
// })


// ── Tag ──────────────────────────────────────────────────────────────────────
// Flexible tagging for humans (e.g., "VIP", "engineering", "founder").
//
// Properties:
//   name        : String (tag name, lowercase)
//   description : String (optional description)
//   created_at  : DateTime


// ─────────────────────────────────────────────────────────────────────────────
// SECTION 4: RELATIONSHIP DEFINITIONS
// ─────────────────────────────────────────────────────────────────────────────

// ── LINKED_TO ────────────────────────────────────────────────────────────────
// (HumanProfile)-[:LINKED_TO]->(Person)
// Links HumanProfile to the existing Person node.
// Properties: created_at (DateTime)

// ── HAS_CONSENT ───────────────────────────────────────────────────────────────
// (HumanProfile)-[:HAS_CONSENT {granted_at, revoked_at}]->(ConsentCategory)
// Tracks consent with timestamps for audit.
// Properties:
//   granted_at  : DateTime (when consent was given)
//   revoked_at  : DateTime (nullable, set if revoked)
//   source      : String ("explicit", "inferred", "default")

// ── TAGGED_AS ─────────────────────────────────────────────────────────────────
// (HumanProfile)-[:TAGGED_AS {tagged_at, tagged_by}]->(Tag)
// Tags a human profile.
// Properties:
//   tagged_at : DateTime
//   tagged_by : String (agent name or phone number)

// ── UPDATED_BY ────────────────────────────────────────────────────────────────
// (HumanProfile)-[:UPDATED_BY {at, field}]->(Agent)
// Audit trail for profile updates.
// Properties:
//   at    : DateTime
//   field : String (which field was updated)

// ── KNOWS ─────────────────────────────────────────────────────────────────────
// (HumanProfile)-[:KNOWS {since, source}]->(HumanProfile)
// Social graph — humans who know each other (extracted from Signal groups).
// Properties:
//   since  : DateTime (when relationship was first observed)
//   source : String ("signal_group", "manual", "inferred")


// ─────────────────────────────────────────────────────────────────────────────
// SECTION 5: SEED DATA
// ─────────────────────────────────────────────────────────────────────────────

// Seed consent categories
MERGE (c1:ConsentCategory {name: "calendar"})
ON CREATE SET c1.description = "Store event preferences and availability",
              c1.created_at = datetime();

MERGE (c2:ConsentCategory {name: "tasks"})
ON CREATE SET c2.description = "Remember task assignments and progress",
              c2.created_at = datetime();

MERGE (c3:ConsentCategory {name: "research"})
ON CREATE SET c3.description = "Store research preferences and topics of interest",
              c3.created_at = datetime();

MERGE (c4:ConsentCategory {name: "social"})
ON CREATE SET c4.description = "Remember personal interests and social context",
              c4.created_at = datetime();

MERGE (c5:ConsentCategory {name: "marketing"})
ON CREATE SET c5.description = "Product updates and marketing communications",
              c5.created_at = datetime();

// Seed common tags
MERGE (t1:Tag {name: "vip"})
ON CREATE SET t1.description = "High priority human", t1.created_at = datetime();

MERGE (t2:Tag {name: "founder"})
ON CREATE SET t2.description = "Company founder", t2.created_at = datetime();

MERGE (t3:Tag {name: "engineering"})
ON CREATE SET t3.description = "Engineering/technical", t3.created_at = datetime();

MERGE (t4:Tag {name: "admin"})
ON CREATE SET t4.description = "System administrator", t4.created_at = datetime();


// ─────────────────────────────────────────────────────────────────────────────
// SECTION 6: QUERY PATTERNS
// ─────────────────────────────────────────────────────────────────────────────

// ── Q1: "What do I know about [person]?" — Full profile retrieval ────────────
// Parameters: $query (name or phone), $requester_phone (for privacy check)
//
// MATCH (hp:HumanProfile)
// WHERE toLower(hp.display_name) CONTAINS toLower($query)
//    OR hp.phone_e164 = $query
//    OR toLower($query) IN [x IN hp.aliases | toLower(x)]
// WITH hp LIMIT 1
// MATCH (hp)-[:LINKED_TO]->(p:Person)
// OPTIONAL MATCH (hp)-[:HAS_CONSENT]->(c:ConsentCategory)
// WHERE c.revoked_at IS NULL
// OPTIONAL MATCH (hp)-[:TAGGED_AS]->(t:Tag)
// RETURN hp.profile_id,
//        hp.display_name,
//        hp.what_to_call,
//        hp.pronouns,
//        hp.timezone,
//        hp.communication_style,
//        hp.preferences,
//        hp.projects,
//        hp.privacy_level,
//        hp.consent_categories,
//        hp.notes,
//        hp.confidence,
//        hp.last_verified,
//        p.phone_number,
//        collect(DISTINCT c.name) AS active_consents,
//        collect(DISTINCT t.name) AS tags;


// ── Q2: "How does [person] prefer to communicate?" ───────────────────────────
// Parameters: $phone_e164
//
// MATCH (hp:HumanProfile {phone_e164: $phone_e164})
// RETURN hp.display_name,
//        hp.communication_style,
//        hp.preferences;


// ── Q3: Create or update HumanProfile ─────────────────────────────────────────
// Parameters: $phone_e164, $display_name, $timezone, etc.
//
// MATCH (p:Person {phone_number: $phone_e164})
// MERGE (hp:HumanProfile {phone_e164: $phone_e164})
// ON CREATE SET
//     hp.profile_id = "hp-" + randomUUID(),
//     hp.display_name = $display_name,
//     hp.timezone = $timezone,
//     hp.privacy_level = "contacts",
//     hp.consent_categories = [],
//     hp.source = "manual",
//     hp.confidence = 1.0,
//     hp.status = "active",
//     hp.created_at = datetime(),
//     hp.updated_at = datetime()
// ON MATCH SET
//     hp.timezone = COALESCE($timezone, hp.timezone),
//     hp.updated_at = datetime()
// MERGE (hp)-[link:LINKED_TO]->(p)
// ON CREATE SET link.created_at = datetime()
// RETURN hp.profile_id, hp.display_name;


// ── Q4: Update specific field ─────────────────────────────────────────────────
// Parameters: $phone_e164, $field, $value
//
// MATCH (hp:HumanProfile {phone_e164: $phone_e164})
// SET hp[$field] = $value,
//     hp.updated_at = datetime()
// RETURN hp.profile_id, hp[$field] AS new_value;


// ── Q5: Add consent category ──────────────────────────────────────────────────
// Parameters: $phone_e164, $category_name
//
// MATCH (hp:HumanProfile {phone_e164: $phone_e164})
// MATCH (c:ConsentCategory {name: $category_name})
// MERGE (hp)-[rel:HAS_CONSENT]->(c)
// ON CREATE SET
//     rel.granted_at = datetime(),
//     rel.source = "explicit",
//     rel.revoked_at = NULL
// SET hp.consent_categories = COALESCE(hp.consent_categories, []) + $category_name
// RETURN hp.display_name, c.name AS consent_granted;


// ── Q6: Revoke consent category ───────────────────────────────────────────────
// Parameters: $phone_e164, $category_name
//
// MATCH (hp:HumanProfile {phone_e164: $phone_e164})
// MATCH (hp)-[rel:HAS_CONSENT]->(c:ConsentCategory {name: $category_name})
// SET rel.revoked_at = datetime()
// SET hp.consent_categories = [x IN hp.consent_categories WHERE x <> $category_name]
// RETURN hp.display_name, c.name AS consent_revoked;


// ── Q7: Privacy-filtered profile query ────────────────────────────────────────
// Parameters: $phone_e164, $requester_privacy_level ("public", "contacts", "private")
//
// MATCH (hp:HumanProfile {phone_e164: $phone_e164})
// WITH hp,
//     CASE $requester_privacy_level
//         WHEN "private" THEN ["public", "contacts", "private"]
//         WHEN "contacts" THEN ["public", "contacts"]
//         ELSE ["public"]
//     END AS allowed_levels
// WHERE hp.privacy_level IN allowed_levels
// RETURN hp.display_name,
//        hp.what_to_call,
//        hp.timezone,
//        hp.projects;


// ── Q8: "Who has consented to [category]?" ───────────────────────────────────
// Parameters: $category_name
//
// MATCH (hp:HumanProfile)-[rel:HAS_CONSENT]->(c:ConsentCategory {name: $category_name})
// WHERE rel.revoked_at IS NULL
// RETURN hp.display_name, hp.phone_e164, rel.granted_at;


// ── Q9: Soft delete (anonymize) profile ───────────────────────────────────────
// Parameters: $phone_e164
//
// MATCH (hp:HumanProfile {phone_e164: $phone_e164})
// SET hp.display_name = "Anonymous",
//     hp.what_to_call = "User",
//     hp.pronouns = null,
//     hp.communication_style = {},
//     hp.preferences = {},
//     hp.projects = {},
//     hp.notes = null,
//     hp.consent_categories = [],
//     hp.status = "anonymized",
//     hp.updated_at = datetime()
// RETURN hp.profile_id, hp.status;


// ── Q10: Get profiles for context enrichment ──────────────────────────────────
// Parameters: $phone_e164s (list)
//
// MATCH (hp:HumanProfile)
// WHERE hp.phone_e164 IN $phone_e164s
//   AND hp.status = "active"
// RETURN hp.phone_e164,
//        hp.display_name,
//        hp.what_to_call,
//        hp.timezone,
//        hp.communication_style,
//        hp.projects;


// ── Q11: Confidence decay update ──────────────────────────────────────────────
// Run periodically to decay confidence of unverified profiles
// Parameters: $decay_factor (e.g., 0.95)
//
// MATCH (hp:HumanProfile)
// WHERE hp.last_verified < datetime() - duration("P30D")
//   AND hp.confidence > 0.5
// SET hp.confidence = hp.confidence * $decay_factor
// RETURN count(hp) AS profiles_updated;


// ── Q12: Search profiles by natural language ──────────────────────────────────
// Parameters: $search_text
//
// CALL db.index.fulltext.queryNodes("human_profile_search", $search_text)
// YIELD node AS hp, score
// WHERE hp.status = "active"
// RETURN hp.display_name, hp.phone_e164, hp.notes, score
// ORDER BY score DESC;


// ─────────────────────────────────────────────────────────────────────────────
// SECTION 7: GRAPH TOPOLOGY
// ─────────────────────────────────────────────────────────────────────────────
//
//                           +------------------+
//                           | ConsentCategory  |
//                           |  (calendar, ...) |
//                           +--------+---------+
//                                    ▲
//                                    | HAS_CONSENT
//                                    |
//         +-------------------+     +--------+---------+     +---------+
//         |      Person       |◄────│   HumanProfile   │────►│   Tag   |
//         | (Signal Calendar) │     │ (extended info)  │     |         |
//         +-------------------+     +--------+---------+     +---------+
//                                           |
//                                           | KNOWS
//                                           |
//                                    +------v------+
//                                    | HumanProfile|
//                                    |  (others)   |
//                                    +-------------+
//
// ─────────────────────────────────────────────────────────────────────────────
