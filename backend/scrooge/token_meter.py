import math
import re

from scrooge.schemas import TokenBreakdown

TOKENIZER_VERSION = "heuristic-v1"
WORD_RE = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", re.UNICODE)


def estimate_tokens(text: str, provider: str = "", model: str = "") -> TokenBreakdown:
    """Provider-neutral fallback estimator for preview and offline cost planning."""
    if provider.lower() == "openai":
        counted = _try_tiktoken_count(text, model)
        if counted is not None:
            return TokenBreakdown(
                input_tokens=counted,
                tokenizer=f"tiktoken:{model or 'default'}",
                is_estimate=True,
            )

    if not text:
        return TokenBreakdown(input_tokens=0, tokenizer=TOKENIZER_VERSION)

    lexical_units = len(WORD_RE.findall(text))
    char_estimate = math.ceil(len(text) / 4)
    # Korean and stack traces are often undercounted by naive char/4, so keep the max.
    tokens = max(lexical_units, char_estimate)
    return TokenBreakdown(
        input_tokens=tokens,
        tokenizer=_fallback_tokenizer_version(provider, model),
        is_estimate=True,
    )


def _try_tiktoken_count(text: str, model: str) -> int | None:
    try:
        import tiktoken  # type: ignore[import-not-found]
    except Exception:
        return None

    try:
        encoding = tiktoken.encoding_for_model(model)
    except Exception:
        try:
            encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            return None
    return len(encoding.encode(text))


def _fallback_tokenizer_version(provider: str, model: str) -> str:
    if not provider:
        return TOKENIZER_VERSION
    model_label = model or "default"
    return f"{provider.lower()}:{model_label}:{TOKENIZER_VERSION}"
