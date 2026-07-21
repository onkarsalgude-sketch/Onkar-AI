from __future__ import annotations

import unittest
import warnings

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.documents import router


PREVIEW_PATH = (
    "/documents/{filename}/preview"
)


class DocumentRouteContractTests(
    unittest.TestCase
):
    def test_preview_get_and_head_routes_are_separate(
        self,
    ):
        routes = [
            route
            for route in router.routes
            if (
                isinstance(route, APIRoute)
                and route.path == PREVIEW_PATH
            )
        ]

        self.assertEqual(
            len(routes),
            2,
        )

        routes_by_method = {}

        for route in routes:
            for method in route.methods:
                routes_by_method[method] = route

        self.assertEqual(
            set(routes_by_method),
            {
                "GET",
                "HEAD",
            },
        )

        self.assertEqual(
            routes_by_method[
                "GET"
            ].operation_id,
            "preview_pdf_get",
        )

        self.assertEqual(
            routes_by_method[
                "HEAD"
            ].operation_id,
            "preview_pdf_head",
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

    def test_openapi_has_no_duplicate_operation_ids(
        self,
    ):
        application = FastAPI()
        application.include_router(
            router
        )

        with warnings.catch_warnings(
            record=True
        ) as captured:
            warnings.simplefilter(
                "always"
            )

            specification = (
                application.openapi()
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

        preview_contract = (
            specification[
                "paths"
            ][PREVIEW_PATH]
        )

        self.assertIn(
            "get",
            preview_contract,
        )

        self.assertNotIn(
            "head",
            preview_contract,
        )

        self.assertEqual(
            preview_contract[
                "get"
            ]["operationId"],
            "preview_pdf_get",
        )

        operation_ids = []

        for path_contract in (
            specification["paths"].values()
        ):
            for method, operation in (
                path_contract.items()
            ):
                if method not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                }:
                    continue

                operation_id = operation.get(
                    "operationId"
                )

                if operation_id:
                    operation_ids.append(
                        operation_id
                    )

        self.assertEqual(
            len(operation_ids),
            len(set(operation_ids)),
        )


if __name__ == "__main__":
    unittest.main()
