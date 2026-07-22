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
from app.services.document_recovery_history_runtime import (
    run_document_recovery_startup_with_history as run_document_recovery_startup,
)
from app.config.system_health_monitoring import (
    load_system_health_monitoring_settings,
    validate_system_health_monitoring_settings,
)


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
    system_health_monitoring_settings=None,
    system_health_definitions_provider=None,
    system_incident_recorder=None,
    system_incident_db_path=None,
    system_incident_alerting_settings=None,
    system_incident_alert_deliverer=None,
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

    system_health_settings = (
        system_health_monitoring_settings
        if system_health_monitoring_settings is not None
        else load_system_health_monitoring_settings()
    )

    validate_system_health_monitoring_settings(
        system_health_settings
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
        from app.api.document_recovery_history_admin import (
            create_document_recovery_history_admin_router,
        )

        recovery_admin_router = (
            create_document_recovery_admin_router(
                recovery_monitoring_settings
            )
        )

        recovery_history_admin_router = (
            create_document_recovery_history_admin_router(
                recovery_monitoring_settings
            )
        )

        application.include_router(
            recovery_admin_router
        )

        application.include_router(
            recovery_history_admin_router
        )

    if system_health_settings.enabled:
        from app.api.system_health_admin import (
            create_system_health_admin_router,
        )
        from app.services.system_health_checks import (
            build_default_health_check_definitions,
        )
        from app.config.system_incident_alerting import (
            load_system_incident_alerting_settings,
            validate_system_incident_alerting_settings,
        )
        from app.services.system_incident_alert_service import (
            deliver_system_incident_alerts,
        )

        def default_system_health_definitions_provider(
            request,
        ):
            return build_default_health_check_definitions(
                recovery_report_provider=lambda: getattr(
                    request.app.state,
                    "document_recovery_report",
                    None,
                )
            )

        resolved_system_health_definitions_provider = (
            system_health_definitions_provider
            if system_health_definitions_provider is not None
            else default_system_health_definitions_provider
        )

        from app.services.system_incident_history_service import (
            record_system_incident_evaluation,
        )

        resolved_system_incident_recorder = (
            system_incident_recorder
            if system_incident_recorder is not None
            else record_system_incident_evaluation
        )

        resolved_system_incident_db_path = str(
            system_incident_db_path
            if system_incident_db_path is not None
            else CHAT_DB
        )

        resolved_system_incident_alerting_settings = (
            system_incident_alerting_settings
            if system_incident_alerting_settings is not None
            else load_system_incident_alerting_settings()
        )

        validate_system_incident_alerting_settings(
            resolved_system_incident_alerting_settings
        )

        resolved_system_incident_alert_deliverer = (
            system_incident_alert_deliverer
            if system_incident_alert_deliverer is not None
            else deliver_system_incident_alerts
        )

        system_health_router = (
            create_system_health_admin_router(
                system_health_settings,
                definitions_provider=(
                    resolved_system_health_definitions_provider
                ),
                incident_recorder=(
                    resolved_system_incident_recorder
                ),
                incident_db_path=(
                    resolved_system_incident_db_path
                ),
                incident_alert_settings=(
                    resolved_system_incident_alerting_settings
                ),
                incident_alert_deliverer=(
                    resolved_system_incident_alert_deliverer
                ),
            )
        )

        application.include_router(
            system_health_router
        )

        from app.api.system_incident_admin import (
            create_system_incident_admin_router,
        )

        system_incident_router = (
            create_system_incident_admin_router(
                system_health_settings
            )
        )

        application.include_router(
            system_incident_router
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
