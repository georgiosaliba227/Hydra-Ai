"""Single-authority SQLite gross-cost ledger. Integer USD microdollars only.

No network/credential handling. Must live at the one gateway, on local durable
storage; separate copies cannot enforce an account-wide cap. Never auto-release
reservations after crashes/timeouts. All failures deny admission.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

USD = 1_000_000
PER_ATTEMPT = 250_000


class BudgetDenied(Exception):
    pass


class MetaBudget:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=0.5)
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            if type(self) is MetaBudget and connection.execute("SELECT 1 FROM sqlite_master WHERE name='live_accounts'").fetchone():
                raise BudgetDenied("Legacy shared ledger is disabled after account-specific ledger initialization")
            yield connection
            connection.commit()
        except (sqlite3.Error, OSError):
            if connection:
                connection.rollback()
            raise BudgetDenied("Ledger unavailable; inference blocked") from None
        finally:
            if connection:
                connection.close()

    def initialize(self, *, historical_micro_usd: int, reconciliation_reference: str) -> None:
        """Operator-only one-time baseline. Does NOT authorize live use."""
        self.amount(historical_micro_usd, allow_zero=True)
        if not reconciliation_reference.strip():
            raise BudgetDenied("Reconciliation evidence required")
        with self.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS meta_policy (id INTEGER PRIMARY KEY CHECK(id=1), baseline INTEGER NOT NULL, approved INTEGER NOT NULL DEFAULT 0, further INTEGER NOT NULL DEFAULT 0, frozen INTEGER NOT NULL DEFAULT 0, price_version TEXT, price_expires INTEGER, evidence TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS meta_attempts (id TEXT PRIMARY KEY, parent TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER, provider_id TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS meta_events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, reference TEXT NOT NULL)")
            if db.execute("SELECT 1 FROM meta_policy").fetchone():
                raise BudgetDenied("Existing ledger cannot be reset")
            db.execute("INSERT INTO meta_policy(id,baseline,evidence) VALUES(1,?,?)", (historical_micro_usd, reconciliation_reference))
            db.execute("INSERT INTO meta_events(kind,reference) VALUES('baseline',?)", (reconciliation_reference,))

    @staticmethod
    def amount(value: int, *, allow_zero: bool = False) -> None:
        if type(value) is not int or value < (0 if allow_zero else 1):
            raise BudgetDenied("Known nonnegative integer cost required")

    @staticmethod
    def exposure(db: sqlite3.Connection) -> int:
        row = db.execute("SELECT baseline FROM meta_policy WHERE id=1").fetchone()
        if row is None:
            raise BudgetDenied("Reconciled policy required")
        return row[0] + db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM meta_attempts").fetchone()[0]

    def record_approval(self, *, reference: str, price_version: str, valid_until: datetime, further_spend: bool = False) -> None:
        """Operator-only evidence after human review; never called by API/mock flow.

        Price version identifies reviewed charge bounds and has an explicit expiry.
        The operator must verify the evidence before recording approval.
        """
        if not reference.strip() or not price_version.strip() or type(further_spend) is not bool:
            raise BudgetDenied("Explicit approval and verified prices required")
        if valid_until.tzinfo is None or valid_until <= datetime.now(timezone.utc):
            raise BudgetDenied("Current price validity required")
        with self.transaction() as db:
            if db.execute("UPDATE meta_policy SET approved=1, further=?, price_version=?, price_expires=? WHERE id=1 AND frozen=0", (int(further_spend), price_version, int(valid_until.timestamp()))).rowcount != 1:
                raise BudgetDenied("Policy unavailable or frozen")
            db.execute("INSERT INTO meta_events(kind,reference) VALUES('approval',?)", (reference,))

    def reserve(self, attempt: str, parent: str, maximum_micro_usd: int, *, price_version: str) -> None:
        """Unique reservation is a one-time dispatch permit; replays always deny.

        Max two attempts per parent and $0.50 total reserved ceiling. Each attempt
        may cost at most $0.25. Unknown price/bounds must never call this method.
        """
        self.amount(maximum_micro_usd)
        try:
            UUID(attempt); UUID(parent)
        except (ValueError, TypeError, AttributeError):
            raise BudgetDenied("Attempt and parent identifiers required") from None
        if maximum_micro_usd > PER_ATTEMPT:
            raise BudgetDenied("Per-attempt limit exceeded")
        with self.transaction() as db:
            policy = db.execute("SELECT approved,further,frozen,price_version,price_expires FROM meta_policy WHERE id=1").fetchone()
            if not policy or not policy[0] or policy[2] or not price_version or policy[3] != price_version or policy[4] is None or policy[4] <= datetime.now(timezone.utc).timestamp():
                raise BudgetDenied("Approval or current verified price missing")
            if db.execute("SELECT 1 FROM meta_attempts WHERE id=?", (attempt,)).fetchone():
                raise BudgetDenied("Attempt already reserved; never redispatch")
            count, reserved = db.execute("SELECT COUNT(*),COALESCE(SUM(reserved),0) FROM meta_attempts WHERE parent=?", (parent,)).fetchone()
            if count >= 2 or reserved + maximum_micro_usd > 2 * PER_ATTEMPT:
                raise BudgetDenied("Request retry limit exceeded")
            total = self.exposure(db) + maximum_micro_usd
            if total >= 120 * USD or (total >= 100 * USD and not policy[1]):
                raise BudgetDenied("Shared spending threshold reached")
            db.execute("INSERT INTO meta_attempts(id,parent,reserved) VALUES(?,?,?)", (attempt, parent, maximum_micro_usd))
            db.execute("INSERT INTO meta_events(kind,reference) VALUES('reserve',?)", (attempt,))
            if total >= 75 * USD and not db.execute("SELECT 1 FROM meta_events WHERE kind='notify_both_75_pending'").fetchone():
                db.execute("INSERT INTO meta_events(kind,reference) VALUES('notify_both_75_pending','georgiosaliba227,aminealichaouche')")

    def settle(self, attempt: str, actual_micro_usd: int, *, provider_id: str) -> None:
        self.amount(actual_micro_usd, allow_zero=True)
        if not provider_id.strip():
            raise BudgetDenied("Authoritative provider usage required")
        blocked_reason = None
        with self.transaction() as db:
            row = db.execute("SELECT reserved,actual,provider_id FROM meta_attempts WHERE id=?", (attempt,)).fetchone()
            if row is None:
                raise BudgetDenied("Unknown reservation")
            if row[1] is not None:
                if row[1:] == (actual_micro_usd, provider_id):
                    return
                # Commit the freeze even though conflicting usage cannot replace
                # the previous settlement; operator reconciliation is required.
                blocked_reason = "Conflicting settlement; ledger frozen"
                db.execute("UPDATE meta_policy SET frozen=1 WHERE id=1")
                db.execute("INSERT INTO meta_events(kind,reference) VALUES('settlement_conflict',?)", (attempt,))
            else:
                db.execute("UPDATE meta_attempts SET actual=?,provider_id=? WHERE id=?", (actual_micro_usd, provider_id, attempt))
                if actual_micro_usd > row[0]:
                    db.execute("UPDATE meta_policy SET frozen=1 WHERE id=1")
                    blocked_reason = "Charge exceeded reservation; ledger frozen"
                db.execute("INSERT INTO meta_events(kind,reference) VALUES('settle',?)", (attempt,))
        if blocked_reason:
            raise BudgetDenied(blocked_reason)

    def freeze(self, reference: str) -> None:
        if not reference.strip():
            raise BudgetDenied("Audit reference required")
        with self.transaction() as db:
            db.execute("UPDATE meta_policy SET frozen=1 WHERE id=1")
            db.execute("INSERT INTO meta_events(kind,reference) VALUES('freeze',?)", (reference,))

    def snapshot(self) -> dict:
        with self.transaction() as db:
            return {"exposure_micro_usd": self.exposure(db),
                    "events": db.execute("SELECT kind,reference FROM meta_events ORDER BY id").fetchall()}
