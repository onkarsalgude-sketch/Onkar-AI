from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.registry import (
    AgentRegistry,
)
from app.api import agents as agents_api
from app.main import app
from app.models.agent import (
    AgentCatalogItem,
    AgentCatalogResponse,
    MAX_AGENT_CAPABILITY_LENGTH,
    MAX_AGENT_CATALOG_SIZE,
    MAX_AGENT_DESCRIPTION_LENGTH,
    MAX_AGENT_NAME_LENGTH,
)


EXPECTED_AGENT_IDS = (
    "coding",
    "document",
    "general-chat",
    "market-research",
    "study",
)

SAFE_AGENT_KEYS = {
    "agent_id",
    "name",
    "description",
    "capabilities",
}


class AgentCatalogApiTests(
    unittest.TestCase
):
    def test_models_are_frozen_and_bounded(
        self,
    ):
        self.assertTrue(
            AgentCatalogItem
            .model_config["frozen"]
        )
        self.assertTrue(
            AgentCatalogResponse
            .model_config["frozen"]
        )
        self.assertEqual(
            AgentCatalogItem
            .model_fields["name"]
            .metadata[0]
            .min_length,
            1,
        )
        self.assertEqual(
            AgentCatalogItem
            .model_fields["name"]
            .metadata[1]
            .max_length,
            MAX_AGENT_NAME_LENGTH,
        )
        self.assertEqual(
            AgentCatalogItem
            .model_fields["description"]
            .metadata[1]
            .max_length,
            MAX_AGENT_DESCRIPTION_LENGTH,
        )
        self.assertEqual(
            AgentCatalogResponse
            .model_fields["agents"]
            .metadata[1]
            .max_length,
            MAX_AGENT_CATALOG_SIZE,
        )

        response = agents_api.list_agents()

        with self.assertRaises(
            ValidationError
        ):
            response.agents = ()

        with self.assertRaises(
            ValidationError
        ):
            response.agents[0].name = (
                "Changed"
            )

    def test_endpoint_returns_exact_safe_catalog(
        self,
    ):
        response = agents_api.list_agents()

        self.assertIsInstance(
            response,
            AgentCatalogResponse,
        )
        self.assertEqual(
            tuple(
                item.agent_id
                for item in response.agents
            ),
            EXPECTED_AGENT_IDS,
        )

        payload = response.model_dump(
            mode="json"
        )

        self.assertEqual(
            set(payload),
            {
                "agents",
            },
        )
        self.assertEqual(
            len(payload["agents"]),
            5,
        )

        for item in payload["agents"]:
            self.assertEqual(
                set(item),
                SAFE_AGENT_KEYS,
            )
            self.assertTrue(
                item["agent_id"]
            )
            self.assertTrue(item["name"])
            self.assertTrue(
                item["description"]
            )
            self.assertTrue(
                item["capabilities"]
            )

    def test_capabilities_serialize_as_json_arrays(
        self,
    ):
        payload = (
            agents_api
            .list_agents()
            .model_dump(mode="json")
        )

        for item in payload["agents"]:
            self.assertIsInstance(
                item["capabilities"],
                list,
            )

            for capability in (
                item["capabilities"]
            ):
                self.assertIsInstance(
                    capability,
                    str,
                )
                self.assertGreaterEqual(
                    len(capability),
                    1,
                )
                self.assertLessEqual(
                    len(capability),
                    MAX_AGENT_CAPABILITY_LENGTH,
                )

    def test_endpoint_does_not_dispatch(
        self,
    ):
        with patch.object(
            AgentRegistry,
            "dispatch",
            side_effect=AssertionError(
                "Catalog must not dispatch."
            ),
        ) as dispatch_mock:
            response = (
                agents_api.list_agents()
            )

        self.assertEqual(
            len(response.agents),
            5,
        )
        dispatch_mock.assert_not_called()

    def test_unexpected_failure_is_generic(
        self,
    ):
        with patch.object(
            agents_api,
            "build_default_agent_registry",
            side_effect=RuntimeError(
                "secret registry failure"
            ),
        ):
            with self.assertRaises(
                HTTPException
            ) as context:
                agents_api.list_agents()

        self.assertEqual(
            context.exception.status_code,
            500,
        )
        self.assertEqual(
            context.exception.detail,
            "Unable to load agents.",
        )
        self.assertNotIn(
            "secret",
            str(
                context.exception.detail
            ),
        )

    def test_api_module_has_no_external_integrations(
        self,
    ):
        source_path = Path(
            inspect.getsourcefile(
                agents_api
            )
        )
        source = source_path.read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)

        imports = set()

        for node in ast.walk(tree):
            if isinstance(
                node,
                ast.Import,
            ):
                imports.update(
                    alias.name
                    for alias in node.names
                )
            elif isinstance(
                node,
                ast.ImportFrom,
            ):
                imports.add(
                    node.module or ""
                )

        self.assertTrue(
            imports.issubset(
                {
                    "__future__",
                    "fastapi",
                    "app.agents.registry",
                    "app.models.agent",
                }
            )
        )

        forbidden_tokens = (
            "Brain",
            "Groq",
            "RAG",
            "requests",
            "httpx",
            "sqlite3",
            "sqlalchemy",
            "Path(",
            "open(",
            ".dispatch(",
        )

        for token in forbidden_tokens:
            self.assertNotIn(
                token,
                source,
            )

    def test_main_registers_route_once(
        self,
    ):
        schema = app.openapi()

        self.assertIn(
            "/agents",
            schema["paths"],
        )
        self.assertEqual(
            tuple(
                schema["paths"]["/agents"]
            ),
            (
                "get",
            ),
        )
        self.assertEqual(
            schema["paths"]["/agents"]
            ["get"]["operationId"],
            "list_agents",
        )

        with TestClient(app) as client:
            response = client.get(
                "/agents"
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            tuple(
                item["agent_id"]
                for item in (
                    response.json()["agents"]
                )
            ),
            EXPECTED_AGENT_IDS,
        )

    def test_openapi_contract_is_safe(
        self,
    ):
        schema = app.openapi()
        operation = (
            schema["paths"]
            ["/agents"]
            ["get"]
        )

        self.assertEqual(
            operation["operationId"],
            "list_agents",
        )
        self.assertEqual(
            operation["responses"]
            ["200"]
            ["content"]
            ["application/json"]
            ["schema"]
            ["$ref"],
            (
                "#/components/schemas/"
                "AgentCatalogResponse"
            ),
        )

        components = (
            schema["components"]["schemas"]
        )
        item_schema = components[
            "AgentCatalogItem"
        ]
        response_schema = components[
            "AgentCatalogResponse"
        ]

        self.assertEqual(
            set(
                item_schema["properties"]
            ),
            SAFE_AGENT_KEYS,
        )
        self.assertEqual(
            set(
                response_schema[
                    "properties"
                ]
            ),
            {
                "agents",
            },
        )

    def test_openapi_has_no_duplicate_operation_ids(
        self,
    ):
        schema = app.openapi()
        seen = set()

        for path_item in (
            schema["paths"].values()
        ):
            for operation in (
                path_item.values()
            ):
                if not isinstance(
                    operation,
                    dict,
                ):
                    continue

                operation_id = (
                    operation.get(
                        "operationId"
                    )
                )

                if not operation_id:
                    continue

                self.assertNotIn(
                    operation_id,
                    seen,
                )
                seen.add(operation_id)

    def test_catalog_has_no_selection_metadata(
        self,
    ):
        payload = (
            agents_api
            .list_agents()
            .model_dump(mode="json")
        )

        forbidden_keys = {
            "selected",
            "is_default",
            "default",
            "used_default",
            "handler",
            "prompt",
            "provider",
            "module",
        }

        for item in payload["agents"]:
            self.assertTrue(
                forbidden_keys.isdisjoint(
                    item
                )
            )


if __name__ == "__main__":
    unittest.main()
