"""Guarded API exposure for authoritative branch merge execution."""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.models.chat import (
    BranchMergeRequest,
    BranchMergeResponse,
)
from app.services.branch_merge_security import (
    BRANCH_MERGE_SECURITY_HEADERS,
    BranchMergeRateLimiter,
    BranchMergeRateLimitExceeded,
    get_direct_client_address,
    is_exact_allowed_origin,
    is_valid_branch_merge_intent,
    verify_branch_merge_bearer,
)
from app.services.branch_merge_service import (
    BranchMergeError,
    execute_branch_merge,
)


logger = logging.getLogger(__name__)

_SERVICE_ERROR_STATUSES = {
    "BRANCH_NOT_FOUND": 404,
    "PARENT_MISSING": 409,
    "DETACHED_BRANCH": 409,
    "INVALID_BRANCH_BOUNDARY": 409,
    "STALE_PREVIEW": 409,
    "IDEMPOTENCY_KEY_REUSED": 409,
    "MERGE_ALREADY_COMPLETED": 409,
    "EMPTY_SELECTION": 422,
    "INVALID_SELECTED_TURN": 422,
    "ORPHAN_SELECTED_MESSAGE": 422,
    "DUPLICATE_SELECTED_ID": 422,
    "MESSAGE_NOT_OWNED_BY_BRANCH": 422,
    "MESSAGE_OUTSIDE_BRANCH_CONTINUATION": 422,
    "MERGE_BUSY": 503,
    "MERGE_FAILED": 500,
}


def _safe_response(status_code, detail, *, headers=None):
    response_headers = dict(
        BRANCH_MERGE_SECURITY_HEADERS
    )
    response_headers.update(headers or {})
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers=response_headers,
    )


def _safe_error_detail(
    code,
    message,
    *,
    retryable=False,
    refresh_preview=False,
    operation_id=None,
):
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "refresh_preview": refresh_preview,
        "operation_id": operation_id,
    }


def _unsupported_media_response():
    return _safe_response(
        415,
        _safe_error_detail(
            "UNSUPPORTED_MEDIA_TYPE",
            "Content-Type must be application/json.",
        ),
    )


def _request_too_large_response():
    return _safe_response(
        413,
        _safe_error_detail(
            "REQUEST_TOO_LARGE",
            "The merge request body is too large.",
        ),
    )


def _rate_limit_response(error):
    return _safe_response(
        429,
        _safe_error_detail(
            "MERGE_RATE_LIMITED",
            "Too many branch merge attempts. Retry later.",
            retryable=True,
        ),
        headers={
            "Retry-After": str(error.retry_after),
        },
    )


def _has_json_content_type(request):
    value = request.headers.get("content-type", "")
    pieces = [piece.strip() for piece in value.split(";")]

    if not pieces or pieces[0].casefold() != "application/json":
        return False

    parameters = pieces[1:]

    if not parameters:
        return True

    if len(parameters) != 1 or "=" not in parameters[0]:
        return False

    name, charset = parameters[0].split("=", 1)
    return (
        name.strip().casefold() == "charset"
        and bool(charset.strip())
    )


async def _read_limited_body(request, max_body_bytes):
    content_length = request.headers.get("content-length")

    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = None

        if (
            declared_length is not None
            and declared_length > max_body_bytes
        ):
            raise _BodyTooLarge()

    body_parts = []
    total_bytes = 0

    async for chunk in request.stream():
        total_bytes += len(chunk)

        if total_bytes > max_body_bytes:
            raise _BodyTooLarge()

        body_parts.append(chunk)

    return b"".join(body_parts)


class _BodyTooLarge(Exception):
    pass


def _load_json_body(raw_body):
    if not raw_body:
        raise ValueError("empty body")

    def reject_nonstandard_constant(_value):
        raise ValueError("non-standard JSON constant")

    return json.loads(
        raw_body.decode("utf-8"),
        parse_constant=reject_nonstandard_constant,
    )


def _sanitize_validation_errors(error):
    sanitized = []

    for item in error.errors():
        error_type = str(item.get("type", "invalid_value"))

        if error_type == "missing":
            message = "Field is required."
        elif error_type == "extra_forbidden":
            message = "Unexpected field."
        else:
            message = "Invalid value."

        location = []

        for part in item.get("loc", ()):
            if isinstance(part, int):
                location.append(part)
            else:
                location.append(str(part)[:100])

        sanitized.append(
            {
                "loc": location,
                "type": error_type,
                "msg": message,
            }
        )

    return sanitized


def _service_error_response(error):
    status_code = _SERVICE_ERROR_STATUSES.get(error.code)

    if status_code is None:
        logger.error("Unrecognized branch merge service failure")
        return _unexpected_error_response()

    if error.code == "MERGE_FAILED":
        message = "The branch merge could not be completed."
    else:
        message = error.message

    retryable = bool(error.retryable)
    response_headers = {}

    if error.code == "MERGE_BUSY":
        retryable = True
        response_headers["Retry-After"] = "1"

    return _safe_response(
        status_code,
        _safe_error_detail(
            error.code,
            message,
            retryable=retryable,
            refresh_preview=bool(
                error.refresh_preview
            ),
            operation_id=error.operation_id,
        ),
        headers=response_headers,
    )


def _unexpected_error_response():
    return _safe_response(
        500,
        _safe_error_detail(
            "MERGE_FAILED",
            "The branch merge could not be completed.",
        ),
    )


def create_branch_merge_router(
    settings,
    db_path,
    *,
    executor=None,
    rate_limiter=None,
):
    """Create an enabled-only router bound to one authoritative DB path."""
    if not settings.enabled:
        raise ValueError(
            "A disabled branch merge router cannot be created."
        )

    merge_executor = executor or execute_branch_merge
    limiter = rate_limiter or BranchMergeRateLimiter(
        settings.rate_per_minute,
        settings.rate_per_hour,
    )
    router = APIRouter()

    @router.post(
        "/chats/{branch_chat_id}/merge-parent",
        response_model=BranchMergeResponse,
    )
    async def merge_branch_into_parent(
        branch_chat_id: int,
        request: Request,
    ):
        if not _has_json_content_type(request):
            return _unsupported_media_response()

        try:
            raw_body = await _read_limited_body(
                request,
                settings.max_body_bytes,
            )
        except _BodyTooLarge:
            return _request_too_large_response()
        except Exception:
            logger.error("Unable to read branch merge request body")
            return _unexpected_error_response()

        origin = request.headers.get("origin")

        if not is_exact_allowed_origin(
            origin,
            settings.allowed_origins,
        ):
            return _safe_response(
                403,
                _safe_error_detail(
                    "MERGE_ORIGIN_FORBIDDEN",
                    "The request origin is not allowed.",
                ),
            )

        if not is_valid_branch_merge_intent(
            request.headers.get(
                "x-onkar-merge-intent"
            )
        ):
            return _safe_response(
                403,
                _safe_error_detail(
                    "MERGE_INTENT_REQUIRED",
                    "The branch merge intent header is required.",
                ),
            )

        client_address = get_direct_client_address(
            request
        )

        try:
            limiter.check_failed_auth(
                client_address
            )
        except BranchMergeRateLimitExceeded as error:
            return _rate_limit_response(error)

        authenticated = verify_branch_merge_bearer(
            request.headers.get("authorization"),
            settings.token_sha256,
        )

        if not authenticated:
            limiter.record_failed_auth(
                client_address
            )
            return _safe_response(
                401,
                _safe_error_detail(
                    "MERGE_AUTH_REQUIRED",
                    "Valid branch merge authorization is required.",
                ),
                headers={
                    "WWW-Authenticate": "Bearer",
                },
            )

        try:
            limiter.consume_authenticated(
                client_address,
                settings.token_sha256,
            )
        except BranchMergeRateLimitExceeded as error:
            return _rate_limit_response(error)

        try:
            submitted_data = _load_json_body(
                raw_body
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
        ):
            return _safe_response(
                400,
                _safe_error_detail(
                    "INVALID_JSON",
                    "The merge request body must be valid JSON.",
                ),
            )

        try:
            merge_request = (
                BranchMergeRequest.model_validate(
                    submitted_data
                )
            )
        except ValidationError as error:
            return _safe_response(
                422,
                {
                    **_safe_error_detail(
                        "INVALID_MERGE_REQUEST",
                        "The merge request is invalid.",
                    ),
                    "errors": (
                        _sanitize_validation_errors(
                            error
                        )
                    ),
                },
            )

        try:
            result = await run_in_threadpool(
                merge_executor,
                db_path,
                branch_chat_id,
                merge_request,
            )
            safe_result = (
                BranchMergeResponse.model_validate(
                    result
                )
            )
        except BranchMergeError as error:
            return _service_error_response(error)
        except Exception:
            logger.error("Unexpected branch merge execution failure")
            return _unexpected_error_response()

        return JSONResponse(
            status_code=200,
            content=safe_result.model_dump(
                mode="json"
            ),
            headers=dict(
                BRANCH_MERGE_SECURITY_HEADERS
            ),
        )

    return router
