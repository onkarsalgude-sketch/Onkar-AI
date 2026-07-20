from fastapi import FastAPI
from fastapi.middleware.cors import (
    CORSMiddleware,
)

from app.config.settings import (
    CHAT_DB,
    load_branch_merge_settings,
    validate_branch_merge_settings,
)
from app.services.document_object_service import get_document_storage


def root():
    return {
        "message": "Onkar AI is running 🚀",
    }


def create_app(
    *,
    branch_merge_settings=None,
    branch_merge_db_path=None,
    branch_merge_executor=None,
    branch_merge_rate_limiter=None,
):
    merge_settings = (
        branch_merge_settings
        if branch_merge_settings is not None
        else load_branch_merge_settings()
    )
    validate_branch_merge_settings(
        merge_settings
    )

    application = FastAPI(title="Onkar AI")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://onkar-ai.vercel.app",
        ],
        allow_origin_regex=(
            r"^https?://"
            r"(localhost|127\.0\.0\.1):"
            r"\d+$"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Sources",
            "X-Chat-Id",
            "X-Model-Id",
        ],
    )

    application.get("/")(root)

    from app.api.backups import (
        router as backups_router,
    )
    from app.api.chat import router as chat_router
    from app.api.documents import (
        router as documents_router,
    )
    from app.api.image import router as image_router

    application.include_router(chat_router)
    application.include_router(documents_router)
    application.include_router(image_router)
    application.include_router(backups_router)

    if merge_settings.enabled:
        from app.api.branch_merge import (
            create_branch_merge_router,
        )

        router_arguments = {}

        if branch_merge_executor is not None:
            router_arguments["executor"] = (
                branch_merge_executor
            )

        if branch_merge_rate_limiter is not None:
            router_arguments["rate_limiter"] = (
                branch_merge_rate_limiter
            )

        merge_router = create_branch_merge_router(
            merge_settings,
            str(
                branch_merge_db_path
                if branch_merge_db_path is not None
                else CHAT_DB
            ),
            **router_arguments,
        )
        application.include_router(merge_router)

    return application


app = create_app()
