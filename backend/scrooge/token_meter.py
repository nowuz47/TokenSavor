import math
import re

from scrooge.schemas import TokenBreakdown

TOKENIZER_VERSION = "heuristic-v1"
WORD_RE = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", re.UNICODE)


def estimate_tokens(text: str) -> TokenBreakdown:
    """Provider-neutral fallback estimator for preview and offline cost planning."""
    if not text:
        return TokenBreakdown(input_tokens=0, tokenizer=TOKENIZER_VERSION)

    lexical_units = len(WORD_RE.findall(text))
    char_estimate = math.ceil(len(text) / 4)
    # Korean and stack traces are often undercounted by naive char/4, so keep the max.
    tokens = max(lexical_units, char_estimate)
    return TokenBreakdown(input_tokens=tokens, tokenizer=TOKENIZER_VERSION, is_estimate=True)

