from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3
from pathlib import Path
import re

from scrooge.config import Settings
from scrooge.pricing import calculate_cost
from scrooge.schemas import MeasurementRequest, OptimizeResponse, TokenBreakdown, UsageState


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
                upstream_status INTEGER
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
        db.execute(
            """
            UPDATE usage_records
            SET
                estimated_original_tokens = COALESCE(estimated_original_tokens, original_tokens),
                estimated_optimized_tokens = COALESCE(estimated_optimized_tokens, optimized_tokens),
                request_family_hash = COALESCE(request_family_hash, original_hash)
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

    def save_preview(self, response: OptimizeResponse, provider: str, model: str) -> None:
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
                    request_family_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )

    def mark_state(
        self,
        request_id: str,
        state: UsageState,
        notes: str | None = None,
        upstream_status: int | None = None,
    ) -> None:
        with self.connect() as db:
            cursor = db.execute(
                """
                UPDATE usage_records
                SET
                    state = ?,
                    decision_notes = COALESCE(?, decision_notes),
                    upstream_status = COALESCE(?, upstream_status)
                WHERE request_id = ?
                """,
                (state.value, notes, upstream_status, request_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(request_id)

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
            saved_tokens = max(0, measured_original - measured_optimized)
            original_cost = calculate_cost(
                TokenBreakdown(input_tokens=measured_original, tokenizer="provider-measured", is_estimate=False),
                row["provider"],
                row["model"],
                measured_output,
            )
            optimized_cost = calculate_cost(
                TokenBreakdown(input_tokens=measured_optimized, tokenizer="provider-measured", is_estimate=False),
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
                    pricing_version = ?,
                    pricing_source_url = ?
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
                    optimized_cost.pricing_version,
                    optimized_cost.source_url,
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
                    provider_usage_source, upstream_status
                FROM usage_records
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        records: list[dict[str, object]] = []
        for row in rows:
            original_tokens = int(row["original_tokens"] or 0)
            saved_tokens = int(row["saved_tokens"] or 0)
            estimated_optimized = int(row["estimated_optimized_tokens"] or row["optimized_tokens"] or 0)
            measured_input = row["measured_input_tokens"]
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
                    ),
                    "provider_usage_source": row["provider_usage_source"],
                    "upstream_status": row["upstream_status"],
                    "token_error_rate": (
                        _token_error_rate(estimated_optimized, int(measured_input))
                        if measured_input is not None
                        else None
                    ),
                }
            )
        return records

    def clear_records(self) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM usage_records")

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
            followup_requests = self._count_followups(db, where)

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
        }

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


def _rejection_reason(state: str, notes: str | None, saved_tokens: int) -> str | None:
    if state != UsageState.REJECTED.value:
        return None
    if notes:
        return notes
    if saved_tokens <= 0:
        return "no_savings"
    return "user_kept_original"


def _token_error_rate(estimated: int, measured: int) -> float:
    return round(abs(measured - estimated) / estimated, 4) if estimated else 0


def _period_clause(period: str) -> str:
    now = datetime.now(timezone.utc)
    if period == "day":
        return f"WHERE created_at >= '{now.date().isoformat()}T00:00:00+00:00'"
    if period == "week":
        return "WHERE created_at >= datetime('now', '-7 days')"
    if period == "month":
        return "WHERE created_at >= datetime('now', '-31 days')"
    return ""
