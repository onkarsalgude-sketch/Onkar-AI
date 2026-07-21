from __future__ import annotations

import unittest
import warnings

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app


class HealthRouteContractTests(
    unittest.TestCase
):
    def test_root_get_and_head_routes_are_registered(
        self,
    ):
        root_routes = [
            route
            for route in app.routes
            if (
                isinstance(route, APIRoute)
                and route.path == "/"
            )
        ]

        self.assertEqual(
            len(root_routes),
            2,
        )

        routes_by_method = {}

        for route in root_routes:
            for method in route.methods:
                routes_by_method[method] = route

        self.assertEqual(
            set(routes_by_method),
            {
                "GET",
                "HEAD",
            },
        )

        self.assertTrue(
            routes_by_method[
                "GET"
            ].include_in_schema
        )

        self.assertFalse(
            routes_by_method[
                "HEAD"
            ].include_in_schema
        )

        self.assertEqual(
            routes_by_method[
                "HEAD"
            ].operation_id,
            "root_head",
        )

    def test_root_head_probe_returns_success(
        self,
    ):
        with TestClient(app) as client:
            get_response = client.get(
                "/"
            )

            head_response = client.head(
                "/"
            )

        self.assertEqual(
            get_response.status_code,
            200,
        )

        self.assertEqual(
            head_response.status_code,
            200,
        )

        self.assertEqual(
            head_response.content,
            b"",
        )

        self.assertEqual(
            head_response.headers.get(
                "content-type"
            ),
            "application/json",
        )

    def test_root_head_is_hidden_from_openapi(
        self,
    ):
        with warnings.catch_warnings(
            record=True
        ) as captured:
            warnings.simplefilter(
                "always"
            )

            specification = (
                app.openapi()
            )

        root_contract = (
            specification[
                "paths"
            ]["/"]
        )

        self.assertIn(
            "get",
            root_contract,
        )

        self.assertNotIn(
            "head",
            root_contract,
        )

        duplicate_warnings = [
            warning
            for warning in captured
            if (
                "Duplicate Operation ID"
                in str(warning.message)
            )
        ]

        self.assertEqual(
            duplicate_warnings,
            [],
        )


if __name__ == "__main__":
    unittest.main()
