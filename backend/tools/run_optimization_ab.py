from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrooge.experiments import evaluate_variants  # noqa: E402
from scrooge.quality import GOLDEN_PROMPTS  # noqa: E402
from scrooge.schemas import OptimizeRequest  # noqa: E402


def main() -> int:
    rows = []
    for golden in GOLDEN_PROMPTS:
        variants = evaluate_variants(
            OptimizeRequest(
                prompt=golden.prompt,
                task_type=golden.task_type,
                provider="openai",
                model="gpt-5.4-mini",
            )
        )
        rows.extend(
            {
                "prompt": golden.name,
                "variant": variant.variant,
                "active": variant.active,
                "saved_tokens": variant.saved_tokens,
                "savings_rate": variant.savings_rate,
                "notes": variant.notes,
            }
            for variant in variants
        )

    print(json.dumps({"variants": rows}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
