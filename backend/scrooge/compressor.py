from collections import Counter
from dataclasses import dataclass
import re


ERROR_RE = re.compile(r"(error|exception|failed|fatal|traceback|panic)", re.IGNORECASE)
STACK_FRAME_RE = re.compile(r"^\s*(at\s+|File\s+\"|#\d+\s+|Caused by:)")
DIFF_HEADER_RE = re.compile(r"^(diff --git|@@|\+\+\+|---)")
COMMAND_RE = re.compile(
    r"^\s*(?:\$|>)?\s*(git|pytest|python -m pytest|npm|pnpm|yarn|cargo|go test|rg|grep|docker|kubectl|tsc|vite|eslint)\b",
    re.IGNORECASE,
)
JS_BUILD_SIGNAL_RE = re.compile(
    r"(TS\d{4}|ESLint|error\s+During build|vite v|npm ERR!|pnpm ERR!|yarn error|"
    r"Module not found|Cannot find module|Failed to compile|Parsing error)",
    re.IGNORECASE,
)
CONTAINER_LOG_SIGNAL_RE = re.compile(
    r"(kubectl|docker compose|CrashLoopBackOff|Back-off|OOMKilled|ImagePullBackOff|pod/|container=|namespace=)",
    re.IGNORECASE,
)
TEST_SIGNAL_RE = re.compile(
    r"(FAILED|ERROR|FAILURES|short test summary|collected \d+ items|AssertionError|E\s+assert|"
    r"\d+\s+failed|\d+\s+passed)",
    re.IGNORECASE,
)
TEST_STRONG_SIGNAL_RE = re.compile(
    r"(FAILED\s+[\w./\\:-]+|FAILURES|short test summary|collected \d+ items|AssertionError|"
    r"E\s+assert|\d+\s+failed|\d+\s+passed)",
    re.IGNORECASE,
)
FILE_REF_RE = re.compile(r"([A-Za-z]:)?[/\\\w.-]+\.(py|ts|tsx|js|jsx|rs|go|java|kt|cpp|c|h):\d+")
GIT_STATUS_RE = re.compile(r"^(On branch|Changes not staged|Changes to be committed|Untracked files:|modified:|new file:|deleted:|\?\?)")
SEARCH_MATCH_RE = re.compile(r"^(.+?):(\d+):(.+)$")
PROTECTED_START_RE = re.compile(r"^\s*(?:<scrooge-keep>|<!--\s*scrooge-keep:start\s*-->|SCROOGE_KEEP_START)\s*$", re.IGNORECASE)
PROTECTED_END_RE = re.compile(r"^\s*(?:</scrooge-keep>|<!--\s*scrooge-keep:end\s*-->|SCROOGE_KEEP_END)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class CompressionResult:
    text: str
    rules: list[str]


def compress_context(text: str, max_lines: int = 80) -> CompressionResult:
    lines = [line.rstrip() for line in text.splitlines()]
    preserved_blocks, compressible_lines = _extract_protected_blocks(lines)
    protected_rules = ["protected_block_preservation"] if preserved_blocks else []

    routed = _compress_routed_context(compressible_lines, max_lines)
    if routed is not None:
        return _attach_protected_blocks(routed, preserved_blocks, protected_rules)

    if len(lines) <= max_lines:
        if preserved_blocks:
            return CompressionResult(text=text.strip(), rules=protected_rules)
        return CompressionResult(text=text.strip(), rules=[])

    if preserved_blocks:
        if len(compressible_lines) <= max_lines:
            return _attach_protected_blocks(
                CompressionResult(text="\n".join(compressible_lines).strip(), rules=[]),
                preserved_blocks,
                protected_rules,
            )
        lines = compressible_lines

    head = lines[: max_lines // 2]
    tail = lines[-(max_lines // 2) :]
    omitted = len(lines) - len(head) - len(tail)
    result = CompressionResult(
        text="\n".join(head + [f"... omitted {omitted} middle lines ..."] + tail),
        rules=["generic_head_tail_compaction"],
    )
    return _attach_protected_blocks(result, preserved_blocks, protected_rules)


def _compress_routed_context(lines: list[str], max_lines: int) -> CompressionResult | None:
    if _looks_like_js_build_output(lines):
        return _compress_js_build_output(lines, max_lines)
    if _looks_like_search_output(lines):
        return _compress_search_output(lines, max_lines)
    if _looks_like_container_output(lines):
        return _compress_container_output(lines, max_lines)
    if _looks_like_test_output(lines):
        return _compress_test_output(lines, max_lines)
    if _looks_like_git_status(lines):
        return _compress_git_status(lines, max_lines)
    if _looks_like_diff(lines):
        return _compress_diff(lines, max_lines)
    if _looks_like_stacktrace(lines):
        return _compress_stacktrace(lines, max_lines)
    if _looks_like_log(lines):
        return _compress_log(lines, max_lines)
    return None


def _extract_protected_blocks(lines: list[str]) -> tuple[list[str], list[str]]:
    protected: list[str] = []
    compressible: list[str] = []
    in_protected = False

    for line in lines:
        if PROTECTED_START_RE.match(line):
            in_protected = True
            protected.append(line)
            continue
        if PROTECTED_END_RE.match(line):
            protected.append(line)
            in_protected = False
            continue
        if in_protected:
            protected.append(line)
        else:
            compressible.append(line)
    return protected, compressible


def _attach_protected_blocks(
    result: CompressionResult, protected_blocks: list[str], protected_rules: list[str]
) -> CompressionResult:
    if not protected_blocks:
        return result
    text_parts = [result.text.strip(), "Protected context kept verbatim:", "\n".join(protected_blocks).strip()]
    return CompressionResult(
        text="\n\n".join(part for part in text_parts if part),
        rules=result.rules + protected_rules,
    )


def _looks_like_log(lines: list[str]) -> bool:
    matches = sum(1 for line in lines if ERROR_RE.search(line))
    return matches >= 3


def _looks_like_stacktrace(lines: list[str]) -> bool:
    return sum(1 for line in lines if STACK_FRAME_RE.search(line)) >= 5


def _looks_like_diff(lines: list[str]) -> bool:
    return sum(1 for line in lines if DIFF_HEADER_RE.search(line)) >= 3


def _looks_like_test_output(lines: list[str]) -> bool:
    command_matches = sum(1 for line in lines[:12] if COMMAND_RE.search(line) and "test" in line.lower())
    strong_signal_matches = sum(1 for line in lines if TEST_STRONG_SIGNAL_RE.search(line))
    return strong_signal_matches >= 2 or (command_matches >= 1 and strong_signal_matches >= 1)


def _looks_like_js_build_output(lines: list[str]) -> bool:
    command_hint = any(
        COMMAND_RE.search(line)
        and re.search(r"\b(npm|pnpm|yarn|tsc|vite|eslint)\b", line, re.IGNORECASE)
        for line in lines[:12]
    )
    js_signals = sum(1 for line in lines if JS_BUILD_SIGNAL_RE.search(line))
    js_file_refs = sum(1 for line in lines if re.search(r"\.(ts|tsx|js|jsx):\d+", line))
    return js_signals >= 2 or (command_hint and (js_signals >= 1 or js_file_refs >= 1))


def _looks_like_container_output(lines: list[str]) -> bool:
    command_hint = any(
        COMMAND_RE.search(line) and re.search(r"\b(docker|kubectl)\b", line, re.IGNORECASE)
        for line in lines[:12]
    )
    container_signals = sum(1 for line in lines if CONTAINER_LOG_SIGNAL_RE.search(line))
    error_signals = sum(1 for line in lines if ERROR_RE.search(line))
    return container_signals >= 2 or (command_hint and error_signals >= 2)


def _looks_like_git_status(lines: list[str]) -> bool:
    return any("git status" in line.lower() for line in lines[:8]) or sum(
        1 for line in lines if GIT_STATUS_RE.search(line.strip())
    ) >= 3


def _looks_like_search_output(lines: list[str]) -> bool:
    command_hint = any(COMMAND_RE.search(line) and re.search(r"\b(rg|grep)\b", line, re.IGNORECASE) for line in lines[:8])
    matches = sum(1 for line in lines if SEARCH_MATCH_RE.match(line))
    return matches >= 8 or (command_hint and matches >= 3)


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


def _compress_test_output(lines: list[str], max_lines: int) -> CompressionResult:
    command_lines = [line for line in lines[:12] if COMMAND_RE.search(line)]
    failure_lines = [
        line
        for line in lines
        if TEST_SIGNAL_RE.search(line) or FILE_REF_RE.search(line) or line.strip().startswith(("E   ", "E   assert"))
    ]
    normalized = [re.sub(r"\d+", "<n>", line.strip()) for line in failure_lines if line.strip()]
    counts = Counter(normalized)
    summary = [
        "Command output summary:",
        "- Type: test-runner",
        f"- Total lines: {len(lines)}",
        f"- Failure/signal lines: {len(failure_lines)}",
    ]
    if command_lines:
        summary.append(f"- Command: {command_lines[0].strip()}")
    summary.extend(f"- {count}x {sample}" for sample, count in counts.most_common(8))

    budget = max(6, max_lines - len(summary) - 3)
    samples = ["Representative test signals:"] + failure_lines[:budget]
    return CompressionResult(
        text="\n".join(summary + [""] + samples),
        rules=["command_output_test_summary", "command_output_failure_preservation"],
    )


def _compress_js_build_output(lines: list[str], max_lines: int) -> CompressionResult:
    command_lines = [line for line in lines[:12] if COMMAND_RE.search(line)]
    signal_lines = [
        line
        for line in lines
        if JS_BUILD_SIGNAL_RE.search(line) or FILE_REF_RE.search(line) or re.search(r"\.(ts|tsx|js|jsx):\d+", line)
    ]
    normalized = [re.sub(r"\d+", "<n>", line.strip()) for line in signal_lines if line.strip()]
    counts = Counter(normalized)
    summary = [
        "Command output summary:",
        "- Type: js-build-or-lint",
        f"- Total lines: {len(lines)}",
        f"- Build/lint signal lines: {len(signal_lines)}",
    ]
    if command_lines:
        summary.append(f"- Command: {command_lines[0].strip()}")
    summary.extend(f"- {count}x {sample}" for sample, count in counts.most_common(8))
    budget = max(6, max_lines - len(summary) - 3)
    samples = ["Representative build/lint signals:"] + signal_lines[:budget]
    return CompressionResult(
        text="\n".join(summary + [""] + samples),
        rules=["command_output_js_build_summary", "command_output_lint_failure_preservation"],
    )


def _compress_container_output(lines: list[str], max_lines: int) -> CompressionResult:
    command_lines = [line for line in lines[:12] if COMMAND_RE.search(line)]
    signal_lines = [line for line in lines if CONTAINER_LOG_SIGNAL_RE.search(line) or ERROR_RE.search(line)]
    normalized = [re.sub(r"\d+", "<n>", line.strip()) for line in signal_lines if line.strip()]
    counts = Counter(normalized)
    summary = [
        "Command output summary:",
        "- Type: container-or-kubernetes",
        f"- Total lines: {len(lines)}",
        f"- Container/log signal lines: {len(signal_lines)}",
    ]
    if command_lines:
        summary.append(f"- Command: {command_lines[0].strip()}")
    summary.extend(f"- {count}x {sample}" for sample, count in counts.most_common(10))
    budget = max(6, max_lines - len(summary) - 3)
    samples = ["Representative container signals:"] + signal_lines[:budget]
    return CompressionResult(
        text="\n".join(summary + [""] + samples),
        rules=["command_output_container_log_summary", "command_output_container_signal_preservation"],
    )


def _compress_git_status(lines: list[str], max_lines: int) -> CompressionResult:
    branch = next((line.strip() for line in lines if line.strip().startswith("On branch")), "On branch: unknown")
    file_lines = [
        line.strip()
        for line in lines
        if line.strip().startswith(("modified:", "new file:", "deleted:", "renamed:", "both modified:", "??"))
    ]
    counts = Counter(line.split(":", 1)[0].replace("??", "untracked") for line in file_lines)
    summary = [
        "Command output summary:",
        "- Type: git-status",
        f"- {branch}",
        f"- Changed files: {len(file_lines)}",
    ]
    summary.extend(f"- {kind.strip()}: {count}" for kind, count in counts.items())
    budget = max(5, max_lines - len(summary) - 2)
    samples = ["Changed file samples:"] + file_lines[:budget]
    return CompressionResult(
        text="\n".join(summary + [""] + samples),
        rules=["command_output_git_status_summary", "command_output_changed_file_sampling"],
    )


def _compress_search_output(lines: list[str], max_lines: int) -> CompressionResult:
    matches = [match for line in lines if (match := SEARCH_MATCH_RE.match(line))]
    file_counts = Counter(match.group(1) for match in matches)
    summary = [
        "Command output summary:",
        "- Type: search-results",
        f"- Total matches: {len(matches)}",
        f"- Matched files: {len(file_counts)}",
    ]
    summary.extend(f"- {count}x {path}" for path, count in file_counts.most_common(10))
    budget = max(5, max_lines - len(summary) - 2)
    samples = ["Representative matches:"] + [match.group(0) for match in matches[:budget]]
    return CompressionResult(
        text="\n".join(summary + [""] + samples),
        rules=["command_output_search_summary", "command_output_match_sampling"],
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
