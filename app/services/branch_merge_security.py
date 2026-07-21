"""Isolated security controls for the administrative branch-merge route.

The limiter is deliberately process-local. Deployments with multiple workers
or backend instances must replace it with shared, atomic rate-limit storage.
"""

import hashlib
import math
import secrets
import threading
import time
from collections import deque


BRANCH_MERGE_INTENT = "v1"

BRANCH_MERGE_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; frame-ancestors 'none'"
    ),
    "X-Frame-Options": "DENY",
}


class BranchMergeRateLimitExceeded(Exception):
    def __init__(self, retry_after):
        super().__init__("Branch merge rate limit exceeded.")
        self.retry_after = max(1, int(retry_after))


def _hash_submitted_token(plaintext_token):
    return hashlib.sha256(
        plaintext_token.encode("utf-8")
    ).hexdigest()


def verify_branch_merge_bearer(
    authorization_header,
    configured_sha256,
):
    """Verify a fixed capability token with one digest/compare code path."""

    if isinstance(configured_sha256, str):
        configured_sha256 = configured_sha256.strip().casefold()
    candidate = ""
    valid_format = False

    if isinstance(authorization_header, str):
        pieces = authorization_header.split(" ")

        if (
            len(pieces) == 2
            and pieces[0].casefold() == "bearer"
            and pieces[1]
        ):
            candidate = pieces[1]
            valid_format = True

    submitted_sha256 = _hash_submitted_token(candidate)
    digest_matches = secrets.compare_digest(
        submitted_sha256,
        configured_sha256,
    )
    return valid_format and digest_matches


def is_exact_allowed_origin(origin, allowed_origins):
    return (
        isinstance(origin, str)
        and origin != "null"
        and origin in allowed_origins
    )


def is_valid_branch_merge_intent(intent):
    return intent == BRANCH_MERGE_INTENT


def get_direct_client_address(request):
    """Use ASGI peer data only; forwarded headers are not trusted here."""
    if request.client is None or not request.client.host:
        return "unknown"

    return request.client.host


class BranchMergeRateLimiter:
    """Bounded, process-local sliding-window limiter for merge attempts."""

    def __init__(
        self,
        rate_per_minute,
        rate_per_hour,
        *,
        failed_rate_per_minute=None,
        failed_rate_per_hour=None,
        max_identities=4096,
        clock=None,
    ):
        self.rate_per_minute = rate_per_minute
        self.rate_per_hour = rate_per_hour
        self.failed_rate_per_minute = (
            failed_rate_per_minute
            if failed_rate_per_minute is not None
            else rate_per_minute
        )
        self.failed_rate_per_hour = (
            failed_rate_per_hour
            if failed_rate_per_hour is not None
            else rate_per_hour
        )
        self.max_identities = max(1, max_identities)
        self._clock = clock or time.monotonic
        self._failed_attempts = {}
        self._authenticated_attempts = {}
        self._lock = threading.Lock()

    @staticmethod
    def _prune_events(events, now):
        cutoff = now - 3600

        while events and events[0] <= cutoff:
            events.popleft()

    @staticmethod
    def _retry_after(events, now, minute_limit, hour_limit):
        minute_events = [
            timestamp
            for timestamp in events
            if timestamp > now - 60
        ]
        waits = []

        if len(minute_events) >= minute_limit:
            waits.append(
                minute_events[-minute_limit] + 60 - now
            )

        if len(events) >= hour_limit:
            waits.append(events[-hour_limit] + 3600 - now)

        return max(1, math.ceil(max(waits, default=1)))

    def _prune_store(self, store, now):
        expired_keys = []

        for key, events in store.items():
            self._prune_events(events, now)

            if not events:
                expired_keys.append(key)

        for key in expired_keys:
            store.pop(key, None)

    def _events_for(self, store, key, now):
        events = store.get(key)

        if events is not None:
            self._prune_events(events, now)
            return events

        if len(store) >= self.max_identities:
            self._prune_store(store, now)

        while len(store) >= self.max_identities:
            store.pop(next(iter(store)))

        events = deque()
        store[key] = events
        return events

    @staticmethod
    def _is_limited(events, now, minute_limit, hour_limit):
        minute_count = sum(
            timestamp > now - 60
            for timestamp in events
        )
        return (
            minute_count >= minute_limit
            or len(events) >= hour_limit
        )

    def check_failed_auth(self, client_address):
        with self._lock:
            now = self._clock()
            events = self._events_for(
                self._failed_attempts,
                client_address,
                now,
            )

            if self._is_limited(
                events,
                now,
                self.failed_rate_per_minute,
                self.failed_rate_per_hour,
            ):
                raise BranchMergeRateLimitExceeded(
                    self._retry_after(
                        events,
                        now,
                        self.failed_rate_per_minute,
                        self.failed_rate_per_hour,
                    )
                )

    def record_failed_auth(self, client_address):
        with self._lock:
            now = self._clock()
            events = self._events_for(
                self._failed_attempts,
                client_address,
                now,
            )
            events.append(now)

    def consume_authenticated(
        self,
        client_address,
        credential_identity,
    ):
        key = (
            client_address,
            credential_identity,
        )

        with self._lock:
            now = self._clock()
            events = self._events_for(
                self._authenticated_attempts,
                key,
                now,
            )

            if self._is_limited(
                events,
                now,
                self.rate_per_minute,
                self.rate_per_hour,
            ):
                raise BranchMergeRateLimitExceeded(
                    self._retry_after(
                        events,
                        now,
                        self.rate_per_minute,
                        self.rate_per_hour,
                    )
                )

            events.append(now)
