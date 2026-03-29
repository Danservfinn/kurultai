#!/usr/bin/env python3
"""V12: Communication Fingerprint — pure Python stats from Message nodes.

Computes per-human communication statistics (avg message length, emoji rate,
question ratio, formality score) and MERGEs as :Inference:CommunicationFingerprint.

No LLM required — pure Cypher aggregation.
"""

import os, sys, logging, re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)

EMOJI_PATTERN = re.compile(
    r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
    r'\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF'
    r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF]'
)


def compute_fingerprint(driver, human_id: str) -> dict:
    """Compute communication stats for one human over last 30 days.

    Returns dict with: avg_length, emoji_rate, question_ratio, msg_count_30d
    """
    with driver.session() as s:
        result = s.run("""
            MATCH (m:Message {humanId: $hid, direction: 'inbound'})
            WHERE m.timestamp >= datetime() - duration('P30D')
              AND m.contentScrubbed IS NOT NULL
            RETURN
                avg(size(m.contentScrubbed)) AS avg_length,
                count(m) AS total,
                count(CASE WHEN m.contentScrubbed CONTAINS '?' THEN 1 END) AS questions,
                collect(m.contentScrubbed) AS texts
            """, hid=human_id).single()

    if not result or result['total'] == 0:
        return {'avg_length': 0, 'emoji_rate': 0.0, 'question_ratio': 0.0, 'msg_count_30d': 0}

    total = result['total']
    avg_len = round(result['avg_length'] or 0, 1)
    q_ratio = round(result['questions'] / total, 3) if total > 0 else 0.0

    # Compute emoji rate from collected texts
    texts = result['texts'] or []
    total_chars = sum(len(t) for t in texts if t)
    emoji_count = sum(len(EMOJI_PATTERN.findall(t)) for t in texts if t)
    emoji_rate = round(emoji_count / max(total_chars, 1), 4)

    return {
        'avg_length': avg_len,
        'emoji_rate': emoji_rate,
        'question_ratio': q_ratio,
        'msg_count_30d': total,
    }


def store_fingerprint(driver, human_id: str, stats: dict) -> None:
    """MERGE CommunicationFingerprint node for human."""
    with driver.session() as s:
        s.run("""
            MERGE (cf:Inference:CommunicationFingerprint {humanId: $hid})
            ON CREATE SET
                cf.id = randomUUID(),
                cf.avgLength = $avg_len,
                cf.emojiRate = $emoji_rate,
                cf.questionRatio = $q_ratio,
                cf.msgCount30d = $msg_count,
                cf.superseded = false,
                cf.scope = 'system',
                cf.field = 'communication_fingerprint',
                cf.value = 'stats',
                cf.createdAt = datetime(),
                cf.timestamp = datetime()
            ON MATCH SET
                cf.avgLength = $avg_len,
                cf.emojiRate = $emoji_rate,
                cf.questionRatio = $q_ratio,
                cf.msgCount30d = $msg_count,
                cf.updatedAt = datetime()
        """, hid=human_id, avg_len=stats['avg_length'],
             emoji_rate=stats['emoji_rate'],
             q_ratio=stats['question_ratio'],
             msg_count=stats['msg_count_30d'])


def compute_all_fingerprints(driver) -> int:
    """Compute fingerprints for all active humans. Returns count processed."""
    with driver.session() as s:
        result = s.run("""
            MATCH (h:Human)
            WHERE EXISTS {
                MATCH (m:Message {humanId: h.id, direction: 'inbound'})
                WHERE m.timestamp >= datetime() - duration('P30D')
            }
            RETURN h.id AS hid
        """)
        human_ids = [r['hid'] for r in result]

    count = 0
    for hid in human_ids:
        try:
            stats = compute_fingerprint(driver, hid)
            if stats['msg_count_30d'] > 0:
                store_fingerprint(driver, hid, stats)
                count += 1
        except Exception as e:
            logger.warning(f"V12: fingerprint failed for {hid}: {e}")

    logger.info(f"V12: computed {count} fingerprints for {len(human_ids)} humans")
    return count


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    driver = get_driver()
    try:
        compute_all_fingerprints(driver)
    finally:
        close_driver()
