from contextlib import asynccontextmanager

from app.config.document_recovery_monitoring import (
    load_document_recovery_monitoring_settings,
    validate_document_recovery_monitoring_settings,
)

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
from app.services.rag_runtime import initialize_rag_runtime
from app.services.document_recovery_runtime import run_document_recovery_startup


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
    document_recovery_settings=None,
    document_recovery_runner=None,
    document_recovery_rag=None,
    document_recovery_monitoring_settings=None,
):
    merge_settings = (
        branch_merge_settings
        if branch_merge_settings is not None
        else load_branch_merge_settings()
    )
    validate_branch_merge_settings(
        merge_settings
    )

    recovery_monitoring_settings = (
        document_recovery_monitoring_settings
        if document_recovery_monitoring_settings is not None
        else load_document_recovery_monitoring_settings()
    )

    validate_document_recovery_monitoring_settings(
        recovery_monitoring_settings
    )

    document_storage = (
        get_document_storage()
    )

    rag_runtime = (
        initialize_rag_runtime()
    )

    resolved_recovery_runner = (
        document_recovery_runner
        if document_recovery_runner is not None
        else run_document_recovery_startup
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        from app.api.documents import (
            rag as default_document_recovery_rag,
        )

        resolved_recovery_rag = (
            document_recovery_rag
            if document_recovery_rag is not None
            else default_document_recovery_rag
        )

        report = resolved_recovery_runner(
            rag=resolved_recovery_rag,
            settings=document_recovery_settings,
        )

        application.state.document_recovery_report = (
            report
        )

        yield

    application = FastAPI(
        title="Onkar AI",
        lifespan=lifespan,
    )
    application.state.document_storage = (
        document_storage
    )

    application.state.rag_runtime = (
        rag_runtime
    )

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
    application.head(
        "/",
        operation_id="root_head",
        include_in_schema=False,
    )(root)

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

    application.state.document_recovery_report = None

    if recovery_monitoring_settings.enabled:
        from app.api.document_recovery_admin import (
            create_document_recovery_admin_router,
        )

        recovery_admin_router = (
            create_document_recovery_admin_router(
                recovery_monitoring_settings
            )
        )

        application.include_router(
            recovery_admin_router
        )

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
