from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.config.system_incident_alerting import (
    DEFAULT_SYSTEM_INCIDENT_ALERTS_ENABLED,
    DEFAULT_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS,
    MAX_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS,
    MIN_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS,
    SystemIncidentAlertingConfigurationError,
    SystemIncidentAlertingSettings,
    load_system_incident_alerting_settings,
    validate_system_incident_alerting_settings,
)
from app.services.system_incident_alert_service import (
    MAX_ALERT_TRANSITIONS,
    SystemIncidentAlertError,
    build_system_incident_alert_payload,
    deliver_system_incident_alerts,
)


WEBHOOK_URL = (
    "https://alerts.example.test/"
    "hooks/private-token"
)


def enabled_settings(
    *,
    timeout_seconds=5.0,
):
    return SystemIncidentAlertingSettings(
        enabled=True,
        webhook_url=WEBHOOK_URL,
        timeout_seconds=timeout_seconds,
    )


def signal(
    *,
    component="database",
    severity="critical",
    source_status="unavailable",
    detail="database_unreachable",
    critical=True,
    fingerprint=None,
):
    return {
        "incident_key": (
            "system_health:"
            + component
        ),
        "component": component,
        "severity": severity,
        "source_status": source_status,
        "detail": detail,
        "critical": critical,
        "fingerprint": (
            fingerprint
            if fingerprint is not None
            else "a" * 64
        ),
    }


def evaluation(
    *,
    opened=None,
    updated=None,
    resolved=None,
    unchanged=None,
):
    return {
        "service": "system_incidents",
        "observed_at": (
            "2026-07-22T10:00:00Z"
        ),
        "opened": (
            []
            if opened is None
            else opened
        ),
        "updated": (
            []
            if updated is None
            else updated
        ),
        "resolved": (
            []
            if resolved is None
            else resolved
        ),
        "unchanged": (
            []
            if unchanged is None
            else unchanged
        ),
    }


class FakeResponse:
    def __init__(
        self,
        status_code,
    ):
        self.status_code = status_code
        self.closed = False

    def close(
        self,
    ):
        self.closed = True


class SystemIncidentAlertingTests(
    unittest.TestCase
):
    def test_defaults_are_disabled(
        self,
    ):
        self.assertFalse(
            DEFAULT_SYSTEM_INCIDENT_ALERTS_ENABLED
        )
        self.assertEqual(
            DEFAULT_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS,
            5.0,
        )

    def test_disabled_environment_loads_without_url(
        self,
    ):
        settings = load_system_incident_alerting_settings(
            {}
        )

        self.assertFalse(
            settings.enabled
        )
        self.assertEqual(
            settings.webhook_url,
            "",
        )

    def test_enabled_environment_normalizes_values(
        self,
    ):
        settings = load_system_incident_alerting_settings(
            {
                "SYSTEM_INCIDENT_ALERTS_ENABLED": "YES",
                "SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL": (
                    "  "
                    + WEBHOOK_URL
                    + "  "
                ),
                "SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS": (
                    "7.5"
                ),
            }
        )

        self.assertTrue(
            settings.enabled
        )
        self.assertEqual(
            settings.webhook_url,
            WEBHOOK_URL,
        )
        self.assertEqual(
            settings.timeout_seconds,
            7.5,
        )

    def test_enabled_requires_url(
        self,
    ):
        with self.assertRaises(
            SystemIncidentAlertingConfigurationError
        ):
            validate_system_incident_alerting_settings(
                SystemIncidentAlertingSettings(
                    enabled=True
                )
            )

    def test_non_https_url_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemIncidentAlertingConfigurationError
        ):
            validate_system_incident_alerting_settings(
                SystemIncidentAlertingSettings(
                    enabled=True,
                    webhook_url=(
                        "http://alerts.example.test/hook"
                    ),
                )
            )

    def test_url_credentials_are_rejected(
        self,
    ):
        with self.assertRaises(
            SystemIncidentAlertingConfigurationError
        ):
            validate_system_incident_alerting_settings(
                SystemIncidentAlertingSettings(
                    enabled=True,
                    webhook_url=(
                        "https://user:password@"
                        "alerts.example.test/hook"
                    ),
                )
            )

    def test_url_fragment_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemIncidentAlertingConfigurationError
        ):
            validate_system_incident_alerting_settings(
                SystemIncidentAlertingSettings(
                    enabled=True,
                    webhook_url=(
                        WEBHOOK_URL
                        + "#fragment"
                    ),
                )
            )

    def test_timeout_bounds_are_enforced(
        self,
    ):
        for timeout_seconds in (
            (
                MIN_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS
                - 0.1
            ),
            (
                MAX_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS
                + 0.1
            ),
        ):
            with self.subTest(
                timeout_seconds=timeout_seconds
            ):
                with self.assertRaises(
                    SystemIncidentAlertingConfigurationError
                ):
                    validate_system_incident_alerting_settings(
                        enabled_settings(
                            timeout_seconds=(
                                timeout_seconds
                            )
                        )
                    )

    def test_repr_hides_webhook_url(
        self,
    ):
        rendered = repr(
            enabled_settings()
        )

        self.assertNotIn(
            "private-token",
            rendered,
        )
        self.assertNotIn(
            WEBHOOK_URL,
            rendered,
        )

    def test_disabled_provider_does_not_call_sender(
        self,
    ):
        calls = []

        result = deliver_system_incident_alerts(
            SystemIncidentAlertingSettings(),
            {
                "unsafe": (
                    "password=do-not-read"
                ),
            },
            sender=lambda *args: calls.append(
                args
            ),
        )

        self.assertFalse(
            result["attempted"]
        )
        self.assertEqual(
            calls,
            [],
        )

    def test_unchanged_transitions_are_suppressed(
        self,
    ):
        calls = []

        result = deliver_system_incident_alerts(
            enabled_settings(),
            evaluation(
                unchanged=[
                    signal()
                ]
            ),
            sender=lambda *args: calls.append(
                args
            ),
            now=lambda: datetime(
                2026,
                7,
                22,
                10,
                1,
                tzinfo=timezone.utc,
            ),
        )

        self.assertFalse(
            result["attempted"]
        )
        self.assertEqual(
            calls,
            [],
        )

    def test_opened_alert_is_delivered(
        self,
    ):
        calls = []

        result = deliver_system_incident_alerts(
            enabled_settings(),
            evaluation(
                opened=[
                    signal()
                ]
            ),
            sender=lambda *args: calls.append(
                args
            ),
            now=lambda: datetime(
                2026,
                7,
                22,
                10,
                1,
                tzinfo=timezone.utc,
            ),
        )

        self.assertTrue(
            result["delivered"]
        )
        self.assertEqual(
            result["transition_count"],
            1,
        )
        self.assertEqual(
            len(
                calls
            ),
            1,
        )

        url, payload, timeout_seconds = (
            calls[0]
        )

        self.assertEqual(
            url,
            WEBHOOK_URL,
        )
        self.assertEqual(
            timeout_seconds,
            5.0,
        )
        self.assertEqual(
            payload["transitions"][0][
                "transition"
            ],
            "opened",
        )
        self.assertEqual(
            payload["transitions"][0][
                "state"
            ],
            "open",
        )

    def test_updated_and_resolved_states_are_distinct(
        self,
    ):
        payload = build_system_incident_alert_payload(
            evaluation(
                updated=[
                    signal(
                        detail="database_timeout"
                    )
                ],
                resolved=[
                    signal(
                        component=(
                            "document_recovery"
                        ),
                        severity="warning",
                        detail="recovery_failed",
                        critical=False,
                        fingerprint="b" * 64,
                    )
                ],
            ),
            now=lambda: datetime(
                2026,
                7,
                22,
                10,
                2,
                tzinfo=timezone.utc,
            ),
        )

        self.assertIsNotNone(
            payload
        )

        self.assertEqual(
            [
                item["transition"]
                for item in payload[
                    "transitions"
                ]
            ],
            [
                "updated",
                "resolved",
            ],
        )

        self.assertEqual(
            [
                item["state"]
                for item in payload[
                    "transitions"
                ]
            ],
            [
                "open",
                "resolved",
            ],
        )

    def test_unsafe_transition_values_are_sanitized(
        self,
    ):
        unsafe_signal = {
            "incident_key": "<script>",
            "component": "DATABASE PASSWORD",
            "severity": "root",
            "source_status": "exploded",
            "detail": "password=secret",
            "critical": "true",
            "fingerprint": "credential",
            "database_url": (
                "postgresql://secret"
            ),
        }

        payload = build_system_incident_alert_payload(
            evaluation(
                opened=[
                    unsafe_signal
                ]
            ),
            now=lambda: datetime(
                2026,
                7,
                22,
                10,
                3,
                tzinfo=timezone.utc,
            ),
        )

        self.assertIsNotNone(
            payload
        )

        transition = payload[
            "transitions"
        ][0]

        self.assertEqual(
            transition["incident_key"],
            "system_health:unknown",
        )
        self.assertEqual(
            transition["component"],
            "unknown",
        )
        self.assertEqual(
            transition["severity"],
            "warning",
        )
        self.assertEqual(
            transition["source_status"],
            "unavailable",
        )
        self.assertEqual(
            transition["detail"],
            "check_failed",
        )
        self.assertFalse(
            transition["critical"]
        )
        self.assertEqual(
            transition["fingerprint"],
            "0" * 64,
        )

        serialized = str(
            payload
        ).casefold()

        for forbidden in (
            "password",
            "credential",
            "database_url",
            "postgresql://",
            "script",
        ):
            self.assertNotIn(
                forbidden,
                serialized,
            )

    def test_transition_limit_is_enforced(
        self,
    ):
        with self.assertRaises(
            SystemIncidentAlertError
        ):
            build_system_incident_alert_payload(
                evaluation(
                    opened=[
                        signal(
                            component=(
                                "component_"
                                + str(index)
                            )
                        )
                        for index in range(
                            MAX_ALERT_TRANSITIONS
                            + 1
                        )
                    ]
                )
            )

    def test_invalid_evaluation_shape_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemIncidentAlertError
        ):
            build_system_incident_alert_payload(
                {
                    "opened": {},
                }
            )

    def test_invalid_sender_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemIncidentAlertError
        ):
            deliver_system_incident_alerts(
                enabled_settings(),
                evaluation(
                    opened=[
                        signal()
                    ]
                ),
                sender=None,
            )

    def test_sender_failure_is_generic(
        self,
    ):
        def failing_sender(
            webhook_url,
            payload,
            timeout_seconds,
        ):
            del webhook_url
            del payload
            del timeout_seconds

            raise RuntimeError(
                "private-token password secret"
            )

        with self.assertRaises(
            SystemIncidentAlertError
        ) as caught:
            deliver_system_incident_alerts(
                enabled_settings(),
                evaluation(
                    opened=[
                        signal()
                    ]
                ),
                sender=failing_sender,
            )

        self.assertEqual(
            str(
                caught.exception
            ),
            "System incident alert delivery failed.",
        )
        self.assertNotIn(
            "private-token",
            str(
                caught.exception
            ),
        )

    def test_default_sender_uses_safe_http_contract(
        self,
    ):
        response = FakeResponse(
            204
        )

        with patch(
            (
                "app.services."
                "system_incident_alert_service."
                "requests.post"
            ),
            return_value=response,
        ) as post:
            result = (
                deliver_system_incident_alerts(
                    enabled_settings(
                        timeout_seconds=6.5
                    ),
                    evaluation(
                        opened=[
                            signal()
                        ]
                    ),
                    now=lambda: datetime(
                        2026,
                        7,
                        22,
                        10,
                        4,
                        tzinfo=timezone.utc,
                    ),
                )
            )

        self.assertTrue(
            result["delivered"]
        )
        self.assertTrue(
            response.closed
        )

        _, keyword_arguments = (
            post.call_args
        )

        self.assertEqual(
            keyword_arguments["timeout"],
            6.5,
        )
        self.assertFalse(
            keyword_arguments[
                "allow_redirects"
            ]
        )
        self.assertIn(
            "json",
            keyword_arguments,
        )

    def test_non_success_response_is_generic(
        self,
    ):
        response = FakeResponse(
            500
        )

        with patch(
            (
                "app.services."
                "system_incident_alert_service."
                "requests.post"
            ),
            return_value=response,
        ):
            with self.assertRaises(
                SystemIncidentAlertError
            ) as caught:
                deliver_system_incident_alerts(
                    enabled_settings(),
                    evaluation(
                        opened=[
                            signal()
                        ]
                    ),
                )

        self.assertTrue(
            response.closed
        )
        self.assertEqual(
            str(
                caught.exception
            ),
            "System incident alert delivery failed.",
        )

    def test_sent_at_is_normalized_to_utc(
        self,
    ):
        payload = build_system_incident_alert_payload(
            evaluation(
                opened=[
                    signal()
                ]
            ),
            now=lambda: datetime(
                2026,
                7,
                22,
                15,
                30,
                tzinfo=timezone(
                    timedelta(
                        hours=5,
                        minutes=30,
                    )
                ),
            ),
        )

        self.assertIsNotNone(
            payload
        )
        self.assertEqual(
            payload["sent_at"],
            "2026-07-22T10:00:00+00:00",
        )
        self.assertEqual(
            payload["observed_at"],
            "2026-07-22T10:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
