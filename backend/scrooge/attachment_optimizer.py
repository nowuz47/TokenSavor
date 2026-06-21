from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scrooge.compressor import compress_context
from scrooge.schemas import AttachmentDiscoverySource, AttachmentMetadata, AttachmentTokenStatus, OptimizationReason
from scrooge.token_meter import estimate_tokens


TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".log",
    ".md",
    ".txt",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".java",
    ".sql",
}
TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_TYPES = {
    "application/json",
    "application/x-ndjson",
    "application/sql",
    "application/javascript",
    "application/typescript",
}


@dataclass(frozen=True)
class AttachmentOptimization:
    attachments: list[AttachmentMetadata]
    context_text: str
    reasons: list[OptimizationReason]


def optimize_text_attachments(
    attachments: list[AttachmentMetadata],
    provider: str,
    model: str,
) -> AttachmentOptimization:
    processed: list[AttachmentMetadata] = []
    context_blocks: list[str] = []
    reason_ids: set[str] = set()

    for item in attachments:
        if item.content is None:
            processed.append(item)
            continue

        if not _is_supported_text_attachment(item):
            processed.append(
                item.model_copy(
                    update={
                        "content_hash": item.content_hash or _hash_text(item.content),
                        "token_status": AttachmentTokenStatus.UNKNOWN,
                        "measurement_source": None,
                        "content_available": True,
                        "read_error": item.read_error or "unsupported_attachment_type",
                    }
                )
            )
            reason_ids.add("attachment_unsupported_unknown")
            continue

        original_text = item.content.strip()
        original_tokens = estimate_tokens(original_text, provider, model).input_tokens
        optimized_text, rules = _compress_attachment(item.name, item.mime_type, original_text)
        optimized_tokens = estimate_tokens(optimized_text, provider, model).input_tokens

        if optimized_tokens > original_tokens:
            optimized_text = original_text
            optimized_tokens = original_tokens
            rules = ["attachment_short_file_kept"]

        saved_tokens = max(0, original_tokens - optimized_tokens)
        savings_rate = round(saved_tokens / original_tokens, 4) if original_tokens else 0
        reason_ids.update(rules)
        processed.append(
            item.model_copy(
                update={
                    "content_hash": item.content_hash or _hash_text(original_text),
                    "size_bytes": item.size_bytes if item.size_bytes is not None else len(original_text.encode("utf-8")),
                    "mime_type": item.mime_type or mimetypes.guess_type(item.name)[0] or "text/plain",
                    "content": None,
                    "token_status": AttachmentTokenStatus.MEASURED,
                    "estimated_tokens": original_tokens,
                    "measured_tokens": optimized_tokens,
                    "original_tokens": original_tokens,
                    "optimized_tokens": optimized_tokens,
                    "saved_tokens": saved_tokens,
                    "savings_rate": savings_rate,
                    "measurement_source": "measured_controlled",
                    "discovery_source": item.discovery_source
                    if item.discovery_source != AttachmentDiscoverySource.UNKNOWN
                    else AttachmentDiscoverySource.SCROOGE_FILE,
                    "content_available": True,
                }
            )
        )
        context_blocks.append(
            "\n".join(
                [
                    f"Attachment: {item.name}",
                    f"- Original attachment tokens: {original_tokens}",
                    f"- Optimized attachment tokens: {optimized_tokens}",
                    f"- Attachment savings rate: {savings_rate:.1%}",
                    f"- Applied attachment rules: {', '.join(rules)}",
                    "Optimized attachment context:",
                    optimized_text,
                ]
            )
        )

    reasons = [
        OptimizationReason(rule_id=rule_id, description=_describe_attachment_rule(rule_id))
        for rule_id in sorted(reason_ids)
    ]
    context_text = ""
    if context_blocks:
        context_text = "Controlled text attachments optimized by Scrooge:\n\n" + "\n\n".join(context_blocks)
    return AttachmentOptimization(attachments=processed, context_text=context_text, reasons=reasons)


def _is_supported_text_attachment(item: AttachmentMetadata) -> bool:
    suffix = Path(item.name).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True
    mime_type = (item.mime_type or "").lower()
    return mime_type.startswith(TEXT_MIME_PREFIXES) or mime_type in TEXT_MIME_TYPES


def _compress_attachment(name: str, mime_type: str | None, text: str) -> tuple[str, list[str]]:
    suffix = Path(name).suffix.lower()
    lowered_mime = (mime_type or "").lower()
    if suffix == ".csv" or lowered_mime == "text/csv":
        return _compress_csv(text)
    if suffix == ".json" or lowered_mime in {"application/json", "application/x-ndjson"}:
        return _compress_json(text)
    if suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".sql"}:
        return _compress_code(name, text)
    compressed = compress_context(text, max_lines=80)
    return compressed.text, [f"attachment_{rule}" for rule in compressed.rules] or ["attachment_text_context_kept"]


def _compress_csv(text: str) -> tuple[str, list[str]]:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return "", ["attachment_csv_empty"]

    headers = rows[0]
    data_rows = rows[1:]
    numeric_stats: list[str] = []
    for index, header in enumerate(headers[:30]):
        values: list[float] = []
        for row in data_rows:
            if index >= len(row):
                continue
            try:
                values.append(float(row[index].replace(",", "")))
            except ValueError:
                continue
        if values:
            numeric_stats.append(
                f"- {header}: min={min(values):.2f}, max={max(values):.2f}, avg={sum(values) / len(values):.2f}"
            )

    preview_rows = [",".join(headers)]
    preview_rows.extend(",".join(row) for row in data_rows[:8])
    result = [
        "CSV summary:",
        f"- Columns: {', '.join(headers)}",
        f"- Data rows: {len(data_rows)}",
        "- Numeric columns:",
        *(numeric_stats or ["- none detected"]),
        "",
        "Representative rows:",
        *preview_rows,
    ]
    return "\n".join(result), ["attachment_csv_schema_summary", "attachment_csv_numeric_summary"]


def _compress_json(text: str) -> tuple[str, list[str]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        compressed = compress_context(text, max_lines=80)
        return compressed.text, ["attachment_json_parse_fallback", *[f"attachment_{rule}" for rule in compressed.rules]]

    paths = Counter(_iter_json_paths(payload))
    sample = _truncate_json(payload)
    result = [
        "JSON summary:",
        f"- Top-level type: {type(payload).__name__}",
        "- Frequent key paths:",
        *[f"- {path}: {count}" for path, count in paths.most_common(30)],
        "",
        "Representative sample:",
        json.dumps(sample, ensure_ascii=False, indent=2),
    ]
    return "\n".join(result), ["attachment_json_schema_summary", "attachment_json_sample_preservation"]


def _compress_code(name: str, text: str) -> tuple[str, list[str]]:
    lines = text.splitlines()
    signal_re = re.compile(
        r"^\s*(class |def |async def |function |export |import |from |public |private |protected |SELECT |WITH |CREATE |ALTER )",
        re.IGNORECASE,
    )
    risk_re = re.compile(r"(eval\(|exec\(|TODO|FIXME|except|throw|raise|password|secret|token)", re.IGNORECASE)
    selected = [line for line in lines if signal_re.search(line) or risk_re.search(line)]
    if len(lines) <= 120 or not selected:
        compressed = compress_context(text, max_lines=100)
        return compressed.text, ["attachment_code_context_kept", *[f"attachment_{rule}" for rule in compressed.rules]]

    result = [
        f"Code summary for {name}:",
        f"- Total lines: {len(lines)}",
        f"- Signal lines: {len(selected)}",
        "",
        "Imports, declarations, and risk signals:",
        *selected[:100],
    ]
    omitted = max(0, len(selected) - 100)
    if omitted:
        result.append(f"... omitted {omitted} additional signal lines ...")
    return "\n".join(result), ["attachment_code_declaration_summary", "attachment_code_risk_signal_preservation"]


def _iter_json_paths(value: Any, prefix: str = "$") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            paths.append(child_path)
            paths.extend(_iter_json_paths(child, child_path))
        return paths
    if isinstance(value, list):
        paths = [f"{prefix}[]"]
        for child in value[:20]:
            paths.extend(_iter_json_paths(child, f"{prefix}[]"))
        return paths
    return [prefix]


def _truncate_json(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        return "<truncated>"
    if isinstance(value, dict):
        return {key: _truncate_json(child, depth + 1) for key, child in list(value.items())[:12]}
    if isinstance(value, list):
        return [_truncate_json(child, depth + 1) for child in value[:5]]
    return value


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _describe_attachment_rule(rule_id: str) -> str:
    descriptions = {
        "attachment_code_context_kept": "Kept short code attachment content because compression would not save tokens safely.",
        "attachment_code_declaration_summary": "Summarized code around imports, declarations, and callable boundaries.",
        "attachment_code_risk_signal_preservation": "Preserved code risk signals such as eval, exceptions, TODOs, and secrets.",
        "attachment_csv_numeric_summary": "Summarized numeric CSV columns with min, max, and average.",
        "attachment_csv_schema_summary": "Preserved CSV column names, row count, and representative rows.",
        "attachment_json_parse_fallback": "Could not parse JSON reliably, so text-safe compression was used.",
        "attachment_json_sample_preservation": "Kept a representative JSON sample.",
        "attachment_json_schema_summary": "Summarized JSON key paths and structure.",
        "attachment_short_file_kept": "Kept attachment body because compression would not reduce tokens safely.",
        "attachment_text_context_kept": "Kept text attachment context because it was already compact.",
        "attachment_unsupported_unknown": "Attachment type is not supported for local text optimization, so tokens remain unmeasured.",
    }
    if rule_id.startswith("attachment_"):
        return descriptions.get(rule_id, "Applied text attachment compression while preserving key context.")
    return descriptions.get(rule_id, rule_id)
