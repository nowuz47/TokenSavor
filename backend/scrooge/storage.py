from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import sqlite3
from pathlib import Path

from scrooge.config import Settings
from scrooge.schemas import OptimizeResponse, UsageState


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
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_db(self) -> None:
        with self.connect() as db:
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
                    measured_input_tokens INTEGER,
                    measured_output_tokens INTEGER
                )
                """
            )

    def save_preview(self, response: OptimizeResponse, provider: str, model: str) -> None:
        original_prompt = response.original_prompt if self.settings.store_prompt_bodies else None
        optimized_prompt = response.optimized_prompt if self.settings.store_prompt_bodies else None
        with self.connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO usage_records (
                    request_id, created_at, provider, model, task_type, state,
                    original_hash, optimized_hash, original_prompt, optimized_prompt,
                    original_tokens, optimized_tokens, saved_tokens,
                    original_cost_usd, optimized_cost_usd, saved_cost_usd,
                    tokenizer_version, pricing_version, pricing_source_url, applied_rules
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    response.saved_tokens,
                    response.original_cost.total_cost_usd,
                    response.optimized_cost.total_cost_usd,
                    response.saved_cost_usd,
                    response.optimized_tokens.tokenizer,
                    response.optimized_cost.pricing_version,
                    response.optimized_cost.source_url,
                    ",".join(reason.rule_id for reason in response.reasons),
                ),
            )

    def mark_state(self, request_id: str, state: UsageState) -> None:
        with self.connect() as db:
            db.execute("UPDATE usage_records SET state = ? WHERE request_id = ?", (state.value, request_id))

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
                    SUM(CASE WHEN state = 'measured' THEN 1 ELSE 0 END) as measured_requests
                FROM usage_records
                {where}
                """
            ).fetchone()

        total_original = int(row["original_tokens"] or 0)
        saved = int(row["saved_tokens"] or 0)
        return {
            "period": period,
            "total_requests": int(row["total_requests"] or 0),
            "approved_requests": int(row["approved_requests"] or 0),
            "rejected_requests": int(row["rejected_requests"] or 0),
            "original_tokens": total_original,
            "optimized_tokens": int(row["optimized_tokens"] or 0),
            "saved_tokens": saved,
            "original_cost_usd": round(float(row["original_cost_usd"] or 0), 8),
            "optimized_cost_usd": round(float(row["optimized_cost_usd"] or 0), 8),
            "saved_cost_usd": round(float(row["saved_cost_usd"] or 0), 8),
            "savings_rate": round(saved / total_original, 4) if total_original else 0,
            "measured_requests": int(row["measured_requests"] or 0),
        }


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _period_clause(period: str) -> str:
    now = datetime.now(timezone.utc)
    if period == "day":
        return f"WHERE created_at >= '{now.date().isoformat()}T00:00:00+00:00'"
    if period == "week":
        return "WHERE created_at >= datetime('now', '-7 days')"
    if period == "month":
        return "WHERE created_at >= datetime('now', '-31 days')"
    return ""

