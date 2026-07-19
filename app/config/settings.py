from pathlib import Path
from dataclasses import dataclass
import ipaddress
import os
import re
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

BASE_DIR = Path(__file__).resolve().parent.parent.parent

APP_DIR = BASE_DIR / "app"

DATABASE_DIR = APP_DIR / "database"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

CHAT_DB = DATABASE_DIR / "chat_history.db"
MEMORY_DB = DATABASE_DIR / "memory.db"

STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR = STORAGE_DIR / "uploads"
VECTOR_DB_DIR = STORAGE_DIR / "vector_db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

PDF_STORAGE_DIR = STORAGE_DIR / "pdfs"
PDF_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

VECTOR_DB_DIR = STORAGE_DIR / "vector_db"
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

PDF_CONTEXT_FILE = STORAGE_DIR / "pdf_context.txt"


class BranchMergeConfigurationError(RuntimeError):
    """Fail-closed configuration error without secret-bearing details."""

    def __init__(self):
        super().__init__(
            "Branch merge security configuration is invalid."
        )


@dataclass(frozen=True)
class BranchMergeSettings:
    enabled: bool
    token_sha256: str
    allowed_origins: tuple[str, ...]
    max_body_bytes: int
    rate_per_minute: int
    rate_per_hour: int


_LOWERCASE_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ORIGIN_HOST_LABEL_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


def _parse_branch_merge_bool(value):
    normalized = str(value).strip().casefold()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"", "0", "false", "no", "off"}:
        return False

    raise BranchMergeConfigurationError()


def _parse_positive_setting(value):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise BranchMergeConfigurationError() from error

    if parsed <= 0:
        raise BranchMergeConfigurationError()

    return parsed


def _normalize_branch_merge_origin(value):
    candidate = str(value).strip()

    if (
        not candidate
        or "*" in candidate
        or not candidate.isascii()
        or any(character.isspace() for character in candidate)
    ):
        raise BranchMergeConfigurationError()

    try:
        parsed = urlsplit(candidate)
        parsed_port = parsed.port
    except ValueError as error:
        raise BranchMergeConfigurationError() from error

    hostname = parsed.hostname

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or hostname.casefold() == "null"
    ):
        raise BranchMergeConfigurationError()

    if parsed_port is not None and not (1 <= parsed_port <= 65535):
        raise BranchMergeConfigurationError()

    try:
        parsed_ip = ipaddress.ip_address(hostname)
    except ValueError:
        labels = hostname.split(".")

        if (
            len(hostname) > 253
            or any(
                _ORIGIN_HOST_LABEL_PATTERN.fullmatch(label)
                is None
                for label in labels
            )
        ):
            raise BranchMergeConfigurationError()

        expected_host = hostname
    else:
        expected_host = (
            f"[{hostname}]"
            if parsed_ip.version == 6
            else hostname
        )

    expected_netloc = expected_host

    if parsed_port is not None:
        expected_netloc += f":{parsed_port}"

    if parsed.netloc.casefold() != expected_netloc.casefold():
        raise BranchMergeConfigurationError()

    return candidate[:-1] if candidate.endswith("/") else candidate


def load_branch_merge_settings(environ=None):
    """Load branch-merge controls, validating enabled mode fail-closed."""
    source = os.environ if environ is None else environ
    enabled = _parse_branch_merge_bool(
        source.get("BRANCH_MERGE_ENABLED", "false")
    )
    token_sha256 = str(
        source.get("BRANCH_MERGE_TOKEN_SHA256", "")
    ).strip()
    raw_origins = str(
        source.get("BRANCH_MERGE_ALLOWED_ORIGINS", "")
    )
    allowed_origins = tuple(
        dict.fromkeys(
            _normalize_branch_merge_origin(origin)
            for origin in raw_origins.split(",")
            if origin.strip()
        )
    )
    max_body_bytes = _parse_positive_setting(
        source.get(
            "BRANCH_MERGE_MAX_BODY_BYTES",
            "1048576",
        )
    )
    rate_per_minute = _parse_positive_setting(
        source.get(
            "BRANCH_MERGE_RATE_PER_MINUTE",
            "5",
        )
    )
    rate_per_hour = _parse_positive_setting(
        source.get(
            "BRANCH_MERGE_RATE_PER_HOUR",
            "20",
        )
    )

    settings = BranchMergeSettings(
        enabled=enabled,
        token_sha256=token_sha256,
        allowed_origins=allowed_origins,
        max_body_bytes=max_body_bytes,
        rate_per_minute=rate_per_minute,
        rate_per_hour=rate_per_hour,
    )
    validate_branch_merge_settings(settings)
    return settings


def validate_branch_merge_settings(settings):
    if (
        settings.max_body_bytes <= 0
        or settings.rate_per_minute <= 0
        or settings.rate_per_hour <= 0
    ):
        raise BranchMergeConfigurationError()

    if settings.enabled:
        if (
            _LOWERCASE_SHA256_PATTERN.fullmatch(
                settings.token_sha256
            )
            is None
            or not settings.allowed_origins
        ):
            raise BranchMergeConfigurationError()

        normalized_origins = tuple(
            _normalize_branch_merge_origin(origin)
            for origin in settings.allowed_origins
        )

        if normalized_origins != tuple(
            settings.allowed_origins
        ):
            raise BranchMergeConfigurationError()

    return settings
