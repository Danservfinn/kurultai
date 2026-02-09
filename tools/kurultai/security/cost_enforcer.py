"""Cost enforcer for Kurultai v0.2 multi-agent orchestration.

Tracks and enforces per-agent spending budgets to prevent runaway costs
in multi-agent workflows. Uses a reservation-based model: agents must
authorize spending before committing, and unreserved funds are released
back to the budget.

OWASP LLM04:2023 - Denial of Service / resource exhaustion prevention.

Usage:
    enforcer = CostEnforcer(default_budget=10.0, budget_window_seconds=3600)

    # Reserve budget before an operation
    reservation_id = enforcer.authorize_spending("agent-001", 2.50, "gpt-4 call")

    # After operation completes, commit actual spend
    enforcer.commit_spending(reservation_id, 1.80)

    # Or release if operation was cancelled
    enforcer.release_reservation(reservation_id)
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger("kurultai.security.cost_enforcer")


class ReservationState(Enum):
    """Lifecycle states for a budget reservation."""
    PENDING = "pending"
    COMMITTED = "committed"
    RELEASED = "released"


@dataclass
class Reservation:
    """A spending reservation held against an agent budget.

    Attributes:
        reservation_id: Unique identifier for this reservation.
        agent_id: The agent that owns this reservation.
        amount: The reserved (maximum) spending amount.
        operation: Human-readable description of the operation.
        state: Current lifecycle state.
        created_at: Unix timestamp when reservation was created.
        committed_amount: Actual amount committed (may be less than reserved).
    """
    reservation_id: str
    agent_id: str
    amount: float
    operation: str
    state: ReservationState = ReservationState.PENDING
    created_at: float = field(default_factory=time.time)
    committed_amount: float = 0.0


@dataclass
class AgentBudget:
    """Tracks spending for a single agent within a rolling time window.

    Attributes:
        agent_id: The agent this budget belongs to.
        max_budget: Maximum spending allowed per window.
        window_start: Unix timestamp of when the current window began.
        total_committed: Total amount committed in the current window.
        total_reserved: Total amount currently reserved (pending).
    """
    agent_id: str
    max_budget: float
    window_start: float = field(default_factory=time.time)
    total_committed: float = 0.0
    total_reserved: float = 0.0


class BudgetExceededError(Exception):
    """Raised when an agent attempts to exceed its spending budget."""
    pass


class ReservationError(Exception):
    """Raised for invalid reservation operations (e.g., double commit)."""
    pass


class CostEnforcer:
    """Thread-safe per-agent budget enforcement with reservation semantics.

    The enforcer uses a rolling time window. When the window expires,
    committed and reserved totals are reset. Reservations hold budget
    capacity until they are committed or released.

    Args:
        default_budget: Default maximum spend per agent per window.
        budget_window_seconds: Duration of the rolling budget window in seconds.
        reservation_timeout_seconds: Timeout after which pending reservations
            are automatically expired and their budget released.
    """

    def __init__(
        self,
        default_budget: float = 10.0,
        budget_window_seconds: int = 3600,
        reservation_timeout_seconds: int = 300,
    ):
        if default_budget <= 0:
            raise ValueError("default_budget must be positive")
        if budget_window_seconds <= 0:
            raise ValueError("budget_window_seconds must be positive")

        self.default_budget = default_budget
        self.budget_window_seconds = budget_window_seconds
        self.reservation_timeout_seconds = reservation_timeout_seconds

        self._lock = threading.Lock()
        self._budgets: Dict[str, AgentBudget] = {}
        self._reservations: Dict[str, Reservation] = {}
        # Per-agent budget overrides
        self._budget_overrides: Dict[str, float] = {}

    def set_agent_budget(self, agent_id: str, max_budget: float) -> None:
        """Override the default budget for a specific agent.

        Args:
            agent_id: The agent to configure.
            max_budget: Custom maximum budget for this agent.
        """
        if max_budget <= 0:
            raise ValueError("max_budget must be positive")
        with self._lock:
            self._budget_overrides[agent_id] = max_budget
            # Update existing budget record if present
            if agent_id in self._budgets:
                self._budgets[agent_id].max_budget = max_budget

    def _get_or_create_budget(self, agent_id: str) -> AgentBudget:
        """Get or create budget tracker for an agent. Must hold _lock."""
        now = time.time()
        budget = self._budgets.get(agent_id)

        if budget is None:
            max_b = self._budget_overrides.get(agent_id, self.default_budget)
            budget = AgentBudget(agent_id=agent_id, max_budget=max_b, window_start=now)
            self._budgets[agent_id] = budget
            return budget

        # Check if window has expired -- reset if so
        if now - budget.window_start >= self.budget_window_seconds:
            budget.window_start = now
            budget.total_committed = 0.0
            budget.total_reserved = 0.0
            logger.info("Budget window reset for agent %s", agent_id)

        return budget

    def _expire_stale_reservations(self, agent_id: str) -> None:
        """Expire timed-out pending reservations. Must hold _lock."""
        now = time.time()
        expired_ids = []

        for res_id, res in self._reservations.items():
            if (
                res.agent_id == agent_id
                and res.state == ReservationState.PENDING
                and now - res.created_at > self.reservation_timeout_seconds
            ):
                expired_ids.append(res_id)

        for res_id in expired_ids:
            res = self._reservations[res_id]
            budget = self._budgets.get(res.agent_id)
            if budget is not None:
                budget.total_reserved = max(0.0, budget.total_reserved - res.amount)
            res.state = ReservationState.RELEASED
            logger.warning(
                "Reservation %s expired for agent %s (amount=%.4f, operation=%s)",
                res_id, res.agent_id, res.amount, res.operation,
            )

    def authorize_spending(
        self, agent_id: str, amount: float, operation: str
    ) -> str:
        """Reserve budget for an upcoming operation.

        The reserved amount is held against the agent budget until the
        reservation is committed or released.

        Args:
            agent_id: The agent requesting budget.
            amount: Maximum amount to reserve.
            operation: Description of the planned operation.

        Returns:
            A unique reservation_id string.

        Raises:
            BudgetExceededError: If the reservation would exceed the agent budget.
            ValueError: If amount is not positive.
        """
        if amount <= 0:
            raise ValueError("Spending amount must be positive")
        if not agent_id or not isinstance(agent_id, str):
            raise ValueError("agent_id must be a non-empty string")

        with self._lock:
            self._expire_stale_reservations(agent_id)
            budget = self._get_or_create_budget(agent_id)

            available = budget.max_budget - budget.total_committed - budget.total_reserved
            if amount > available:
                raise BudgetExceededError(
                    f"Agent '{agent_id}' budget exceeded: "
                    f"requested={amount:.4f}, available={available:.4f}, "
                    f"committed={budget.total_committed:.4f}, "
                    f"reserved={budget.total_reserved:.4f}, "
                    f"max={budget.max_budget:.4f}"
                )

            reservation_id = str(uuid.uuid4())
            reservation = Reservation(
                reservation_id=reservation_id,
                agent_id=agent_id,
                amount=amount,
                operation=operation,
            )
            self._reservations[reservation_id] = reservation
            budget.total_reserved += amount

            logger.info(
                "Budget reserved: agent=%s amount=%.4f operation=%s reservation=%s",
                agent_id, amount, operation, reservation_id,
            )
            return reservation_id

    def commit_spending(self, reservation_id: str, actual_amount: float) -> None:
        """Commit actual spending against a reservation.

        The committed amount may be less than or equal to the reserved
        amount. The difference is returned to the available budget.

        Args:
            reservation_id: ID returned by authorize_spending.
            actual_amount: Actual amount spent (must be <= reserved amount).

        Raises:
            ReservationError: If the reservation is not in PENDING state.
            ValueError: If actual_amount exceeds reserved amount.
        """
        if actual_amount < 0:
            raise ValueError("actual_amount cannot be negative")

        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise ReservationError(f"Reservation '{reservation_id}' not found")
            if reservation.state != ReservationState.PENDING:
                raise ReservationError(
                    f"Reservation '{reservation_id}' is already {reservation.state.value}"
                )
            if actual_amount > reservation.amount:
                raise ValueError(
                    f"Actual amount {actual_amount:.4f} exceeds reserved "
                    f"amount {reservation.amount:.4f}"
                )

            budget = self._get_or_create_budget(reservation.agent_id)
            budget.total_reserved = max(0.0, budget.total_reserved - reservation.amount)
            budget.total_committed += actual_amount

            reservation.state = ReservationState.COMMITTED
            reservation.committed_amount = actual_amount

            logger.info(
                "Spending committed: agent=%s actual=%.4f reserved=%.4f operation=%s",
                reservation.agent_id, actual_amount, reservation.amount, reservation.operation,
            )

    def release_reservation(self, reservation_id: str) -> None:
        """Release a pending reservation, returning budget to available.

        Args:
            reservation_id: ID returned by authorize_spending.

        Raises:
            ReservationError: If the reservation is not in PENDING state.
        """
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise ReservationError(f"Reservation '{reservation_id}' not found")
            if reservation.state != ReservationState.PENDING:
                raise ReservationError(
                    f"Reservation '{reservation_id}' is already {reservation.state.value}"
                )

            budget = self._get_or_create_budget(reservation.agent_id)
            budget.total_reserved = max(0.0, budget.total_reserved - reservation.amount)
            reservation.state = ReservationState.RELEASED

            logger.info(
                "Reservation released: agent=%s amount=%.4f operation=%s",
                reservation.agent_id, reservation.amount, reservation.operation,
            )

    def get_budget_remaining(self, agent_id: str) -> float:
        """Get the remaining available budget for an agent.

        This accounts for both committed spending and pending reservations.

        Args:
            agent_id: The agent to query.

        Returns:
            Remaining budget as a float. Returns the full default budget
            if the agent has no spending history.
        """
        with self._lock:
            budget = self._get_or_create_budget(agent_id)
            self._expire_stale_reservations(agent_id)
            return max(0.0, budget.max_budget - budget.total_committed - budget.total_reserved)

    def get_agent_summary(self, agent_id: str) -> dict:
        """Get a summary of an agent budget state.

        Args:
            agent_id: The agent to query.

        Returns:
            Dict with keys: agent_id, max_budget, committed, reserved,
            available, window_start.
        """
        with self._lock:
            budget = self._get_or_create_budget(agent_id)
            self._expire_stale_reservations(agent_id)
            available = max(0.0, budget.max_budget - budget.total_committed - budget.total_reserved)
            return {
                "agent_id": agent_id,
                "max_budget": budget.max_budget,
                "committed": budget.total_committed,
                "reserved": budget.total_reserved,
                "available": available,
                "window_start": budget.window_start,
            }
