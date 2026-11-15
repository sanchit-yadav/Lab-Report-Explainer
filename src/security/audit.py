"""HIPAA §164.312(b) Cryptographic Tamper-Evident Audit Trail Logger.

Maintains a Merkle-chained, append-only log of all clinical document access,
PHI de-identification events, model inferences, and report exports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Tuple
import uuid

logger = logging.getLogger("security.audit")

GENESIS_HASH = "0" * 64


@dataclass
class AuditRecord:
    """Immutable audit entry cryptographically bound to its predecessor."""
    entry_id: str
    timestamp: str
    event_type: str
    actor_id: str
    resource_id: str
    details: Dict[str, Any]
    previous_hash: str
    entry_hash: str

    def compute_hash(self) -> str:
        """Compute deterministic SHA-256 hash over payload and parent hash."""
        payload = {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "resource_id": self.resource_id,
            "details": self.details,
            "previous_hash": self.previous_hash,
        }
        canonical_json = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class SecurityAuditLogger:
    """Thread-safe cryptographic audit logger implementing HIPAA §164.312(b)."""

    _instance: Optional["SecurityAuditLogger"] = None
    _lock = threading.Lock()

    def __init__(self, log_file_path: Optional[Path] = None):
        self.log_file_path = log_file_path or Path("data/audit_log.jsonl")
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._chain: List[AuditRecord] = []
        self._file_lock = threading.Lock()
        self._load_chain_from_disk()

    @classmethod
    def get_instance(cls) -> "SecurityAuditLogger":
        """Singleton accessor."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_chain_from_disk(self) -> None:
        """Reconstruct in-memory chain from existing disk records."""
        if not self.log_file_path.exists():
            return

        with self._file_lock:
            self._chain = []
            try:
                for line in self.log_file_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    record = AuditRecord(**data)
                    self._chain.append(record)
            except Exception as e:
                logger.error(f"Error loading audit log from disk: {e}")

    @property
    def latest_hash(self) -> str:
        """Hash of the most recent log record or genesis hash."""
        return self._chain[-1].entry_hash if self._chain else GENESIS_HASH

    def log_event(
        self,
        event_type: str,
        actor_id: str,
        resource_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditRecord:
        """Append a new tamper-evident event to the cryptographic audit trail."""
        details = details or {}
        entry_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._file_lock:
            prev_hash = self.latest_hash
            record = AuditRecord(
                entry_id=entry_id,
                timestamp=timestamp,
                event_type=event_type,
                actor_id=actor_id,
                resource_id=resource_id,
                details=details,
                previous_hash=prev_hash,
                entry_hash="",
            )
            record.entry_hash = record.compute_hash()
            self._chain.append(record)

            # Persist immediately to append-only audit file
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(record)) + "\n")
            except Exception as e:
                logger.error(f"Failed to persist audit log record {entry_id}: {e}")

        logger.info(f"AUDIT [{event_type}] resource={resource_id} actor={actor_id} hash={record.entry_hash[:8]}...")
        return record

    def verify_integrity(self) -> Tuple[bool, Optional[str]]:
        """Verify the integrity of the entire audit chain.

        Returns:
            Tuple of (is_valid, error_description)
        """
        with self._file_lock:
            expected_prev = GENESIS_HASH

            for idx, record in enumerate(self._chain):
                # 1. Verify previous hash chaining
                if record.previous_hash != expected_prev:
                    return False, (
                        f"Broken chain linkage at record {idx} ({record.entry_id}): "
                        f"previous_hash '{record.previous_hash[:8]}' != expected '{expected_prev[:8]}'"
                    )

                # 2. Verify cryptographic hash integrity of the record itself
                recomputed = record.compute_hash()
                if record.entry_hash != recomputed:
                    return False, (
                        f"Tampered record at index {idx} ({record.entry_id}): "
                        f"entry_hash '{record.entry_hash[:8]}' != recomputed '{recomputed[:8]}'"
                    )

                expected_prev = record.entry_hash

            return True, None

    def get_records(
        self,
        resource_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[AuditRecord]:
        """Query audit trail records with optional filtering."""
        with self._file_lock:
            filtered = self._chain
            if resource_id:
                filtered = [r for r in filtered if r.resource_id == resource_id]
            if event_type:
                filtered = [r for r in filtered if r.event_type == event_type]
            return list(reversed(filtered))[:limit]

    def clear(self) -> None:
        """Clear audit log (used strictly for test isolation)."""
        with self._file_lock:
            self._chain.clear()
            if self.log_file_path.exists():
                self.log_file_path.write_text("", encoding="utf-8")
