import unittest
from unittest.mock import (
    Mock,
    patch,
)

from app.main import create_app


class DocumentStorageStartupTests(
    unittest.TestCase
):
    def test_storage_is_validated_and_attached(
        self,
    ):
        storage = Mock(
            name="document-storage"
        )

        with patch(
            "app.main.get_document_storage",
            return_value=storage,
        ) as get_storage:
            application = create_app()

        get_storage.assert_called_once_with()

        self.assertIs(
            application.state.document_storage,
            storage,
        )

    def test_storage_failure_stops_app_creation(
        self,
    ):
        with patch(
            "app.main.get_document_storage",
            side_effect=RuntimeError(
                "storage unavailable"
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "storage unavailable",
            ):
                create_app()


if __name__ == "__main__":
    unittest.main()
