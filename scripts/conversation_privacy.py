#!/usr/bin/env python3
"""
Conversation Privacy - Privacy controls and audit logging for human conversations.

Provides:
1. Access control - users can only see their own conversations
2. Admin access with audit logging
3. GDPR-style data export and deletion
4. Privacy request handling

Usage:
    from conversation_privacy import ConversationPrivacy

    privacy = ConversationPrivacy()

    # Check access
    if privacy.can_access(requesting_user, target_phone):
        conversations = get_conversations(target_phone)

    # Admin access (logged)
    with privacy.admin_access(admin_id, target_phone) as audit:
        conversations = get_conversations(target_phone)

    # Export user data
    privacy.export_user_data(phone_number)

    # Delete user data
    privacy.delete_user_data(phone_number)
"""

import os
import json
import stat
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from contextlib import contextmanager

import sys
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from human_profile_memory import HumanProfileMemory
from conversation_logger import ConversationLogger

# Paths
MEMORY_DIR = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans"
ARCHIVE_DIR = MEMORY_DIR / "archive"
AUDIT_LOG = Path.home() / ".openclaw" / "logs" / "privacy_audit.log"
ADMIN_CONFIG = Path.home() / ".openclaw" / "config" / "privacy_admins.json"

# Admin user IDs (phone numbers with admin access)
DEFAULT_ADMINS = ["+15165643945"]  # System admin


class AuditLogger:
    """Audit logging for privacy-sensitive operations."""

    def __init__(self, log_file: Path = AUDIT_LOG):
        self.log_file = log_file
        self._ensure_log_file()

    def _ensure_log_file(self) -> None:
        """Ensure log file exists with proper permissions."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()
        # Set permissions to 600 (owner read/write only)
        os.chmod(self.log_file, stat.S_IRUSR | stat.S_IWUSR)

    def log(
        self,
        action: str,
        actor: str,
        target: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True
    ) -> None:
        """
        Log a privacy-related action.

        Args:
            action: Action type (access, export, delete, admin_access)
            actor: User ID performing the action
            target: Target user ID (if applicable)
            details: Additional details
            success: Whether the action succeeded
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "actor": actor,
            "target": target,
            "success": success,
            "details": details or {}
        }

        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_logs(
        self,
        actor: Optional[str] = None,
        target: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query audit logs.

        Args:
            actor: Filter by actor
            target: Filter by target
            action: Filter by action type
            since: Filter by timestamp
            limit: Maximum results

        Returns:
            List of matching log entries
        """
        if not self.log_file.exists():
            return []

        results = []
        with open(self.log_file, "r") as f:
            for line in reversed(list(f.readlines())):
                try:
                    entry = json.loads(line.strip())

                    # Apply filters
                    if actor and entry.get("actor") != actor:
                        continue
                    if target and entry.get("target") != target:
                        continue
                    if action and entry.get("action") != action:
                        continue
                    if since:
                        entry_time = datetime.fromisoformat(entry["timestamp"])
                        if entry_time < since:
                            continue

                    results.append(entry)
                    if len(results) >= limit:
                        break
                except (json.JSONDecodeError, KeyError):
                    continue

        return results


class ConversationPrivacy:
    """Privacy controls for conversation storage."""

    def __init__(self):
        self.memory = HumanProfileMemory("main")
        self.logger = ConversationLogger()
        self.audit = AuditLogger()
        self._admins = self._load_admins()

    def _load_admins(self) -> List[str]:
        """Load admin users from config."""
        if ADMIN_CONFIG.exists():
            try:
                with open(ADMIN_CONFIG, "r") as f:
                    config = json.load(f)
                    return config.get("admins", DEFAULT_ADMINS)
            except (json.JSONDecodeError, KeyError):
                pass
        return DEFAULT_ADMINS

    def _save_admins(self) -> None:
        """Save admin users to config."""
        ADMIN_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        with open(ADMIN_CONFIG, "w") as f:
            json.dump({"admins": self._admins, "updated": datetime.now().isoformat()}, f, indent=2)
        os.chmod(ADMIN_CONFIG, stat.S_IRUSR | stat.S_IWUSR)

    def is_admin(self, user_id: str) -> bool:
        """Check if a user has admin privileges."""
        return user_id in self._admins

    def add_admin(self, admin_id: str, added_by: str) -> bool:
        """
        Add an admin user.

        Args:
            admin_id: User ID to make admin
            added_by: Admin performing the action

        Returns:
            True if successful
        """
        if not self.is_admin(added_by):
            return False

        if admin_id not in self._admins:
            self._admins.append(admin_id)
            self._save_admins()
            self.audit.log("add_admin", added_by, admin_id)
        return True

    def remove_admin(self, admin_id: str, removed_by: str) -> bool:
        """Remove an admin user."""
        if not self.is_admin(removed_by):
            return False

        if admin_id in self._admins and admin_id != DEFAULT_ADMINS[0]:
            self._admins.remove(admin_id)
            self._save_admins()
            self.audit.log("remove_admin", removed_by, admin_id)
        return True

    def can_access(self, requesting_user: str, target_phone: str) -> bool:
        """
        Check if a user can access another user's conversations.

        Users can only access their own conversations, unless they are admin.

        Args:
            requesting_user: User requesting access
            target_phone: Target phone number

        Returns:
            True if access is allowed
        """
        # Self-access is always allowed
        if requesting_user == target_phone:
            return True

        # Admin access is allowed but logged
        if self.is_admin(requesting_user):
            return True

        return False

    @contextmanager
    def admin_access(self, admin_id: str, target_phone: str):
        """
        Context manager for admin access to user data.

        Logs the access attempt automatically.

        Args:
            admin_id: Admin user ID
            target_phone: Target phone number

        Yields:
            Audit context object

        Raises:
            PermissionError: If not an admin
        """
        if not self.is_admin(admin_id):
            self.audit.log("admin_access_denied", admin_id, target_phone, success=False)
            raise PermissionError(f"User {admin_id} is not an admin")

        self.audit.log("admin_access", admin_id, target_phone)

        class AuditContext:
            def __init__(self, privacy, admin, target):
                self.privacy = privacy
                self.admin = admin
                self.target = target
                self.accessed = False

            def record_access(self, data_type: str, count: int = 1):
                """Record that data was accessed."""
                self.accessed = True
                self.privacy.audit.log(
                    "data_access",
                    self.admin,
                    self.target,
                    {"data_type": data_type, "count": count}
                )

        try:
            yield AuditContext(self, admin_id, target_phone)
        except Exception as e:
            self.audit.log("admin_access_error", admin_id, target_phone, {"error": str(e)}, success=False)
            raise

    def get_user_conversations(
        self,
        requesting_user: str,
        target_phone: str,
        limit: int = 50
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get conversations with access control.

        Args:
            requesting_user: User requesting access
            target_phone: Target phone number
            limit: Maximum conversations

        Returns:
            List of conversations or None if access denied
        """
        if not self.can_access(requesting_user, target_phone):
            self.audit.log("access_denied", requesting_user, target_phone, success=False)
            return None

        # Log admin access
        if requesting_user != target_phone:
            self.audit.log("data_access", requesting_user, target_phone, {"type": "conversations", "limit": limit})

        return self.logger.get_recent_conversations(target_phone, limit=limit)

    def export_user_data(self, phone_number: str, requesting_user: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Export all user data for GDPR-style requests.

        Args:
            phone_number: User to export
            requesting_user: User making request (defaults to phone_number)

        Returns:
            Dict with all user data or None if access denied
        """
        if requesting_user is None:
            requesting_user = phone_number

        if not self.can_access(requesting_user, phone_number):
            self.audit.log("export_denied", requesting_user, phone_number, success=False)
            return None

        self.audit.log("export", requesting_user, phone_number)

        # Gather all data
        profile = self.memory.read_profile(phone_number)
        conversations_json = self.logger.export_conversations(phone_number)
        conversations = json.loads(conversations_json) if conversations_json else []
        stats = self.logger.get_conversation_stats(phone_number)

        # Load archived conversations
        normalized_id = self.memory._normalize_id(phone_number)
        archived = []
        for archive_file in ARCHIVE_DIR.glob(f"{normalized_id}-archive-*.json"):
            try:
                with open(archive_file, "r") as f:
                    archived.extend(json.load(f))
            except (json.JSONDecodeError, Exception):
                pass

        return {
            "export_date": datetime.now().isoformat(),
            "phone_number": phone_number,
            "profile": profile,
            "conversations": conversations,
            "archived_conversations": archived,
            "statistics": stats,
            "file_location": str(self.memory._get_file_path(phone_number))
        }

    def delete_user_data(
        self,
        phone_number: str,
        requesting_user: Optional[str] = None,
        confirm: bool = False
    ) -> Dict[str, Any]:
        """
        Delete all user data for GDPR-style requests.

        Args:
            phone_number: User to delete
            requesting_user: User making request (defaults to phone_number)
            confirm: Must be True to actually delete

        Returns:
            Dict with deletion status
        """
        if requesting_user is None:
            requesting_user = phone_number

        if not self.can_access(requesting_user, phone_number):
            self.audit.log("delete_denied", requesting_user, phone_number, success=False)
            return {"success": False, "error": "Access denied"}

        if not confirm:
            return {
                "success": False,
                "error": "Must set confirm=True to delete",
                "warning": "This will permanently delete all data for " + phone_number
            }

        self.audit.log("delete", requesting_user, phone_number)

        # Get file path before deletion
        file_path = self.memory._get_file_path(phone_number)

        # Count items to delete
        profile = self.memory.read_profile(phone_number)
        conv_count = len(profile.get("conversations", [])) if profile else 0

        # Delete main profile
        deleted = self.memory.delete_profile(phone_number)

        # Delete archives
        normalized_id = self.memory._normalize_id(phone_number)
        archive_count = 0
        for archive_file in ARCHIVE_DIR.glob(f"{normalized_id}-archive-*.json"):
            try:
                archive_count += len(json.loads(archive_file.read_text()))
            except Exception:
                pass
            archive_file.unlink()

        return {
            "success": deleted,
            "phone_number": phone_number,
            "conversations_deleted": conv_count,
            "archived_deleted": archive_count,
            "file_deleted": str(file_path) if deleted else None,
            "deleted_at": datetime.now().isoformat()
        }

    def request_privacy_action(
        self,
        phone_number: str,
        action: str,
        requesting_user: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle a privacy request.

        Args:
            phone_number: User making request
            action: Action type (export, delete, access)
            requesting_user: User making request (defaults to phone_number)

        Returns:
            Dict with result
        """
        self.audit.log("privacy_request", requesting_user or phone_number, phone_number, {"action": action})

        if action == "export":
            data = self.export_user_data(phone_number, requesting_user)
            return {
                "success": data is not None,
                "action": "export",
                "data": data
            }

        elif action == "delete":
            # Delete requires explicit confirmation
            return {
                "success": False,
                "action": "delete",
                "message": "To delete data, use delete_user_data() with confirm=True",
                "warning": "This action is irreversible"
            }

        elif action == "access":
            conversations = self.get_user_conversations(
                requesting_user or phone_number,
                phone_number
            )
            return {
                "success": conversations is not None,
                "action": "access",
                "data": conversations
            }

        else:
            return {
                "success": False,
                "error": f"Unknown action: {action}"
            }

    def get_audit_logs(
        self,
        requesting_user: str,
        target: Optional[str] = None,
        limit: int = 100
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get audit logs.

        Args:
            requesting_user: User requesting logs
            target: Filter by target user
            limit: Maximum results

        Returns:
            List of audit entries or None if not authorized
        """
        # Only admins can view audit logs
        if not self.is_admin(requesting_user):
            self.audit.log("audit_log_denied", requesting_user, target, success=False)
            return None

        return self.audit.get_logs(target=target, limit=limit)

    def verify_permissions(self) -> Dict[str, Any]:
        """
        Verify that file permissions are correctly set.

        Returns:
            Dict with permission status
        """
        issues = []

        # Check memory directory
        if MEMORY_DIR.exists():
            mode = oct(MEMORY_DIR.stat().st_mode)[-3:]
            if mode != "700":
                issues.append(f"Memory dir has mode {mode}, should be 700")
        else:
            issues.append("Memory directory does not exist")

        # Check profile files
        for profile_file in MEMORY_DIR.glob("*.md"):
            mode = oct(profile_file.stat().st_mode)[-3:]
            if mode != "600":
                issues.append(f"{profile_file.name} has mode {mode}, should be 600")

        # Check archive files
        for archive_file in ARCHIVE_DIR.glob("*.json"):
            mode = oct(archive_file.stat().st_mode)[-3:]
            if mode != "600":
                issues.append(f"{archive_file.name} has mode {mode}, should be 600")

        # Check audit log
        if AUDIT_LOG.exists():
            mode = oct(AUDIT_LOG.stat().st_mode)[-3:]
            if mode != "600":
                issues.append(f"Audit log has mode {mode}, should be 600")

        return {
            "ok": len(issues) == 0,
            "issues": issues,
            "checked_at": datetime.now().isoformat()
        }

    def fix_permissions(self) -> Dict[str, Any]:
        """
        Fix file permissions to secure defaults.

        Returns:
            Dict with actions taken
        """
        actions = []

        # Fix memory directory
        if MEMORY_DIR.exists():
            os.chmod(MEMORY_DIR, stat.S_IRWXU)  # 700
            actions.append(f"Set {MEMORY_DIR} to 700")

        # Fix archive directory
        if ARCHIVE_DIR.exists():
            os.chmod(ARCHIVE_DIR, stat.S_IRWXU)  # 700
            actions.append(f"Set {ARCHIVE_DIR} to 700")

        # Fix profile files
        for profile_file in MEMORY_DIR.glob("*.md"):
            os.chmod(profile_file, stat.S_IRUSR | stat.S_IWUSR)  # 600
            actions.append(f"Set {profile_file.name} to 600")

        # Fix archive files
        for archive_file in ARCHIVE_DIR.glob("*.json"):
            os.chmod(archive_file, stat.S_IRUSR | stat.S_IWUSR)  # 600
            actions.append(f"Set {archive_file.name} to 600")

        # Fix audit log
        if AUDIT_LOG.exists():
            os.chmod(AUDIT_LOG, stat.S_IRUSR | stat.S_IWUSR)  # 600
            actions.append("Set audit log to 600")

        return {
            "ok": True,
            "actions": actions,
            "fixed_at": datetime.now().isoformat()
        }


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Conversation Privacy Controls")
    parser.add_argument("command", choices=["verify", "fix", "export", "delete", "logs", "admins"])
    parser.add_argument("--phone", "-p", help="Phone number for export/delete")
    parser.add_argument("--admin", "-a", help="Admin user ID")
    parser.add_argument("--add-admin", help="Add an admin user")
    parser.add_argument("--remove-admin", help="Remove an admin user")
    parser.add_argument("--confirm", action="store_true", help="Confirm destructive action")
    parser.add_argument("--limit", "-l", type=int, default=100, help="Limit results")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    privacy = ConversationPrivacy()

    if args.command == "verify":
        result = privacy.verify_permissions()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["ok"]:
                print("✓ All permissions verified")
            else:
                print("✗ Permission issues found:")
                for issue in result["issues"]:
                    print(f"  - {issue}")

    elif args.command == "fix":
        result = privacy.fix_permissions()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Fixed {len(result['actions'])} permission(s):")
            for action in result["actions"]:
                print(f"  ✓ {action}")

    elif args.command == "export":
        if not args.phone:
            print("Error: --phone is required for export")
            sys.exit(1)
        result = privacy.export_user_data(args.phone)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"Export for {args.phone}")
            print(f"  Conversations: {len(result.get('conversations', []))}")
            print(f"  Archived: {len(result.get('archived_conversations', []))}")
            print(f"  Export date: {result.get('export_date')}")

    elif args.command == "delete":
        if not args.phone:
            print("Error: --phone is required for delete")
            sys.exit(1)
        result = privacy.delete_user_data(args.phone, confirm=args.confirm)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["success"]:
                print(f"✓ Deleted data for {args.phone}")
                print(f"  Conversations: {result.get('conversations_deleted', 0)}")
                print(f"  Archived: {result.get('archived_deleted', 0)}")
            else:
                print(f"✗ {result.get('error', 'Unknown error')}")
                if result.get("warning"):
                    print(f"  {result['warning']}")

    elif args.command == "logs":
        requesting = args.admin or args.phone or "+15165643945"
        result = privacy.get_audit_logs(requesting, target=args.phone, limit=args.limit)
        if result is None:
            print("Error: Admin access required to view audit logs")
            sys.exit(1)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"Audit Logs ({len(result)} entries)")
            print("=" * 60)
            for entry in result:
                ts = entry.get("timestamp", "unknown")[:19]
                action = entry.get("action", "unknown")
                actor = entry.get("actor", "unknown")
                target = entry.get("target", "")
                status = "✓" if entry.get("success", True) else "✗"
                print(f"{status} [{ts}] {action} by {actor}" + (f" -> {target}" if target else ""))

    elif args.command == "admins":
        if args.add_admin:
            if not args.admin:
                print("Error: --admin required to add admins")
                sys.exit(1)
            success = privacy.add_admin(args.add_admin, args.admin)
            if success:
                print(f"✓ Added {args.add_admin} as admin")
            else:
                print("✗ Failed to add admin (not authorized)")
        elif args.remove_admin:
            if not args.admin:
                print("Error: --admin required to remove admins")
                sys.exit(1)
            success = privacy.remove_admin(args.remove_admin, args.admin)
            if success:
                print(f"✓ Removed {args.remove_admin} from admins")
            else:
                print("✗ Failed to remove admin")
        else:
            print("Current admins:")
            for admin in privacy._admins:
                print(f"  - {admin}")
