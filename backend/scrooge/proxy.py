from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, Request

from scrooge.config import Settings, get_settings
from scrooge.optimizer import optimize_prompt
from scrooge.schemas import OptimizeRequest, ProxyCaptureResponse, UsageState
from scrooge.storage import UsageStore

router = APIRouter(prefix="/proxy", tags=["proxy"])


def extract_prompt(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""

    if isinstance(payload.get("prompt"), str):
        return payload["prompt"]
    if isinstance(payload.get("input"), str):
        return payload["input"]
    if isinstance(payload.get("input"), list):
        return "\n".join(str(item) for item in payload["input"])

    messages = payload.get("messages")
    if isinstance(messages, list):
        parts: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(
                    str(block.get("text"))
                    for block in content
                    if isinstance(block, dict) and block.get("text")
                )
        return "\n".join(parts)

    return ""


@router.api_route("/{provider}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def capture_and_forward(
    provider: str,
    path: str,
    request: Request,
    x_scrooge_forward: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> ProxyCaptureResponse:
    store = UsageStore(settings)
    payload: Any | None = None
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            payload = await request.json()
        except Exception:
            payload = None

    prompt = extract_prompt(payload)
    preview = None
    if prompt:
        model = _extract_model(payload) or settings.default_model
        preview = optimize_prompt(OptimizeRequest(prompt=prompt, provider=provider, model=model))
        store.save_preview(preview, provider=provider, model=model)

    should_forward = x_scrooge_forward == "true"
    upstream_body = None
    upstream_status = None
    if should_forward:
        upstream_base = settings.upstream_for(provider)
        if upstream_base:
            upstream_status, upstream_body = await _forward_request(upstream_base, path, request, payload)
            if preview:
                store.mark_state(
                    preview.request_id,
                    UsageState.SENT if 200 <= (upstream_status or 500) < 300 else UsageState.FAILED,
                )

    return ProxyCaptureResponse(
        request_id=preview.request_id if preview else "uncaptured",
        captured=preview is not None,
        forwarded=should_forward and upstream_status is not None,
        upstream_status=upstream_status,
        preview=preview,
        upstream_body=upstream_body,
    )


async def _forward_request(
    upstream_base: str,
    path: str,
    original_request: Request,
    payload: Any | None,
) -> tuple[int, Any]:
    headers = {
        key: value
        for key, value in original_request.headers.items()
        if key.lower() not in {"host", "content-length", "x-scrooge-forward"}
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.request(
            original_request.method,
            f"{upstream_base}/{path}",
            headers=headers,
            params=original_request.query_params,
            json=payload,
        )
    try:
        body: Any = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _extract_model(payload: Any) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("model"), str):
        return payload["model"]
    return None

