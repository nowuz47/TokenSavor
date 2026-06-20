from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SecurityFindingData:
    kind: str
    label: str
    severity: str
    start: int
    end: int
    preview: str


PATTERNS: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    (
        "api_key",
        "API key or secret token",
        "high",
        re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|xox[baprs]-[A-Za-z0-9-]{12,}|AKIA[0-9A-Z]{16})\b"),
    ),
    (
        "password",
        "Password assignment",
        "high",
        re.compile(r"(?i)\b(password|passwd|pwd|secret)\s*[:=]\s*['\"]?[^'\"\s]{6,}"),
    ),
    (
        "bearer_token",
        "Bearer token",
        "high",
        re.compile(r"(?i)\bauthorization\s*[:=]\s*bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    ),
    (
        "email",
        "Email address",
        "medium",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        "phone",
        "Phone number",
        "medium",
        re.compile(r"\b(?:\+82[-\s]?)?0?1[016789][-\s]?\d{3,4}[-\s]?\d{4}\b"),
    ),
    (
        "korean_rrn",
        "Korean resident registration number",
        "high",
        re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b"),
    ),
    (
        "internal_url",
        "Internal URL or host",
        "medium",
        re.compile(r"\bhttps?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[0-1])\.\d+\.\d+|192\.168\.\d+\.\d+|[A-Za-z0-9.-]+\.internal)[^\s]*"),
    ),
)


def scan_prompt_security(prompt: str) -> tuple[list[SecurityFindingData], str]:
    findings: list[SecurityFindingData] = []
    redactions: list[tuple[int, int, str]] = []
    for kind, label, severity, pattern in PATTERNS:
        for match in pattern.finditer(prompt):
            preview = _preview(match.group(0))
            findings.append(
                SecurityFindingData(
                    kind=kind,
                    label=label,
                    severity=severity,
                    start=match.start(),
                    end=match.end(),
                    preview=preview,
                )
            )
            redactions.append((match.start(), match.end(), f"[REDACTED:{kind}]"))
    return findings, _apply_redactions(prompt, redactions)


def _preview(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}...{value[-3:]}"


def _apply_redactions(text: str, redactions: list[tuple[int, int, str]]) -> str:
    if not redactions:
        return text
    output: list[str] = []
    cursor = 0
    for start, end, replacement in sorted(redactions, key=lambda item: item[0]):
        if start < cursor:
            continue
        output.append(text[cursor:start])
        output.append(replacement)
        cursor = end
    output.append(text[cursor:])
    return "".join(output)
