from collections import Counter
from dataclasses import dataclass
import re


ERROR_RE = re.compile(r"(error|exception|failed|fatal|traceback|panic)", re.IGNORECASE)
STACK_FRAME_RE = re.compile(r"^\s*(at\s+|File\s+\"|#\d+\s+|Caused by:)")
DIFF_HEADER_RE = re.compile(r"^(diff --git|@@|\+\+\+|---)")


@dataclass(frozen=True)
class CompressionResult:
    text: str
    rules: list[str]


def compress_context(text: str, max_lines: int = 80) -> CompressionResult:
    lines = [line.rstrip() for line in text.splitlines()]
    if len(lines) <= max_lines:
        return CompressionResult(text=text.strip(), rules=[])

    if _looks_like_diff(lines):
        return _compress_diff(lines, max_lines)
    if _looks_like_stacktrace(lines):
        return _compress_stacktrace(lines, max_lines)
    if _looks_like_log(lines):
        return _compress_log(lines, max_lines)

    head = lines[: max_lines // 2]
    tail = lines[-(max_lines // 2) :]
    omitted = len(lines) - len(head) - len(tail)
    return CompressionResult(
        text="\n".join(head + [f"... omitted {omitted} middle lines ..."] + tail),
        rules=["generic_head_tail_compaction"],
    )


def _looks_like_log(lines: list[str]) -> bool:
    matches = sum(1 for line in lines if ERROR_RE.search(line))
    return matches >= 3


def _looks_like_stacktrace(lines: list[str]) -> bool:
    return sum(1 for line in lines if STACK_FRAME_RE.search(line)) >= 5


def _looks_like_diff(lines: list[str]) -> bool:
    return sum(1 for line in lines if DIFF_HEADER_RE.search(line)) >= 3


def _compress_log(lines: list[str], max_lines: int) -> CompressionResult:
    error_lines = [line for line in lines if ERROR_RE.search(line)]
    normalized = [re.sub(r"\d+", "<n>", line) for line in error_lines]
    counts = Counter(normalized)
    summary = ["Log summary:", f"- Total lines: {len(lines)}", f"- Error-like lines: {len(error_lines)}"]
    summary.extend(f"- {count}x {sample}" for sample, count in counts.most_common(10))

    samples = ["Representative samples:"]
    samples.extend(error_lines[: max(5, max_lines - len(summary) - 2)])
    return CompressionResult(
        text="\n".join(summary + [""] + samples),
        rules=["log_error_frequency_summary", "log_representative_samples"],
    )


def _compress_stacktrace(lines: list[str], max_lines: int) -> CompressionResult:
    causes = [line for line in lines if "Caused by:" in line or ERROR_RE.search(line)]
    frames = [line for line in lines if STACK_FRAME_RE.search(line)]
    selected = causes[:10] + frames[: max_lines - 12]
    omitted = max(0, len(lines) - len(selected))
    return CompressionResult(
        text="\n".join(["Stack trace summary:"] + selected + [f"... omitted {omitted} frames ..."]),
        rules=["stacktrace_cause_preservation", "stacktrace_frame_limit"],
    )


def _compress_diff(lines: list[str], max_lines: int) -> CompressionResult:
    headers = [line for line in lines if DIFF_HEADER_RE.search(line)]
    changed = [line for line in lines if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    selected = headers[:30] + changed[: max_lines - 32]
    omitted = max(0, len(lines) - len(selected))
    return CompressionResult(
        text="\n".join(["Git diff summary:"] + selected + [f"... omitted {omitted} diff lines ..."]),
        rules=["diff_header_preservation", "diff_changed_line_sampling"],
    )

