from __future__ import annotations

import json
import re
from typing import Any


def parse_json_fenced(text: str, default: Any = None) -> Any:
    stripped = text.strip()
    if not stripped:
        return {} if default is None else default

    fenced = re.search(
        r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```",
        stripped,
        re.DOTALL | re.IGNORECASE,
    )
    candidate = fenced.group(1) if fenced else stripped

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    starts = [idx for idx in (candidate.find("{"), candidate.find("[")) if idx >= 0]
    if not starts:
        return {} if default is None else default

    start = min(starts)
    end_obj = candidate.rfind("}")
    end_arr = candidate.rfind("]")
    end = max(end_obj, end_arr)
    if end <= start:
        return {} if default is None else default

    try:
        return json.loads(candidate[start:end + 1])
    except json.JSONDecodeError:
        return {} if default is None else default
