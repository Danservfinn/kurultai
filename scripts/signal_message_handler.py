#!/usr/bin/env python3
"""
Signal Message Handler — Unified message processing pipeline.

Replaces signal_calendar_listener.py. Processes all incoming Signal
messages through a priority-ordered handler chain:

1. Ingest to Neo4j (always, non-blocking)
2. Profile/privacy commands (/privacy, /consent, /forget, profile update)
3. Calendar commands (schedule, reschedule, list events)
4. Conversational response (LLM with graph context)

Called by signal_jsonrpc_server.py on each incoming message (event-driven).

Usage:
    from signal_message_handler import process_message
    process_message(raw_msg)  # called by signal_jsonrpc_server.py
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from profile_handler import handle_profile_command
from conversation_logger import log_inbound, log_outbound
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)

# V2 imports (graceful if missing)
try:
    from conversation_ingester import ingest_message
    _HAS_INGESTER = True
except ImportError:
    _HAS_INGESTER = False

try:
    from conversational_responder import generate_response
    _HAS_RESPONDER = True
except ImportError:
    _HAS_RESPONDER = False

try:
    from pending_question import (
        get_pending_question, answer_question, get_next_event_question,
        create_confirmation_question, build_event_summary, expire_old_questions,
    )
    _HAS_PENDING_Q = True
except ImportError:
    _HAS_PENDING_Q = False

try:
    from neo4j_human_v2 import HumanStoreV2
    _HAS_HUMAN_STORE = True
except ImportError:
    _HAS_HUMAN_STORE = False

# Configuration
SIGNAL_ACCOUNT = os.getenv("SIGNAL_ACCOUNT", "+15165643945")
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://127.0.0.1:8080")
GROUP_ID = os.getenv("SIGNAL_GROUP_ID", "BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=")
LOG_FILE = os.path.expanduser("~/.openclaw/logs/signal_message_handler.log")

def _load_group_members() -> dict:
    """Load group members from env var or default config."""
    raw = os.getenv("SIGNAL_GROUP_MEMBERS", "")
    if raw:
        # Format: "+1234:Name,+5678:Name2"
        members = {}
        for pair in raw.split(","):
            if ":" in pair:
                phone, name = pair.strip().split(":", 1)
                members[phone.strip()] = name.strip()
        return members
    # Fallback to config file
    config_path = os.path.expanduser("~/.openclaw/config/group_members.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


GROUP_MEMBERS = _load_group_members()


def log_msg(message: str, level: str = "INFO"):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = datetime.now().isoformat()
    line = f"[{ts}] [{level}] {message}\n"
    fd = os.open(LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(line)


def process_message(raw_msg: dict) -> bool:
    """Process an incoming Signal message through the handler chain.

    Args:
        raw_msg: Dict with keys: message, sender, sender_name, group_id, message_id

    Returns:
        True if a response was sent
    """
    sender_phone = raw_msg.get("sender", "")
    sender_name = raw_msg.get("sender_name", "") or GROUP_MEMBERS.get(sender_phone, "")
    message_text = raw_msg.get("message", "")
    group_id = raw_msg.get("group_id")  # None = DM, string = group

    if not message_text or not sender_phone:
        return False

    log_msg(f"Processing [{sender_name or sender_phone[-4:]}]: ({len(message_text)} chars)")

    # -------------------------------------------------------------------------
    # Step 1: Ingest to Neo4j (non-blocking, consent-gated)
    # -------------------------------------------------------------------------
    human_id = None
    message_id = None

    # Pre-resolve human_id for consent check (before ingestion)
    if _HAS_HUMAN_STORE and not human_id:
        try:
            store = HumanStoreV2()
            try:
                human = store.find_or_create_by_phone(sender_phone, sender_name)
                human_id = human["id"]
            finally:
                store.close()
        except Exception:
            pass

    # Check message_storage consent before ingestion (fail-closed)
    _should_ingest = False  # Default: do not ingest without consent
    if human_id:
        try:
            from consent_decorator import check_consent
            _should_ingest = check_consent(human_id, "message_storage")
            if not _should_ingest:
                log_msg(f"Skipping ingestion — no message_storage consent")
        except Exception as e:
            log_msg(f"Consent check failed (fail-closed): {e}", "WARNING")
            _should_ingest = False
    else:
        # No human_id yet — allow ingestion so human can be created
        # (consent will be checked on subsequent messages)
        _should_ingest = True

    if _should_ingest and _HAS_INGESTER:
        try:
            result = ingest_message(
                phone=sender_phone,
                content=message_text,
                direction="inbound",
                channel="signal",
                group_id=group_id if group_id else None,
            )
            human_id = result.get("human_id")
            message_id = result.get("message_id")  # For engagement persistence
        except Exception as e:
            log_msg(f"Ingestion failed: {e}", "ERROR")

    # Also log to legacy system (only if consent allows ingestion)
    if _should_ingest:
        try:
            log_inbound(
                phone_number=sender_phone,
                content=message_text,
                channel="signal",
                message_id=str(raw_msg.get("message_id", "")),
            )
        except Exception:
            pass

    # Resolve human_id if ingestion didn't provide it
    if not human_id and _HAS_HUMAN_STORE:
        try:
            store = HumanStoreV2()
            try:
                human = store.find_or_create_by_phone(sender_phone, sender_name)
                human_id = human["id"]
            finally:
                store.close()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Step 2: Profile/privacy commands (highest priority)
    # -------------------------------------------------------------------------
    try:
        profile_response = handle_profile_command(message_text, sender_phone, sender_name)
        if profile_response:
            if group_id:
                # Privacy-sensitive responses must go to DM, not group
                _send_and_log(profile_response, sender_phone, None, {**raw_msg, "is_dm": True})
                _send_and_log("Check your DMs — I sent that info privately.", sender_phone, group_id, raw_msg)
            else:
                _send_and_log(profile_response, sender_phone, group_id, raw_msg)
            log_msg(f"Profile command handled")
            return True
    except Exception as e:
        log_msg(f"Profile handler error: {e}", "ERROR")

    # -------------------------------------------------------------------------
    # Step 2.05: Voting approval commands (owner only)
    # -------------------------------------------------------------------------
    if sender_phone == "+19194133445":
        text_lower = message_text.strip().lower()
        if text_lower.startswith("approve ") or text_lower.startswith("reject "):
            try:
                parts = message_text.strip().split(None, 1)
                action = parts[0].lower()
                proposal_id = parts[1].strip() if len(parts) > 1 else ""
                if proposal_id:
                    from kurultai_voting_approval import handle_human_approval
                    result = handle_human_approval(proposal_id, action)
                    # Force DM regardless of source context — approval responses are sensitive
                    _send_and_log(result, sender_phone, None, {**raw_msg, "is_dm": True})
                    return True
            except Exception as e:
                log_msg(f"Voting approval handler error: {e}", "ERROR")

    # -------------------------------------------------------------------------
    # Step 2.1: Ensure context isolation log path exists
    # -------------------------------------------------------------------------
    if group_id:
        try:
            Path("/Users/kublai/.openclaw/logs").mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Step 2.5: Check for pending question (sequential interrogation)
    # -------------------------------------------------------------------------
    if _HAS_PENDING_Q and human_id:
        try:
            # Expire stale questions first (cheap, idempotent)
            expire_old_questions()

            # Scope pending questions to the current channel
            _pq_channel = group_id if group_id else None
            pending = get_pending_question(human_id, channel_id=_pq_channel)
            if pending:
                # Never process DM-only curiosity questions in group context
                if group_id and pending.get("type") == "profile_curiosity":
                    pending = None
            if pending:
                result = _handle_pending_answer(
                    pending, message_text, sender_phone, sender_name, group_id, raw_msg
                )
                if result:
                    return True
                # If result is False, message wasn't an answer — fall through
        except Exception as e:
            log_msg(f"Pending question handler error: {e}", "ERROR")

    # -------------------------------------------------------------------------
    # Step 3: Calendar commands
    # -------------------------------------------------------------------------
    try:
        from calendar_handler import handle_message
        calendar_response = handle_message(raw_msg)
        if calendar_response:
            _send_and_log(calendar_response, sender_phone, group_id, raw_msg)
            log_msg(f"Calendar command handled")
            return True
    except ImportError:
        pass  # calendar_handler not available
    except Exception as e:
        log_msg(f"Calendar handler error: {e}", "ERROR")

    # -------------------------------------------------------------------------
    # Step 4: Conversational response (LLM with graph context)
    # -------------------------------------------------------------------------
    is_group = bool(group_id)

    if _HAS_RESPONDER and human_id:
        try:
            response = generate_response(
                human_id=human_id,
                message_text=message_text,
                sender_name=sender_name,
                message_id=message_id,
                group_id=group_id if is_group else None,
                group_mode=is_group,
            )
            if response:
                _send_and_log(response, sender_phone, group_id, raw_msg)
                log_msg(f"Conversational response sent ({len(response)} chars)")

                # Check if Kublai wants to escalate to a specialist agent
                try:
                    from conversational_responder import detect_task_escalation
                    if detect_task_escalation(response):
                        _escalate_to_task(
                            message_text, sender_name, sender_phone,
                            message_id=raw_msg.get("message_id"),
                        )
                except Exception:
                    pass

                return True
            else:
                log_msg(f"Engagement decision: silent")
                return False
        except Exception as e:
            log_msg(f"Conversational responder error: {e}\n{traceback.format_exc()}", "ERROR")

    # -------------------------------------------------------------------------
    # Fallback: no handler matched and no responder available
    # -------------------------------------------------------------------------
    log_msg(f"No handler matched ({len(message_text)} chars)", "WARNING")
    return False


def _handle_pending_answer(
    pending: dict,
    message_text: str,
    sender_phone: str,
    sender_name: str,
    group_id: str,
    raw_msg: dict,
) -> bool:
    """Handle a message as an answer to a pending question.

    Returns True if the message was consumed as an answer.
    Returns False if the message should fall through to other handlers.
    """
    # Escape hatch: commands and profile keywords should not be consumed
    text_stripped = message_text.strip()
    if text_stripped.startswith("/") or text_stripped.lower().startswith("profile"):
        return False

    question_type = pending.get("type", "")
    context = pending.get("context", {})

    # Handle confirmation (yes/no to create the event)
    if context.get("confirmation_pending"):
        from calendar_parser import is_affirmative, is_negative
        if is_affirmative(message_text):
            # Create the event
            try:
                from calendar_handler import create_event_from_dict
                response = create_event_from_dict(
                    event_dict=context.get("event_data", {}),
                    resolved_time=context.get("resolved_time", {}),
                    sender_phone=sender_phone,
                    sender_name=context.get("sender_name", sender_name),
                )
                _send_and_log(response, sender_phone, group_id, raw_msg)
                return True
            except Exception as e:
                log_msg(f"Event creation from pending failed: {e}", "ERROR")
                _send_and_log(
                    f"Sorry, something went wrong creating the event: {e}",
                    sender_phone, group_id, raw_msg,
                )
                return True
        elif is_negative(message_text):
            # Cancel — answer_question will mark it
            answer_question(pending["id"], message_text)
            _send_and_log("OK, cancelled.", sender_phone, group_id, raw_msg)
            return True
        else:
            # Not a clear yes/no — fall through to other handlers
            return False

    # Handle event_field answers
    if question_type == "event_field":
        answered = answer_question(pending["id"], message_text)
        if answered is None:
            return False  # Race condition, already answered

        # If user said "done", go straight to confirmation
        if answered.get("_is_done"):
            try:
                summary = create_confirmation_question(
                    pending["humanId"], answered["context"]
                )
                _send_and_log(summary, sender_phone, group_id, raw_msg)
                return True
            except Exception as e:
                log_msg(f"Confirmation question creation failed: {e}", "ERROR")
                return True

        # Check for more fields
        next_q = get_next_event_question(pending["humanId"], answered["context"])
        if next_q:
            _send_and_log(next_q, sender_phone, group_id, raw_msg)
            return True
        else:
            # All fields collected — create confirmation question
            try:
                summary = create_confirmation_question(
                    pending["humanId"], answered["context"]
                )
                _send_and_log(summary, sender_phone, group_id, raw_msg)
                return True
            except Exception as e:
                log_msg(f"Confirmation question creation failed: {e}", "ERROR")
                return True

    # Handle profile_curiosity answers
    if question_type == "profile_curiosity":
        answered = answer_question(pending["id"], message_text)
        if answered is None:
            return False

        if not answered.get("_is_skip"):
            # Apply answer to Neo4j profile or event
            try:
                _apply_curiosity_answer(
                    pending["humanId"],
                    pending.get("field", ""),
                    message_text,
                    context=pending.get("context", {}),
                )
                _send_and_log("Got it, thanks!", sender_phone, group_id, raw_msg)
            except Exception as e:
                log_msg(f"Curiosity answer application failed: {e}", "ERROR")
                _send_and_log("Got it, thanks!", sender_phone, group_id, raw_msg)
        return True

    # Unknown question type — consume silently
    answer_question(pending["id"], message_text)
    return True


EVENT_FIELD_MAP = {
    "event_dress_code": "dress_code",
    "event_cost": "cost",
    "event_what_to_bring": "what_to_bring",
    "event_indoor_outdoor": "indoor_outdoor",
    "event_dietary": "dietary_notes",
    "event_transport": "transport_notes",
    "event_category": "category",
    "event_rain_plan": "rain_plan",
}


def _apply_curiosity_answer(human_id: str, field: str, answer: str, context: dict = None):
    """Apply a curiosity answer to the human's Neo4j profile or event."""
    try:
        with neo4j_session() as session:
            if field == "timezone":
                session.run(
                    "MATCH (h:Human {id: $hid}) SET h.timezone = $val",
                    hid=human_id, val=answer.strip(),
                )
            elif field == "displayName":
                session.run(
                    "MATCH (h:Human {id: $hid}) SET h.displayName = $val",
                    hid=human_id, val=answer.strip(),
                )
                # Also add as NAME_VARIANT identifier
                session.run(
                    """
                    MATCH (h:Human {id: $hid})
                    MERGE (i:Identifier {type: 'NAME_VARIANT', value: $val})
                    MERGE (h)-[:IDENTIFIED_BY]->(i)
                    """,
                    hid=human_id, val=answer.strip(),
                )
            elif field == "event_location":
                # The context should have the event info
                logger.info(f"Event location update for {human_id}: {answer}")
            elif field in EVENT_FIELD_MAP:
                # Update the Event node directly
                event_prop = EVENT_FIELD_MAP[field]
                event_id = (context or {}).get("event_id")
                event_name = (context or {}).get("event_name")
                update_props = {event_prop: answer.strip()}
                if event_id:
                    session.run(
                        """
                        MATCH (e:Event {event_id: $eid, status: 'active'})
                        SET e += $props, e.updated_at = datetime()
                        """,
                        eid=event_id, props=update_props,
                    )
                    logger.info(f"Updated Event.{event_prop} for event_id={event_id}: {answer.strip()}")
                elif event_name:
                    # Fallback for legacy questions without event_id — limit to 1
                    session.run(
                        """
                        MATCH (e:Event {status: 'active'})
                        WHERE e.name = $name AND e.start_datetime > datetime()
                        WITH e ORDER BY e.start_datetime ASC LIMIT 1
                        SET e += $props, e.updated_at = datetime()
                        """,
                        name=event_name, props=update_props,
                    )
                    logger.info(f"Updated Event.{event_prop} for '{event_name}': {answer.strip()}")
                else:
                    logger.warning(f"Event field {field} answer but no event_id or event_name in context")
            else:
                # Store as self-reported Inference
                import uuid as _uuid
                session.run(
                    """
                    MATCH (h:Human {id: $hid})
                    CREATE (i:Inference {
                        id: $iid,
                        humanId: $hid,
                        type: 'self_reported',
                        field: $field,
                        value: $val,
                        confidence: 1.0,
                        source: 'proactive_curiosity',
                        createdAt: datetime()
                    })
                    CREATE (h)-[:HAS_INFERENCE]->(i)
                    """,
                    hid=human_id, iid=str(_uuid.uuid4()),
                    field=field, val=answer.strip(),
                )
    except Exception as e:
        logger.error(f"Failed to apply curiosity answer: {e}")


_rpc_client = None

def _get_rpc_client():
    """Get the shared RPC client from the server (if running in-process)."""
    global _rpc_client
    if _rpc_client is not None:
        return _rpc_client

    # Try importing from the running server
    try:
        from signal_jsonrpc_server import _active_rpc_client
        if _active_rpc_client:
            _rpc_client = _active_rpc_client
            return _rpc_client
    except (ImportError, AttributeError):
        pass
    return None


def _send_and_log(response: str, sender_phone: str, group_id: str, raw_msg: dict):
    """Send response via Signal and log to both systems."""
    is_dm = raw_msg.get("is_dm", False) or not group_id

    # Apply response guard for group messages (catches unguarded code paths)
    if not is_dm and group_id:
        try:
            from response_guard import guard_response
            response = guard_response(response, is_group=True)
        except Exception as e:
            logger.warning(f"ResponseGuard failed: {e}")
            response = "Let's discuss that in a DM."

    # Build send params — DM vs group
    if is_dm:
        send_params = {
            "message": response,
            "recipient": [sender_phone],
            "account": SIGNAL_ACCOUNT,
        }
        log_msg(f"Sending DM to ***{sender_phone[-4:]}")
    else:
        send_params = {
            "message": response,
            "groupId": group_id,
            "account": SIGNAL_ACCOUNT,
        }
        log_msg(f"Sending to group {group_id[:12]}...")
        # Context isolation observability: log group sends
        try:
            import json as _json
            _log_path = Path("/Users/kublai/.openclaw/logs/response-guard-activations.jsonl")
            if _log_path.parent.exists():
                with open(_log_path, "a") as _f:
                    _f.write(_json.dumps({
                        "timestamp": datetime.now().isoformat(),
                        "event": "group_send",
                        "group_id": group_id[:12],
                        "response_length": len(response),
                    }) + "\n")
                    _f.flush()
        except Exception:
            pass  # Never fail send due to logging

    # Try direct RPC client first (avoids HTTP self-deadlock)
    rpc = _get_rpc_client()
    if rpc:
        try:
            result = rpc.call("send", send_params)
            if isinstance(result, dict) and "error" in result:
                log_msg(f"RPC send error: {result['error']}", "WARNING")
            else:
                log_msg(f"Sent via direct RPC")
        except Exception as e:
            log_msg(f"Direct RPC send failed: {e}", "ERROR")
    else:
        # Fallback to HTTP
        import requests
        try:
            rpc_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "send",
                "params": send_params,
            }
            requests.post(
                f"{SIGNAL_API_URL}/api/v1/rpc",
                json=rpc_payload,
                timeout=30,
            )
        except Exception as e:
            log_msg(f"HTTP send failed: {e}", "ERROR")

    # Log outbound to legacy
    try:
        log_outbound(
            phone_number=sender_phone,
            content=response,
            channel="signal",
            message_id=str(raw_msg.get("message_id", "")),
        )
    except Exception:
        pass

    # Log outbound to Neo4j
    if _HAS_INGESTER:
        try:
            ingest_message(
                phone=sender_phone,
                content=response,
                direction="outbound",
                channel="signal",
                group_id=group_id if group_id else None,
            )
        except Exception:
            pass


def _escalate_to_task(message_text: str, sender_name: str, sender_phone: str,
                      message_id: int = None):
    """Create a task via task_intake when Kublai decides to route work.

    Uses the Python API directly to pass origin_message_id for Signal
    reply threading. Falls back to subprocess CLI if import fails.
    """
    try:
        sys.path.insert(0, os.path.expanduser("~/.openclaw/agents/main/scripts"))
        from task_intake import create_task
        create_task(
            title=f"Signal request from {sender_name}: {message_text[:80]}",
            body=f"From {sender_name} ({sender_phone}) via Signal: {message_text}",
            priority="normal",
            source="signal-escalation",
            origin_type="human",
            origin_initiator=sender_phone,
            origin_source="signal",
            origin_message_id=message_id,
            notify_on_complete=True,
            notify_target=sender_phone,
        )
        log_msg(f"Escalated to task system ({len(message_text)} chars)")
    except Exception as e:
        log_msg(f"Task escalation (API) failed: {e}, trying subprocess", "WARNING")
        try:
            import subprocess
            cmd = [
                "python3",
                os.path.expanduser("~/.openclaw/agents/main/scripts/task_intake.py"),
                "--title", f"Signal request from {sender_name}: {message_text[:80]}",
                "--body", f"From {sender_name} ({sender_phone}) via Signal: {message_text}",
                "--priority", "normal",
                "--source", "signal-escalation",
                "--notify-on-complete",
                "--notify-target", sender_phone,
            ]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log_msg(f"Escalated via subprocess fallback")
        except Exception as sub_err:
            log_msg(f"Task escalation failed completely: {sub_err}", "ERROR")


# Legacy compatibility: signal_jsonrpc_server.py imports process_calendar_message
process_calendar_message = process_message
