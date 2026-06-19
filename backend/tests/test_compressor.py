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

