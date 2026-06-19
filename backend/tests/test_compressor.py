from scrooge.compressor import compress_context


def test_log_compression_preserves_error_signal() -> None:
    lines = ["INFO boot"] * 100
    lines += ["ERROR database timeout request_id=123"] * 8
    lines += ["Exception: connection pool exhausted"] * 4

    result = compress_context("\n".join(lines), max_lines=30)

    assert "Error-like lines" in result.text
    assert "database timeout" in result.text
    assert "log_error_frequency_summary" in result.rules


def test_diff_compression_preserves_headers_and_changes() -> None:
    diff = "\n".join(
        [
            "diff --git a/app.py b/app.py",
            "--- a/app.py",
            "+++ b/app.py",
            "@@ -1,3 +1,3 @@",
        ]
        + [f"+added line {i}" for i in range(120)]
    )

    result = compress_context(diff, max_lines=25)

    assert "Git diff summary" in result.text
    assert "diff --git a/app.py b/app.py" in result.text
    assert "diff_header_preservation" in result.rules


def test_test_runner_output_is_summarized_like_cli_proxy() -> None:
    output = "\n".join(
        ["$ pytest", "collected 120 items"]
        + ["tests/test_ok.py ."] * 80
        + [
            "================================== FAILURES ==================================",
            "FAILED tests/test_payment.py::test_refund_rounding - AssertionError: expected 10.00",
            "backend/payments/refund.py:42: AssertionError",
            "E   assert Decimal('9.99') == Decimal('10.00')",
            "=========================== short test summary info ===========================",
            "1 failed, 119 passed in 8.41s",
        ]
    )

    result = compress_context(output, max_lines=24)

    assert "Type: test-runner" in result.text
    assert "tests/test_payment.py::test_refund_rounding" in result.text
    assert "backend/payments/refund.py:42" in result.text
    assert "command_output_test_summary" in result.rules


def test_git_status_output_counts_changed_files() -> None:
    output = "\n".join(
        [
            "$ git status --short",
            "On branch main",
            "Changes not staged for commit:",
        ]
        + [f"modified: backend/scrooge/module_{index}.py" for index in range(30)]
        + [f"?? scratch_{index}.txt" for index in range(20)]
    )

    result = compress_context(output, max_lines=20)

    assert "Type: git-status" in result.text
    assert "Changed files: 50" in result.text
    assert "backend/scrooge/module_0.py" in result.text
    assert "command_output_git_status_summary" in result.rules


def test_search_output_keeps_representative_matches_and_file_counts() -> None:
    output = "\n".join(
        ["$ rg saved_tokens"]
        + [f"backend/scrooge/storage.py:{index}:saved_tokens = max(0, original - optimized)" for index in range(1, 40)]
        + [f"frontend/src/App.tsx:{index}:Saved Tokens" for index in range(40, 70)]
    )

    result = compress_context(output, max_lines=22)

    assert "Type: search-results" in result.text
    assert "Total matches: 69" in result.text
    assert "backend/scrooge/storage.py" in result.text
    assert "command_output_search_summary" in result.rules


def test_protected_blocks_are_kept_verbatim() -> None:
    output = "\n".join(
        ["INFO repeated noise"] * 100
        + [
            "SCROOGE_KEEP_START",
            "Do not remove eval() ban or divide-by-zero requirement.",
            "SCROOGE_KEEP_END",
            "ERROR calculator divide by zero",
        ]
    )

    result = compress_context(output, max_lines=20)

    assert "Do not remove eval() ban or divide-by-zero requirement." in result.text
    assert "SCROOGE_KEEP_START" in result.text
    assert "protected_block_preservation" in result.rules
