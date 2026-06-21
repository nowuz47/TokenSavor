from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from pathlib import Path
import re
from uuid import uuid4

from scrooge.config import Settings
from scrooge.pricing import calculate_cost
from scrooge.schemas import (
    AttachmentMetadata,
    AttachmentTokenStatus,
    CaptureSource,
    CompatibilityRunRequest,
    DeliveryStatus,
    HotkeyEventRequest,
    MeasurementRequest,
    MeasurementStatus,
    OptimizeResponse,
    TokenBreakdown,
    TokenizerConfidence,
    UsageState,
)


COMPATIBILITY_TARGETS = ("codex_desktop", "claude_code", "gemini_cli", "cursor", "windsurf")
COMPATIBILITY_REQUIRED_ATTEMPTS = 100


def _sqlite_path(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        return database_url.removeprefix("sqlite:///")
    if database_url.startswith("sqlite://"):
        return database_url.removeprefix("sqlite://")
    return database_url


class UsageStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = _sqlite_path(settings.database_url)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            self._init_db_schema(connection)
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_db(self) -> None:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            self._init_db_schema(connection)
            connection.commit()
        finally:
            connection.close()

    def _init_db_schema(self, db: sqlite3.Connection) -> None:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_records (
                request_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                task_type TEXT NOT NULL,
                state TEXT NOT NULL,
                original_hash TEXT NOT NULL,
                optimized_hash TEXT NOT NULL,
                original_prompt TEXT,
                optimized_prompt TEXT,
                estimated_original_tokens INTEGER,
                estimated_optimized_tokens INTEGER,
                original_tokens INTEGER NOT NULL,
                optimized_tokens INTEGER NOT NULL,
                saved_tokens INTEGER NOT NULL,
                original_cost_usd REAL NOT NULL,
                optimized_cost_usd REAL NOT NULL,
                saved_cost_usd REAL NOT NULL,
                tokenizer_version TEXT NOT NULL,
                pricing_version TEXT NOT NULL,
                pricing_source_url TEXT NOT NULL,
                applied_rules TEXT NOT NULL,
                measured_original_tokens INTEGER,
                measured_input_tokens INTEGER,
                measured_output_tokens INTEGER,
                measurement_source TEXT,
                decision_notes TEXT,
                request_family_hash TEXT,
                provider_usage_source TEXT,
                upstream_status INTEGER,
                capture_source TEXT,
                delivery_status TEXT,
                measurement_status TEXT,
                failure_reason TEXT,
                tokenizer_confidence TEXT,
                possible_attachment_reference INTEGER,
                prompt_savings_rate REAL,
                total_savings_rate REAL
            )
            """
        )
        self._ensure_column(db, "usage_records", "estimated_original_tokens", "INTEGER")
        self._ensure_column(db, "usage_records", "estimated_optimized_tokens", "INTEGER")
        self._ensure_column(db, "usage_records", "measured_original_tokens", "INTEGER")
        self._ensure_column(db, "usage_records", "measurement_source", "TEXT")
        self._ensure_column(db, "usage_records", "decision_notes", "TEXT")
        self._ensure_column(db, "usage_records", "request_family_hash", "TEXT")
        self._ensure_column(db, "usage_records", "provider_usage_source", "TEXT")
        self._ensure_column(db, "usage_records", "upstream_status", "INTEGER")
        self._ensure_column(db, "usage_records", "capture_source", "TEXT")
        self._ensure_column(db, "usage_records", "delivery_status", "TEXT")
        self._ensure_column(db, "usage_records", "measurement_status", "TEXT")
        self._ensure_column(db, "usage_records", "failure_reason", "TEXT")
        self._ensure_column(db, "usage_records", "tokenizer_confidence", "TEXT")
        self._ensure_column(db, "usage_records", "possible_attachment_reference", "INTEGER")
        self._ensure_column(db, "usage_records", "prompt_savings_rate", "REAL")
        self._ensure_column(db, "usage_records", "total_savings_rate", "REAL")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS request_attachments (
                attachment_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                name TEXT NOT NULL,
                mime_type TEXT,
                size_bytes INTEGER,
                content_hash TEXT,
                token_status TEXT NOT NULL,
                estimated_tokens INTEGER,
                measured_tokens INTEGER,
                original_tokens INTEGER,
                optimized_tokens INTEGER,
                saved_tokens INTEGER,
                savings_rate REAL,
                measurement_source TEXT,
                discovery_source TEXT,
                content_available INTEGER,
                path_available INTEGER,
                read_error TEXT,
                FOREIGN KEY(request_id) REFERENCES usage_records(request_id) ON DELETE CASCADE
            )
            """
        )
        self._ensure_column(db, "request_attachments", "original_tokens", "INTEGER")
        self._ensure_column(db, "request_attachments", "optimized_tokens", "INTEGER")
        self._ensure_column(db, "request_attachments", "saved_tokens", "INTEGER")
        self._ensure_column(db, "request_attachments", "savings_rate", "REAL")
        self._ensure_column(db, "request_attachments", "measurement_source", "TEXT")
        self._ensure_column(db, "request_attachments", "discovery_source", "TEXT")
        self._ensure_column(db, "request_attachments", "content_available", "INTEGER")
        self._ensure_column(db, "request_attachments", "path_available", "INTEGER")
        self._ensure_column(db, "request_attachments", "read_error", "TEXT")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS hotkey_events (
                event_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                request_id TEXT,
                status TEXT NOT NULL,
                failure_reason TEXT,
                saved_tokens INTEGER NOT NULL,
                elapsed_ms INTEGER,
                discovered_attachment_count INTEGER,
                content_available_attachment_count INTEGER,
                unknown_attachment_count INTEGER,
                unsupported_attachment_count INTEGER
            )
            """
        )
        self._ensure_column(db, "hotkey_events", "discovered_attachment_count", "INTEGER")
        self._ensure_column(db, "hotkey_events", "content_available_attachment_count", "INTEGER")
        self._ensure_column(db, "hotkey_events", "unknown_attachment_count", "INTEGER")
        self._ensure_column(db, "hotkey_events", "unsupported_attachment_count", "INTEGER")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS compatibility_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                target_app TEXT NOT NULL,
                target_version TEXT,
                verification_mode TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                successes INTEGER NOT NULL,
                failures INTEGER NOT NULL,
                prompt_loss_count INTEGER NOT NULL,
                failure_reasons TEXT NOT NULL,
                notes TEXT
            )
            """
        )
        db.execute(
            """
            UPDATE usage_records
            SET
                estimated_original_tokens = COALESCE(estimated_original_tokens, original_tokens),
                estimated_optimized_tokens = COALESCE(estimated_optimized_tokens, optimized_tokens),
                request_family_hash = COALESCE(request_family_hash, original_hash),
                capture_source = COALESCE(capture_source, 'manual'),
                delivery_status = COALESCE(
                    delivery_status,
                    CASE
                        WHEN state = 'measured' THEN 'measured'
                        WHEN state = 'sent' AND capture_source = 'proxy' THEN 'sent_proxy'
                        WHEN state = 'sent' THEN 'copied'
                        WHEN state = 'rejected' THEN 'not_used'
                        WHEN state = 'failed' THEN 'failed'
                        ELSE 'previewed'
                    END
                ),
                measurement_status = COALESCE(
                    measurement_status,
                    CASE
                        WHEN state = 'measured' THEN 'measured'
                        WHEN provider_usage_source IS NULL THEN 'estimated'
                        ELSE 'unavailable'
                    END
                ),
                tokenizer_confidence = COALESCE(tokenizer_confidence, 'heuristic_fallback'),
                possible_attachment_reference = COALESCE(possible_attachment_reference, 0),
                prompt_savings_rate = COALESCE(
                    prompt_savings_rate,
                    CASE WHEN original_tokens > 0 THEN saved_tokens * 1.0 / original_tokens ELSE 0 END
                )
            """
        )

    def _ensure_column(
        self,
        db: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def save_preview(
        self,
        response: OptimizeResponse,
        provider: str,
        model: str,
        capture_source: CaptureSource = CaptureSource.MANUAL,
        attachments: list[AttachmentMetadata] | None = None,
    ) -> None:
        original_prompt = response.original_prompt if self.settings.store_prompt_bodies else None
        optimized_prompt = response.optimized_prompt if self.settings.store_prompt_bodies else None
        with self.connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO usage_records (
                    request_id, created_at, provider, model, task_type, state,
                    original_hash, optimized_hash, original_prompt, optimized_prompt,
                    estimated_original_tokens, estimated_optimized_tokens,
                    original_tokens, optimized_tokens, saved_tokens,
                    original_cost_usd, optimized_cost_usd, saved_cost_usd,
                    tokenizer_version, pricing_version, pricing_source_url, applied_rules,
                    request_family_hash, capture_source, delivery_status, measurement_status,
                    tokenizer_confidence, possible_attachment_reference, prompt_savings_rate,
                    total_savings_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response.request_id,
                    response.created_at.isoformat(),
                    provider,
                    model,
                    response.task_type.value,
                    UsageState.ESTIMATED.value,
                    _hash_text(response.original_prompt),
                    _hash_text(response.optimized_prompt),
                    original_prompt,
                    optimized_prompt,
                    response.original_tokens.input_tokens,
                    response.optimized_tokens.input_tokens,
                    response.original_tokens.input_tokens,
                    response.optimized_tokens.input_tokens,
                    response.saved_tokens,
                    response.original_cost.total_cost_usd,
                    response.optimized_cost.total_cost_usd,
                    response.saved_cost_usd,
                    response.optimized_tokens.tokenizer,
                    response.optimized_cost.pricing_version,
                    response.optimized_cost.source_url,
                    ",".join(reason.rule_id for reason in response.reasons),
                    _family_hash(provider, model, response.task_type.value, response.original_prompt),
                    capture_source.value,
                    DeliveryStatus.PREVIEWED.value,
                    MeasurementStatus.ESTIMATED.value,
                    response.optimized_tokens.tokenizer_confidence.value,
                    1 if response.attachment_summary.possible_attachment_reference else 0,
                    response.prompt_savings_rate,
                    response.total_savings_rate,
                ),
            )
            self._replace_attachments(db, response.request_id, attachments or [])

    def mark_state(
        self,
        request_id: str,
        state: UsageState,
        notes: str | None = None,
        upstream_status: int | None = None,
        failure_reason: str | None = None,
    ) -> None:
        with self.connect() as db:
            delivery_status = _delivery_status_for_state(state)
            measurement_status = MeasurementStatus.MEASURED.value if state == UsageState.MEASURED else None
            cursor = db.execute(
                """
                UPDATE usage_records
                SET
                    state = ?,
                    decision_notes = COALESCE(?, decision_notes),
                    upstream_status = COALESCE(?, upstream_status),
                    failure_reason = COALESCE(?, failure_reason),
                    delivery_status = CASE
                        WHEN ? IS NOT NULL AND ? = 'sent' AND capture_source = 'proxy' THEN 'sent_proxy'
                        WHEN ? IS NOT NULL THEN ?
                        ELSE delivery_status
                    END,
                    measurement_status = COALESCE(?, measurement_status)
                WHERE request_id = ?
                """,
                (
                    state.value,
                    notes,
                    upstream_status,
                    failure_reason,
                    delivery_status,
                    state.value,
                    delivery_status,
                    delivery_status,
                    measurement_status,
                    request_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(request_id)

    def record_hotkey_event(self, event: HotkeyEventRequest) -> dict[str, str]:
        event_id = uuid4().hex
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO hotkey_events (
                    event_id, created_at, request_id, status, failure_reason, saved_tokens, elapsed_ms,
                    discovered_attachment_count, content_available_attachment_count,
                    unknown_attachment_count, unsupported_attachment_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    datetime.now(timezone.utc).isoformat(),
                    event.request_id,
                    event.status,
                    event.failure_reason,
                    event.saved_tokens,
                    event.elapsed_ms,
                    event.discovered_attachment_count,
                    event.content_available_attachment_count,
                    event.unknown_attachment_count,
                    event.unsupported_attachment_count,
                ),
            )
            if event.request_id:
                db.execute(
                    """
                    UPDATE usage_records
                    SET
                        state = COALESCE(?, state),
                        delivery_status = COALESCE(?, delivery_status),
                        failure_reason = COALESCE(?, failure_reason),
                        decision_notes = COALESCE(?, decision_notes)
                    WHERE request_id = ?
                    """,
                    (
                        _usage_state_for_hotkey_status(event.status),
                        _delivery_status_for_hotkey_status(event.status),
                        event.failure_reason,
                        _decision_note_for_hotkey_status(event.status),
                        event.request_id,
                    ),
                )
        return {"event_id": event_id, "status": event.status}

    def record_compatibility_run(self, run: CompatibilityRunRequest) -> dict[str, object]:
        run_id = uuid4().hex
        created_at = datetime.now(timezone.utc)
        attempts = max(run.attempts, run.successes + run.failures)
        failures = max(run.failures, attempts - run.successes)
        success_rate = _success_rate(attempts, run.successes)
        status = _compatibility_status(attempts, success_rate, run.prompt_loss_count)
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO compatibility_runs (
                    run_id, created_at, target_app, target_version, verification_mode,
                    attempts, successes, failures, prompt_loss_count, failure_reasons, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    created_at.isoformat(),
                    run.target_app,
                    run.target_version,
                    run.verification_mode,
                    attempts,
                    run.successes,
                    failures,
                    run.prompt_loss_count,
                    json.dumps(run.failure_reasons, ensure_ascii=False),
                    run.notes,
                ),
            )
        return {
            "run_id": run_id,
            "target_app": run.target_app,
            "status": status,
            "attempts": attempts,
            "successes": run.successes,
            "failures": failures,
            "success_rate": success_rate,
            "prompt_loss_count": run.prompt_loss_count,
            "verified_at": created_at,
        }

    def compatibility_status(self) -> dict[str, object]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT *
                FROM compatibility_runs
                ORDER BY datetime(created_at) DESC, rowid DESC
                """
            ).fetchall()
        latest_by_target: dict[str, sqlite3.Row] = {}
        for row in rows:
            target = str(row["target_app"])
            if target not in latest_by_target:
                latest_by_target[target] = row
        targets = []
        for target in COMPATIBILITY_TARGETS:
            row = latest_by_target.get(target)
            if row is None:
                targets.append(
                    {
                        "target_app": target,
                        "status": "pending_real_test",
                        "attempts": 0,
                        "successes": 0,
                        "failures": 0,
                        "success_rate": 0,
                        "prompt_loss_count": 0,
                        "required_attempts": COMPATIBILITY_REQUIRED_ATTEMPTS,
                        "last_verified_at": None,
                        "failure_reasons": [],
                    }
                )
                continue
            attempts = int(row["attempts"] or 0)
            successes = int(row["successes"] or 0)
            prompt_loss_count = int(row["prompt_loss_count"] or 0)
            success_rate = _success_rate(attempts, successes)
            targets.append(
                {
                    "target_app": target,
                    "status": _compatibility_status(attempts, success_rate, prompt_loss_count),
                    "attempts": attempts,
                    "successes": successes,
                    "failures": int(row["failures"] or 0),
                    "success_rate": success_rate,
                    "prompt_loss_count": prompt_loss_count,
                    "required_attempts": COMPATIBILITY_REQUIRED_ATTEMPTS,
                    "last_verified_at": row["created_at"],
                    "failure_reasons": _json_list(row["failure_reasons"]),
                }
            )
        codex = next(item for item in targets if item["target_app"] == "codex_desktop")
        if codex["status"] == "verified":
            overall_status = "verified"
        elif codex["status"] == "failed":
            overall_status = "failed"
        elif codex["attempts"]:
            overall_status = "limited"
        else:
            overall_status = "pending_real_test"
        return {"overall_status": overall_status, "targets": targets}

    def recent_failures(self, limit: int = 20) -> list[dict[str, object]]:
        with self.connect() as db:
            usage_rows = db.execute(
                """
                SELECT request_id, created_at, capture_source, delivery_status, failure_reason, upstream_status
                FROM usage_records
                WHERE state = 'failed' OR failure_reason IS NOT NULL
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            hotkey_rows = db.execute(
                """
                SELECT event_id, created_at, status, failure_reason
                FROM hotkey_events
                WHERE failure_reason IS NOT NULL OR status IN ('backend_failed', 'clipboard_failed', 'paste_failed', 'failed')
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        failures: list[dict[str, object]] = []
        for row in usage_rows:
            failures.append(
                {
                    "kind": "usage_record",
                    "id": row["request_id"],
                    "created_at": row["created_at"],
                    "source": row["capture_source"],
                    "status": row["delivery_status"],
                    "reason": row["failure_reason"],
                    "upstream_status": row["upstream_status"],
                }
            )
        for row in hotkey_rows:
            failures.append(
                {
                    "kind": "hotkey_event",
                    "id": row["event_id"],
                    "created_at": row["created_at"],
                    "source": "hotkey",
                    "status": row["status"],
                    "reason": row["failure_reason"],
                    "upstream_status": None,
                }
            )
        return sorted(failures, key=lambda item: str(item["created_at"]), reverse=True)[:limit]

    def record_measurement(
        self,
        request_id: str,
        measurement: MeasurementRequest,
    ) -> dict[str, object]:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT
                    provider, model, original_tokens, optimized_tokens,
                    estimated_original_tokens, estimated_optimized_tokens
                FROM usage_records
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)

            estimated_original = int(row["estimated_original_tokens"] or row["original_tokens"] or 0)
            estimated_optimized = int(row["estimated_optimized_tokens"] or row["optimized_tokens"] or 0)
            measured_original = measurement.measured_original_tokens
            if measured_original is None:
                measured_original = estimated_original
            measured_optimized = measurement.measured_input_tokens
            measured_output = measurement.measured_output_tokens
            measured_total_input = measurement.measured_total_input_tokens
            saved_tokens = max(0, measured_original - measured_optimized)
            original_cost = calculate_cost(
                TokenBreakdown(
                    input_tokens=measured_original,
                    tokenizer="provider-measured",
                    is_estimate=False,
                    tokenizer_confidence=TokenizerConfidence.PROVIDER_MEASURED,
                ),
                row["provider"],
                row["model"],
                measured_output,
            )
            optimized_cost = calculate_cost(
                TokenBreakdown(
                    input_tokens=measured_optimized,
                    tokenizer="provider-measured",
                    is_estimate=False,
                    tokenizer_confidence=TokenizerConfidence.PROVIDER_MEASURED,
                ),
                row["provider"],
                row["model"],
                measured_output,
            )
            saved_cost = round(max(0.0, original_cost.total_cost_usd - optimized_cost.total_cost_usd), 8)
            db.execute(
                """
                UPDATE usage_records
                SET
                    state = ?,
                    original_tokens = ?,
                    optimized_tokens = ?,
                    saved_tokens = ?,
                    original_cost_usd = ?,
                    optimized_cost_usd = ?,
                    saved_cost_usd = ?,
                    measured_original_tokens = ?,
                    measured_input_tokens = ?,
                    measured_output_tokens = ?,
                    measurement_source = ?,
                    provider_usage_source = ?,
                    upstream_status = COALESCE(?, upstream_status),
                    delivery_status = ?,
                    measurement_status = ?,
                    tokenizer_confidence = ?,
                    pricing_version = ?,
                    pricing_source_url = ?,
                    total_savings_rate = COALESCE(?, total_savings_rate)
                WHERE request_id = ?
                """,
                (
                    UsageState.MEASURED.value,
                    measured_original,
                    measured_optimized,
                    saved_tokens,
                    original_cost.total_cost_usd,
                    optimized_cost.total_cost_usd,
                    saved_cost,
                    measured_original,
                    measured_optimized,
                    measured_output,
                    measurement.source,
                    measurement.source,
                    measurement.upstream_status,
                    DeliveryStatus.MEASURED.value,
                    MeasurementStatus.MEASURED.value,
                    "provider_measured",
                    optimized_cost.pricing_version,
                    optimized_cost.source_url,
                    _total_savings_rate(measured_original, measured_optimized, measured_total_input),
                    request_id,
                ),
            )
            if measured_total_input is not None and measurement.source != "measured_controlled":
                measured_attachment_tokens = max(0, measured_total_input - measured_optimized)
                db.execute(
                    """
                    UPDATE request_attachments
                    SET token_status = ?, measured_tokens = ?, measurement_source = COALESCE(?, measurement_source)
                    WHERE request_id = ?
                    """,
                    (
                        AttachmentTokenStatus.MEASURED.value,
                        measured_attachment_tokens,
                        "measured_provider",
                        request_id,
                    ),
                )

        return {
            "request_id": request_id,
            "state": UsageState.MEASURED,
            "estimated_input_tokens": estimated_optimized,
            "measured_input_tokens": measured_optimized,
            "token_error_rate": _token_error_rate(estimated_optimized, measured_optimized),
        }

    def list_records(self, limit: int = 100) -> list[dict[str, object]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT
                    request_id, created_at, provider, model, task_type, state,
                    original_hash, optimized_hash, original_tokens, optimized_tokens,
                    saved_tokens, saved_cost_usd, pricing_version, applied_rules,
                    tokenizer_version, estimated_optimized_tokens, measured_original_tokens,
                    measured_input_tokens, measured_output_tokens, decision_notes,
                    provider_usage_source, upstream_status, capture_source, failure_reason,
                    delivery_status, measurement_status, tokenizer_confidence,
                    possible_attachment_reference, prompt_savings_rate, total_savings_rate
                FROM usage_records
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            attachment_rows = db.execute(
                """
                SELECT
                    request_id,
                    COUNT(*) as attachment_count,
                    SUM(CASE WHEN token_status = 'unknown' THEN 1 ELSE 0 END) as unknown_count,
                    SUM(CASE WHEN token_status = 'measured' THEN 1 ELSE 0 END) as measured_count,
                    SUM(estimated_tokens) as estimated_tokens,
                    SUM(measured_tokens) as measured_tokens,
                    SUM(original_tokens) as original_tokens,
                    SUM(optimized_tokens) as optimized_tokens,
                    SUM(saved_tokens) as saved_tokens,
                    GROUP_CONCAT(DISTINCT measurement_source) as measurement_source,
                    GROUP_CONCAT(DISTINCT discovery_source) as discovery_source,
                    SUM(CASE WHEN content_available = 1 THEN 1 ELSE 0 END) as content_available_count,
                    SUM(CASE WHEN path_available = 1 THEN 1 ELSE 0 END) as path_available_count,
                    SUM(CASE WHEN read_error IS NOT NULL AND read_error != '' THEN 1 ELSE 0 END) as read_error_count
                FROM request_attachments
                GROUP BY request_id
                """
            ).fetchall()
        attachments_by_request = {
            row["request_id"]: {
                "attachment_count": int(row["attachment_count"] or 0),
                "unknown_count": int(row["unknown_count"] or 0),
                "measured_count": int(row["measured_count"] or 0),
                "estimated_tokens": row["estimated_tokens"],
                "measured_tokens": row["measured_tokens"],
                "original_tokens": row["original_tokens"],
                "optimized_tokens": row["optimized_tokens"],
                "saved_tokens": row["saved_tokens"],
                "measurement_source": row["measurement_source"],
                "discovery_source": row["discovery_source"],
                "content_available_count": int(row["content_available_count"] or 0),
                "path_available_count": int(row["path_available_count"] or 0),
                "read_error_count": int(row["read_error_count"] or 0),
            }
            for row in attachment_rows
        }

        records: list[dict[str, object]] = []
        for row in rows:
            original_tokens = int(row["original_tokens"] or 0)
            saved_tokens = int(row["saved_tokens"] or 0)
            estimated_optimized = int(row["estimated_optimized_tokens"] or row["optimized_tokens"] or 0)
            measured_input = row["measured_input_tokens"]
            attachment = attachments_by_request.get(str(row["request_id"]), {})
            attachment_count = int(attachment.get("attachment_count", 0) or 0)
            possible_reference = bool(row["possible_attachment_reference"])
            attachment_status = _attachment_status(
                attachment_count,
                possible_reference,
                int(attachment.get("unknown_count", 0) or 0),
                int(attachment.get("measured_count", 0) or 0),
            )
            records.append(
                {
                    "request_id": row["request_id"],
                    "created_at": row["created_at"],
                    "provider": row["provider"],
                    "model": row["model"],
                    "task_type": row["task_type"],
                    "state": row["state"],
                    "original_hash": row["original_hash"],
                    "optimized_hash": row["optimized_hash"],
                    "original_tokens": original_tokens,
                    "optimized_tokens": int(row["optimized_tokens"] or 0),
                    "saved_tokens": saved_tokens,
                    "saved_cost_usd": round(float(row["saved_cost_usd"] or 0), 8),
                    "savings_rate": round(saved_tokens / original_tokens, 4) if original_tokens else 0,
                    "pricing_version": row["pricing_version"],
                    "applied_rules": [
                        rule for rule in str(row["applied_rules"] or "").split(",") if rule
                    ],
                    "tokenizer_version": row["tokenizer_version"],
                    "measured_original_tokens": row["measured_original_tokens"],
                    "measured_input_tokens": measured_input,
                    "measured_output_tokens": row["measured_output_tokens"],
                    "rejection_reason": _rejection_reason(
                        row["state"],
                        row["decision_notes"],
                        saved_tokens,
                        original_tokens,
                        int(row["optimized_tokens"] or 0),
                    ),
                    "provider_usage_source": row["provider_usage_source"],
                    "upstream_status": row["upstream_status"],
                    "capture_source": row["capture_source"] or CaptureSource.MANUAL.value,
                    "delivery_status": row["delivery_status"] or DeliveryStatus.PREVIEWED.value,
                    "measurement_status": row["measurement_status"] or MeasurementStatus.ESTIMATED.value,
                    "failure_reason": row["failure_reason"],
                    "tokenizer_confidence": row["tokenizer_confidence"] or "heuristic_fallback",
                    "token_error_rate": (
                        _token_error_rate(estimated_optimized, int(measured_input))
                        if measured_input is not None
                        else None
                    ),
                    "attachment_count": attachment_count,
                    "attachment_token_status": attachment_status,
                    "attachment_estimated_tokens": attachment.get("estimated_tokens"),
                    "attachment_measured_tokens": attachment.get("measured_tokens"),
                    "attachment_original_tokens": attachment.get("original_tokens"),
                    "attachment_optimized_tokens": attachment.get("optimized_tokens"),
                    "attachment_saved_tokens": attachment.get("saved_tokens"),
                    "attachment_savings_rate": (
                        round(float(attachment.get("saved_tokens") or 0) / float(attachment.get("original_tokens") or 0), 4)
                        if attachment.get("original_tokens")
                        else None
                    ),
                    "attachment_measurement_source": attachment.get("measurement_source"),
                    "attachment_discovery_source": attachment.get("discovery_source"),
                    "attachment_content_available_count": attachment.get("content_available_count", 0),
                    "attachment_path_available_count": attachment.get("path_available_count", 0),
                    "attachment_read_error_count": attachment.get("read_error_count", 0),
                    "possible_attachment_reference": possible_reference,
                    "prompt_savings_rate": round(float(row["prompt_savings_rate"] or 0), 4),
                    "total_savings_rate": (
                        round(float(row["total_savings_rate"]), 4)
                        if row["total_savings_rate"] is not None
                        else None
                    ),
                }
            )
        return records

    def clear_records(self) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM usage_records")
            db.execute("DELETE FROM request_attachments")
            db.execute("DELETE FROM hotkey_events")

    def summary(self, period: str = "month") -> dict[str, float | int | str]:
        where = _period_clause(period)
        with self.connect() as db:
            row = db.execute(
                f"""
                SELECT
                    COUNT(*) as total_requests,
                    SUM(CASE WHEN state IN ('sent', 'measured') THEN 1 ELSE 0 END) as approved_requests,
                    SUM(CASE WHEN state = 'rejected' THEN 1 ELSE 0 END) as rejected_requests,
                    SUM(original_tokens) as original_tokens,
                    SUM(optimized_tokens) as optimized_tokens,
                    SUM(saved_tokens) as saved_tokens,
                    SUM(original_cost_usd) as original_cost_usd,
                    SUM(optimized_cost_usd) as optimized_cost_usd,
                    SUM(saved_cost_usd) as saved_cost_usd,
                    SUM(CASE WHEN state = 'measured' THEN 1 ELSE 0 END) as measured_requests,
                    AVG(
                        CASE
                            WHEN measured_input_tokens IS NOT NULL
                            AND COALESCE(estimated_optimized_tokens, optimized_tokens) > 0
                            THEN ABS(measured_input_tokens - COALESCE(estimated_optimized_tokens, optimized_tokens)) * 1.0
                                / COALESCE(estimated_optimized_tokens, optimized_tokens)
                            ELSE NULL
                        END
                    ) as avg_token_error_rate,
                    MAX(
                        CASE
                            WHEN measured_input_tokens IS NOT NULL
                            AND COALESCE(estimated_optimized_tokens, optimized_tokens) > 0
                            THEN ABS(measured_input_tokens - COALESCE(estimated_optimized_tokens, optimized_tokens)) * 1.0
                                / COALESCE(estimated_optimized_tokens, optimized_tokens)
                            ELSE NULL
                        END
                    ) as max_token_error_rate
                FROM usage_records
                {where}
                """
            ).fetchone()
            attachment_metrics = self._attachment_metrics(db, where)
            followup_requests = self._count_followups(db, where)
            long_context_savings_rate = self._long_context_savings_rate(db, where)
            hotkey_metrics = self._hotkey_metrics(db, where)
            short_prompt_protected_count = self._short_prompt_protected_count(db, where)
            used_assumed_requests = self._used_assumed_requests(db, where)

        total_original = int(row["original_tokens"] or 0)
        saved = int(row["saved_tokens"] or 0)
        total_requests = int(row["total_requests"] or 0)
        measured_requests = int(row["measured_requests"] or 0)
        return {
            "period": period,
            "total_requests": total_requests,
            "approved_requests": int(row["approved_requests"] or 0),
            "rejected_requests": int(row["rejected_requests"] or 0),
            "original_tokens": total_original,
            "optimized_tokens": int(row["optimized_tokens"] or 0),
            "saved_tokens": saved,
            "original_cost_usd": round(float(row["original_cost_usd"] or 0), 8),
            "optimized_cost_usd": round(float(row["optimized_cost_usd"] or 0), 8),
            "saved_cost_usd": round(float(row["saved_cost_usd"] or 0), 8),
            "savings_rate": round(saved / total_original, 4) if total_original else 0,
            "measured_requests": measured_requests,
            "measurement_coverage": round(measured_requests / total_requests, 4)
            if total_requests
            else 0,
            "avg_token_error_rate": round(float(row["avg_token_error_rate"] or 0), 4),
            "max_token_error_rate": round(float(row["max_token_error_rate"] or 0), 4),
            "followup_requests": followup_requests,
            "reask_rate": round(followup_requests / total_requests, 4) if total_requests else 0,
            "long_context_savings_rate": long_context_savings_rate,
            "short_prompt_protected_count": short_prompt_protected_count,
            "hotkey_attempts": hotkey_metrics["attempts"],
            "hotkey_failed_requests": hotkey_metrics["failed_requests"],
            "hotkey_success_rate": hotkey_metrics["success_rate"],
            "hotkey_validation_status": hotkey_metrics["validation_status"],
            "latest_hotkey_status": hotkey_metrics["latest_status"],
            "hotkey_discovered_attachments": hotkey_metrics["discovered_attachments"],
            "hotkey_content_available_attachments": hotkey_metrics["content_available_attachments"],
            "hotkey_unknown_attachments": hotkey_metrics["unknown_attachments"],
            "hotkey_unsupported_attachments": hotkey_metrics["unsupported_attachments"],
            "used_assumed_requests": used_assumed_requests,
            "backend_health_status": "ok",
            "attachment_requests": attachment_metrics["attachment_requests"],
            "attachment_unknown_requests": attachment_metrics["attachment_unknown_requests"],
            "attachment_measured_requests": attachment_metrics["attachment_measured_requests"],
            "attachment_measured_coverage": attachment_metrics["attachment_measured_coverage"],
            "attachment_original_tokens": attachment_metrics["attachment_original_tokens"],
            "attachment_optimized_tokens": attachment_metrics["attachment_optimized_tokens"],
            "attachment_saved_tokens": attachment_metrics["attachment_saved_tokens"],
            "attachment_savings_rate": attachment_metrics["attachment_savings_rate"],
        }

    def category_summary(self, period: str = "month") -> list[dict[str, object]]:
        where = _period_clause(period)
        with self.connect() as db:
            rows = db.execute(
                f"""
                SELECT
                    task_type,
                    COUNT(*) as total_requests,
                    SUM(saved_tokens) as saved_tokens,
                    SUM(original_tokens) as original_tokens,
                    SUM(CASE WHEN state = 'measured' THEN 1 ELSE 0 END) as measured_requests,
                    AVG(
                        CASE
                            WHEN measured_input_tokens IS NOT NULL
                            AND COALESCE(estimated_optimized_tokens, optimized_tokens) > 0
                            THEN ABS(measured_input_tokens - COALESCE(estimated_optimized_tokens, optimized_tokens)) * 1.0
                                / COALESCE(estimated_optimized_tokens, optimized_tokens)
                            ELSE NULL
                        END
                    ) as avg_token_error_rate
                FROM usage_records
                {where}
                GROUP BY task_type
                ORDER BY total_requests DESC, task_type ASC
                """
            ).fetchall()
        summaries: list[dict[str, object]] = []
        for row in rows:
            original_tokens = int(row["original_tokens"] or 0)
            saved_tokens = int(row["saved_tokens"] or 0)
            summaries.append(
                {
                    "category": row["task_type"],
                    "total_requests": int(row["total_requests"] or 0),
                    "saved_tokens": saved_tokens,
                    "savings_rate": round(saved_tokens / original_tokens, 4) if original_tokens else 0,
                    "measured_requests": int(row["measured_requests"] or 0),
                    "avg_token_error_rate": round(float(row["avg_token_error_rate"] or 0), 4),
                }
            )
        return summaries

    def _count_followups(self, db: sqlite3.Connection, where: str) -> int:
        rows = db.execute(
            f"""
            SELECT created_at, provider, model, task_type, request_family_hash
            FROM usage_records
            {where}
            ORDER BY created_at ASC
            """
        ).fetchall()
        seen: dict[tuple[str, str, str, str], datetime] = {}
        followups = 0
        window = timedelta(minutes=30)
        for row in rows:
            family = row["request_family_hash"] or ""
            if not family:
                continue
            key = (row["provider"], row["model"], row["task_type"], family)
            created_at = _parse_datetime(str(row["created_at"]))
            previous = seen.get(key)
            if previous is not None and created_at - previous <= window:
                followups += 1
            seen[key] = created_at
        return followups

    def _long_context_savings_rate(self, db: sqlite3.Connection, where: str) -> float:
        row = db.execute(
            f"""
            SELECT SUM(saved_tokens) as saved_tokens, SUM(original_tokens) as original_tokens
            FROM usage_records
            {where}
            {'AND' if where else 'WHERE'} (
                applied_rules LIKE '%compression%'
                OR applied_rules LIKE '%compaction%'
                OR applied_rules LIKE '%command_output%'
                OR applied_rules LIKE '%diff%'
                OR applied_rules LIKE '%log_%'
                OR original_tokens >= 500
            )
            """
        ).fetchone()
        original_tokens = int(row["original_tokens"] or 0)
        saved_tokens = int(row["saved_tokens"] or 0)
        return round(saved_tokens / original_tokens, 4) if original_tokens else 0

    def _hotkey_metrics(self, db: sqlite3.Connection, where: str) -> dict[str, float | int | str]:
        event_rows = db.execute(
            """
            SELECT
                status,
                failure_reason,
                discovered_attachment_count,
                content_available_attachment_count,
                unknown_attachment_count,
                unsupported_attachment_count
            FROM hotkey_events
            ORDER BY created_at DESC, rowid DESC
            LIMIT 30
            """
        ).fetchall()
        if event_rows:
            total_requests = len(event_rows)
            failed_requests = sum(1 for row in event_rows if _is_failed_hotkey_status(str(row["status"])))
            latest_status = str(event_rows[0]["status"])
            discovered_attachments = sum(int(row["discovered_attachment_count"] or 0) for row in event_rows)
            content_available_attachments = sum(
                int(row["content_available_attachment_count"] or 0) for row in event_rows
            )
            unknown_attachments = sum(int(row["unknown_attachment_count"] or 0) for row in event_rows)
            unsupported_attachments = sum(int(row["unsupported_attachment_count"] or 0) for row in event_rows)
        else:
            row = db.execute(
                f"""
                SELECT
                    COUNT(*) as total_requests,
                    SUM(CASE WHEN state = 'failed' OR failure_reason IS NOT NULL THEN 1 ELSE 0 END) as failed_requests
                FROM usage_records
                {where}
                {'AND' if where else 'WHERE'} capture_source = 'hotkey'
                """
            ).fetchone()
            total_requests = int(row["total_requests"] or 0)
            failed_requests = int(row["failed_requests"] or 0)
            latest_status = None
            discovered_attachments = 0
            content_available_attachments = 0
            unknown_attachments = 0
            unsupported_attachments = 0
        successful_requests = max(0, total_requests - failed_requests)
        success_rate = round(successful_requests / total_requests, 4) if total_requests else 0
        if total_requests < 30:
            validation_status = "needs_validation"
        elif success_rate >= 0.9 and failed_requests <= 3:
            validation_status = "passed"
        else:
            validation_status = "failed"
        return {
            "attempts": total_requests,
            "failed_requests": failed_requests,
            "success_rate": success_rate,
            "validation_status": validation_status,
            "latest_status": latest_status,
            "discovered_attachments": discovered_attachments,
            "content_available_attachments": content_available_attachments,
            "unknown_attachments": unknown_attachments,
            "unsupported_attachments": unsupported_attachments,
        }

    def _short_prompt_protected_count(self, db: sqlite3.Connection, where: str) -> int:
        row = db.execute(
            f"""
            SELECT COUNT(*) as protected_count
            FROM usage_records
            {where}
            {'AND' if where else 'WHERE'} state = 'rejected'
            AND saved_tokens = 0
            AND (
                original_tokens <= 120
                OR decision_notes IN (
                    'no_savings',
                    'no_savings_short_prompt',
                    'no_savings_structured_prompt',
                    'no_savings_quality_guard'
                )
            )
            """
        ).fetchone()
        return int(row["protected_count"] or 0)

    def _used_assumed_requests(self, db: sqlite3.Connection, where: str) -> int:
        row = db.execute(
            f"""
            SELECT COUNT(*) as used_count
            FROM usage_records
            {where}
            {'AND' if where else 'WHERE'} delivery_status IN (
                'pasted_assumed_used',
                'sent_proxy',
                'measured'
            )
            """
        ).fetchone()
        return int(row["used_count"] or 0)

    def _attachment_metrics(self, db: sqlite3.Connection, where: str) -> dict[str, int | float]:
        row = db.execute(
            f"""
            SELECT
                COUNT(DISTINCT usage_records.request_id) as attachment_requests,
                COUNT(DISTINCT CASE
                    WHEN (
                        usage_records.possible_attachment_reference = 1
                        AND request_attachments.request_id IS NULL
                    )
                    OR request_attachments.token_status = 'unknown'
                    THEN usage_records.request_id
                END) as attachment_unknown_requests,
                COUNT(DISTINCT CASE
                    WHEN request_attachments.token_status = 'measured'
                    THEN usage_records.request_id
                END) as attachment_measured_requests,
                SUM(request_attachments.original_tokens) as attachment_original_tokens,
                SUM(request_attachments.optimized_tokens) as attachment_optimized_tokens,
                SUM(request_attachments.saved_tokens) as attachment_saved_tokens
            FROM usage_records
            LEFT JOIN request_attachments ON request_attachments.request_id = usage_records.request_id
            {where}
            {'AND' if where else 'WHERE'} (
                usage_records.possible_attachment_reference = 1
                OR request_attachments.request_id IS NOT NULL
            )
            """
        ).fetchone()
        attachment_requests = int(row["attachment_requests"] or 0)
        measured_requests = int(row["attachment_measured_requests"] or 0)
        attachment_original_tokens = int(row["attachment_original_tokens"] or 0)
        attachment_saved_tokens = int(row["attachment_saved_tokens"] or 0)
        return {
            "attachment_requests": attachment_requests,
            "attachment_unknown_requests": int(row["attachment_unknown_requests"] or 0),
            "attachment_measured_requests": measured_requests,
            "attachment_measured_coverage": round(measured_requests / attachment_requests, 4)
            if attachment_requests
            else 0,
            "attachment_original_tokens": attachment_original_tokens,
            "attachment_optimized_tokens": int(row["attachment_optimized_tokens"] or 0),
            "attachment_saved_tokens": attachment_saved_tokens,
            "attachment_savings_rate": round(attachment_saved_tokens / attachment_original_tokens, 4)
            if attachment_original_tokens
            else 0,
        }

    def _replace_attachments(
        self,
        db: sqlite3.Connection,
        request_id: str,
        attachments: list[AttachmentMetadata],
    ) -> None:
        db.execute("DELETE FROM request_attachments WHERE request_id = ?", (request_id,))
        for item in attachments:
            db.execute(
                """
                INSERT INTO request_attachments (
                    attachment_id, request_id, name, mime_type, size_bytes, content_hash,
                    token_status, estimated_tokens, measured_tokens, original_tokens,
                    optimized_tokens, saved_tokens, savings_rate, measurement_source,
                    discovery_source, content_available, path_available, read_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    request_id,
                    item.name,
                    item.mime_type,
                    item.size_bytes,
                    item.content_hash,
                    item.token_status.value,
                    item.estimated_tokens,
                    item.measured_tokens,
                    item.original_tokens,
                    item.optimized_tokens,
                    item.saved_tokens,
                    item.savings_rate,
                    item.measurement_source,
                    item.discovery_source.value,
                    1 if item.content_available else 0,
                    1 if item.path_available else 0,
                    item.read_error,
                ),
            )


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _family_hash(provider: str, model: str, task_type: str, text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"```.*?```", " code_block ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"\b[0-9a-f]{8,}\b", "<hash>", normalized)
    normalized = re.sub(r"\d+", "<n>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    fingerprint = " ".join(normalized.split()[:80])
    return _hash_text(f"{provider}|{model}|{task_type}|{fingerprint}")


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _rejection_reason(
    state: str,
    notes: str | None,
    saved_tokens: int,
    original_tokens: int = 0,
    optimized_tokens: int = 0,
) -> str | None:
    if state != UsageState.REJECTED.value:
        return None
    if notes:
        return notes
    if saved_tokens <= 0:
        if original_tokens <= 120:
            return "no_savings_short_prompt"
    if optimized_tokens >= original_tokens:
        return "no_savings_quality_guard"
    return "no_savings"


def _attachment_status(
    attachment_count: int,
    possible_reference: bool,
    unknown_count: int,
    measured_count: int,
) -> str:
    if attachment_count == 0:
        return AttachmentTokenStatus.UNKNOWN.value if possible_reference else AttachmentTokenStatus.NOT_PRESENT.value
    if unknown_count > 0:
        return AttachmentTokenStatus.UNKNOWN.value
    if measured_count == attachment_count:
        return AttachmentTokenStatus.MEASURED.value
    return AttachmentTokenStatus.ESTIMATED.value


def _total_savings_rate(
    measured_original: int,
    measured_optimized: int,
    measured_total_input: int | None,
) -> float | None:
    if measured_total_input is None:
        return None
    attachment_tokens = max(0, measured_total_input - measured_optimized)
    total_original = measured_original + attachment_tokens
    total_optimized = measured_optimized + attachment_tokens
    if total_original <= 0:
        return 0
    return round(max(0, total_original - total_optimized) / total_original, 4)


def _delivery_status_for_state(state: UsageState) -> str:
    if state == UsageState.SENT:
        return DeliveryStatus.COPIED.value
    if state == UsageState.MEASURED:
        return DeliveryStatus.MEASURED.value
    if state == UsageState.REJECTED:
        return DeliveryStatus.NOT_USED.value
    if state == UsageState.FAILED:
        return DeliveryStatus.FAILED.value
    return DeliveryStatus.PREVIEWED.value


def _delivery_status_for_hotkey_status(status: str) -> str | None:
    if status == "optimized_pasted":
        return DeliveryStatus.PASTED_ASSUMED_USED.value
    if status in {"no_savings_kept_original", "empty_selection"}:
        return DeliveryStatus.NOT_USED.value
    if _is_failed_hotkey_status(status):
        return DeliveryStatus.FAILED.value
    return None


def _usage_state_for_hotkey_status(status: str) -> str | None:
    if status == "optimized_pasted":
        return UsageState.SENT.value
    if status in {"no_savings_kept_original", "empty_selection"}:
        return UsageState.REJECTED.value
    if _is_failed_hotkey_status(status):
        return UsageState.FAILED.value
    return None


def _decision_note_for_hotkey_status(status: str) -> str | None:
    if status == "empty_selection":
        return "empty_selection"
    if status == "no_savings_kept_original":
        return "no_savings"
    return None


def _is_failed_hotkey_status(status: str) -> bool:
    return status in {"backend_failed", "clipboard_failed", "paste_failed", "failed"}


def _token_error_rate(estimated: int, measured: int) -> float:
    return round(abs(measured - estimated) / estimated, 4) if estimated else 0


def _success_rate(attempts: int, successes: int) -> float:
    return round(successes / attempts, 4) if attempts else 0


def _compatibility_status(attempts: int, success_rate: float, prompt_loss_count: int) -> str:
    if attempts <= 0:
        return "pending_real_test"
    if prompt_loss_count > 0:
        return "failed"
    if attempts >= COMPATIBILITY_REQUIRED_ATTEMPTS and success_rate >= 0.98:
        return "verified"
    if success_rate >= 0.9:
        return "limited"
    return "failed"


def _json_list(value: object) -> list[str]:
    if not value:
        return []
    try:
        loaded = json.loads(str(value))
    except json.JSONDecodeError:
        return [str(value)]
    if isinstance(loaded, list):
        return [str(item) for item in loaded]
    return [str(loaded)]


def _period_clause(period: str) -> str:
    now = datetime.now(timezone.utc)
    if period == "day":
        return f"WHERE created_at >= '{now.date().isoformat()}T00:00:00+00:00'"
    if period == "week":
        return "WHERE created_at >= datetime('now', '-7 days')"
    if period == "month":
        return "WHERE created_at >= datetime('now', '-31 days')"
    return ""
