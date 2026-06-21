from copy import deepcopy
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, Request

from scrooge.config import Settings, get_settings
from scrooge.optimizer import optimize_prompt
from scrooge.schemas import (
    AttachmentDiscoverySource,
    AttachmentMetadata,
    AttachmentTokenStatus,
    CaptureSource,
    MeasurementRequest,
    OptimizeRequest,
    ProxyCaptureResponse,
    UsageState,
)
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
    optimized_payload = payload
    optimized_forwarded = False
    if prompt:
        model = _extract_model(payload) or settings.default_model
        attachments = extract_attachments(payload)
        preview = optimize_prompt(
            OptimizeRequest(prompt=prompt, provider=provider, model=model, attachments=attachments)
        )
        store.save_preview(
            preview,
            provider=provider,
            model=model,
            capture_source=CaptureSource.PROXY,
            attachments=attachments,
        )
        optimized_payload, optimized_forwarded = apply_optimized_prompt(payload, preview.optimized_prompt)

    should_forward = x_scrooge_forward == "true"
    upstream_body = None
    upstream_status = None
    if should_forward:
        upstream_base = settings.upstream_for(provider)
        if upstream_base:
            upstream_status, upstream_body = await _forward_request(upstream_base, path, request, optimized_payload)
            if preview:
                if 200 <= (upstream_status or 500) < 300:
                    usage = extract_provider_usage(provider, upstream_body)
                    if usage is not None:
                        store.record_measurement(
                            preview.request_id,
                            MeasurementRequest(
                                measured_original_tokens=preview.original_tokens.input_tokens,
                                measured_input_tokens=usage[0],
                                measured_output_tokens=usage[1],
                                source=usage[2],
                                upstream_status=upstream_status,
                            ),
                        )
                    else:
                        store.mark_state(preview.request_id, UsageState.SENT, upstream_status=upstream_status)
                else:
                    store.mark_state(
                        preview.request_id,
                        UsageState.FAILED,
                        upstream_status=upstream_status,
                        failure_reason="upstream_non_2xx",
                    )

    return ProxyCaptureResponse(
        request_id=preview.request_id if preview else "uncaptured",
        captured=preview is not None,
        forwarded=should_forward and upstream_status is not None,
        optimized_forwarded=optimized_forwarded and should_forward and upstream_status is not None,
        upstream_status=upstream_status,
        preview=preview,
        upstream_body=upstream_body,
    )


def apply_optimized_prompt(payload: Any, optimized_prompt: str) -> tuple[Any, bool]:
    if isinstance(payload, str):
        return optimized_prompt, True
    if not isinstance(payload, dict):
        return payload, False

    updated = deepcopy(payload)
    if isinstance(updated.get("prompt"), str):
        updated["prompt"] = optimized_prompt
        return updated, True
    if isinstance(updated.get("input"), str):
        updated["input"] = optimized_prompt
        return updated, True
    if isinstance(updated.get("input"), list):
        updated["input"] = [optimized_prompt]
        return updated, True

    messages = updated.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            if message.get("role") not in {None, "user"}:
                continue
            content = message.get("content")
            if isinstance(content, str):
                message["content"] = optimized_prompt
                return updated, True
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") in {None, "text", "input_text"}:
                        block["text"] = optimized_prompt
                        return updated, True
        updated["messages"].append({"role": "user", "content": optimized_prompt})
        return updated, True

    return payload, False


def extract_attachments(payload: Any) -> list[AttachmentMetadata]:
    if not isinstance(payload, dict):
        return []
    attachments: list[AttachmentMetadata] = []
    for key in ("attachments", "files"):
        value = payload.get(key)
        if isinstance(value, list):
            for index, item in enumerate(value):
                attachment = _attachment_from_object(item, fallback_name=f"{key}-{index + 1}")
                if attachment:
                    attachments.append(attachment)

    messages = payload.get("messages")
    if isinstance(messages, list):
        for message_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block_index, block in enumerate(content):
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type") or "")
                if block_type in {"file", "input_file", "image", "input_image"} or block.get("file_id"):
                    attachment = _attachment_from_object(
                        block,
                        fallback_name=f"message-{message_index + 1}-attachment-{block_index + 1}",
                    )
                    if attachment:
                        attachments.append(attachment)
    return attachments


def _attachment_from_object(value: Any, fallback_name: str) -> AttachmentMetadata | None:
    if isinstance(value, str):
        return AttachmentMetadata(name=value, token_status=AttachmentTokenStatus.UNKNOWN)
    if not isinstance(value, dict):
        return None
    name = (
        value.get("name")
        or value.get("filename")
        or value.get("file_name")
        or value.get("file_id")
        or value.get("id")
        or fallback_name
    )
    size_bytes = _int_or_none(value.get("size_bytes") or value.get("size"))
    estimated_tokens = _int_or_none(value.get("estimated_tokens"))
    token_status = AttachmentTokenStatus.ESTIMATED if estimated_tokens is not None else AttachmentTokenStatus.UNKNOWN
    return AttachmentMetadata(
        name=str(name),
        mime_type=value.get("mime_type") or value.get("mimeType"),
        size_bytes=size_bytes,
        content_hash=value.get("content_hash") or value.get("sha256"),
        token_status=token_status,
        estimated_tokens=estimated_tokens,
        discovery_source=AttachmentDiscoverySource.PROXY_PAYLOAD,
        content_available=False,
        path_available=False,
    )


def extract_provider_usage(provider: str, body: Any) -> tuple[int, int, str] | None:
    if not isinstance(body, dict):
        return None
    provider_name = provider.lower()
    if provider_name == "openai":
        usage = body.get("usage")
        if isinstance(usage, dict):
            input_tokens = _int_or_none(usage.get("input_tokens") or usage.get("prompt_tokens"))
            output_tokens = _int_or_none(usage.get("output_tokens") or usage.get("completion_tokens"))
            if input_tokens is not None and output_tokens is not None:
                return input_tokens, output_tokens, "openai_usage"
    if provider_name == "anthropic":
        usage = body.get("usage")
        if isinstance(usage, dict):
            input_tokens = _int_or_none(usage.get("input_tokens"))
            output_tokens = _int_or_none(usage.get("output_tokens"))
            if input_tokens is not None and output_tokens is not None:
                return input_tokens, output_tokens, "anthropic_usage"
    if provider_name == "gemini":
        usage = body.get("usageMetadata")
        if isinstance(usage, dict):
            input_tokens = _int_or_none(usage.get("promptTokenCount"))
            output_tokens = _int_or_none(usage.get("candidatesTokenCount"))
            if output_tokens is None:
                total_tokens = _int_or_none(usage.get("totalTokenCount"))
                output_tokens = (
                    max(0, total_tokens - input_tokens)
                    if total_tokens is not None and input_tokens is not None
                    else None
                )
            if input_tokens is not None and output_tokens is not None:
                return input_tokens, output_tokens, "gemini_usage_metadata"
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


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
