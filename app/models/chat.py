from datetime import datetime
from typing import (
    Annotated,
    Literal,
    Optional,
)
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[int] = None
    model_id: Optional[str] = None


class Source(BaseModel):
    type: Optional[str] = None
    title: str
    url: Optional[str] = None
    filename: Optional[str] = None
    page: Optional[int] = None
    chat_id: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[Source] = Field(
        default_factory=list
    )


# -------------------------
# Chat backup import models
# -------------------------

class ChatBackupSource(BaseModel):
    type: Optional[str] = Field(
        default=None,
        max_length=50,
    )

    title: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    url: Optional[str] = Field(
        default=None,
        max_length=4000,
    )

    filename: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    page: Optional[int] = Field(
        default=None,
        ge=1,
    )

    chat_id: Optional[int] = None

    domain: Optional[str] = Field(
        default=None,
        max_length=255,
    )


class ChatBackupAttachment(BaseModel):
    filename: str = Field(
        min_length=1,
        max_length=255,
    )

    type: Optional[str] = Field(
        default=None,
        max_length=50,
    )

    size: Optional[str] = Field(
        default=None,
        max_length=100,
    )


class ChatBackupMessage(BaseModel):
    index: Optional[int] = Field(
        default=None,
        ge=1,
    )

    role: Literal[
        "user",
        "assistant",
    ]

    content: str = Field(
        default="",
        max_length=200000,
    )

    model_id: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    created_at: Optional[datetime] = None

    attachment: Optional[
        ChatBackupAttachment
    ] = None

    sources: list[
        ChatBackupSource
    ] = Field(
        default_factory=list,
        max_length=100,
    )


class ChatBackupChatMetadata(BaseModel):
    id: Optional[int] = None

    title: str = Field(
        default="Imported Chat",
        max_length=200,
    )

    created_at: Optional[datetime] = None

    is_pinned: bool = False

    # Accepted for schema compatibility,
    # but import logic must not reuse an old folder ID.
    folder_id: Optional[int] = None

    folder_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )


class ChatBackupModelMetadata(BaseModel):
    selected_id: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    selected_name: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    default_id: Optional[str] = Field(
        default=None,
        max_length=255,
    )


class ChatBackupImportRequest(BaseModel):
    schema_version: int = Field(
        ge=1,
        le=1,
    )

    application: str = Field(
        default="Onkar AI",
        max_length=100,
    )

    exported_at: Optional[datetime] = None

    chat: ChatBackupChatMetadata

    model: Optional[
        ChatBackupModelMetadata
    ] = None

    messages: list[
        ChatBackupMessage
    ] = Field(
        min_length=1,
        max_length=1000,
    )


class ChatBackupImportResponse(BaseModel):
    chat_id: int
    title: str
    message_count: int

    warnings: list[str] = Field(
        default_factory=list
    )
    # -------------------------
# Message action models
# -------------------------

class MessageEditRequest(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=200000,
    )

    @field_validator("content")
    @classmethod
    def validate_content(
        cls,
        value: str,
    ) -> str:
        cleaned_content = value.strip()

        if not cleaned_content:
            raise ValueError(
                "Message content cannot be empty."
            )

        return cleaned_content


class MessageRegenerateRequest(BaseModel):
    model_id: Optional[str] = Field(
        default=None,
        max_length=255,
    )


class MessageEditResponse(BaseModel):
    message: str
    chat_id: int
    message_id: int
    content: str
    deleted_following_messages: int = 0


class MessageDeleteResponse(BaseModel):
    message: str
    chat_id: int
    message_id: int
    role: Literal[
        "user",
        "assistant",
    ]

    # -------------------------
# Message bookmark models
# -------------------------

class MessageBookmarkRequest(BaseModel):
    note: str = Field(
        default="",
        max_length=1000,
    )

    @field_validator("note")
    @classmethod
    def clean_note(
        cls,
        value: str,
    ) -> str:
        return str(
            value or ""
        ).strip()


class MessageBookmarkResponse(BaseModel):
    message: str
    bookmark_id: int
    chat_id: int
    message_id: int
    role: Literal[
        "user",
        "assistant",
    ]
    content: str
    message_created_at: str
    note: str = ""
    created_at: str
    updated_at: str


class MessageBookmarkDeleteResponse(
    BaseModel
):
    message: str
    chat_id: int
    message_id: int

    # -------------------------
# Conversation branch models
# -------------------------

class ChatBranchRequest(BaseModel):
    title: Optional[str] = Field(
        default=None,
        max_length=200,
    )

    @field_validator("title")
    @classmethod
    def clean_title(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        cleaned_title = value.strip()

        return cleaned_title or None


class ChatBranchResponse(BaseModel):
    message: str
    chat_id: int
    title: str
    parent_chat_id: int
    parent_chat_title: str
    branched_from_message_id: int
    branch_message_id: int

    branched_from_message_role: Literal[
        "user"
    ]

    branched_from_message_content: str
    copied_message_count: int = 0
    folder_id: Optional[int] = None
    created_at: str


# -------------------------
# Branch comparison models
# -------------------------

class ChatComparisonMessage(BaseModel):
    id: int
    role: Literal[
        "user",
        "assistant",
        "system",
    ]
    content: str
    created_at: str
    has_attachment_metadata: bool = False
    has_source_metadata: bool = False


class ChatComparisonChatSummary(BaseModel):
    id: int
    title: str


class ChatComparisonCounts(BaseModel):
    common: int
    parent_only: int
    branch_only: int


class BranchMergePreviewTurn(BaseModel):
    turn_key: str
    type: Literal[
        "source",
        "turn",
        "locked",
    ]
    selectable: bool
    anchor_message_id: Optional[int] = None
    message_ids: list[int] = Field(
        default_factory=list
    )
    reason: Optional[str] = None


class BranchMergePreviewSnapshot(BaseModel):
    version: int
    preview_token: str
    expected_parent_last_message_id: int
    expected_branch_last_message_id: int
    turns: list[
        BranchMergePreviewTurn
    ] = Field(default_factory=list)


class ChatCompareParentResponse(BaseModel):
    comparable: bool
    reason: Optional[str] = None
    parent_chat: Optional[
        ChatComparisonChatSummary
    ] = None
    branch_chat: ChatComparisonChatSummary
    branched_from_message_id: Optional[
        int
    ] = None
    branch_message_id: Optional[int] = None
    parent_source_message: Optional[
        ChatComparisonMessage
    ] = None
    branch_source_message: Optional[
        ChatComparisonMessage
    ] = None
    common_messages: list[
        ChatComparisonMessage
    ] = Field(default_factory=list)
    parent_only_messages: list[
        ChatComparisonMessage
    ] = Field(default_factory=list)
    branch_only_messages: list[
        ChatComparisonMessage
    ] = Field(default_factory=list)
    counts: Optional[
        ChatComparisonCounts
    ] = None
    merge_preview: Optional[
        BranchMergePreviewSnapshot
    ] = None


# -------------------------
# Internal branch merge models
# -------------------------

StrictPositiveInt = Annotated[
    int,
    Field(strict=True, gt=0),
]

StrictNonnegativeInt = Annotated[
    int,
    Field(strict=True, ge=0),
]


class StrictBranchMergeModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class BranchMergeExpectedState(
    StrictBranchMergeModel
):
    parent_chat_id: StrictPositiveInt
    branched_from_message_id: StrictPositiveInt
    branch_message_id: StrictPositiveInt
    parent_last_message_id: StrictPositiveInt
    branch_last_message_id: StrictPositiveInt


class BranchMergeSelectedTurn(
    StrictBranchMergeModel
):
    turn_key: str = Field(
        min_length=1,
        max_length=200,
    )
    message_ids: list[
        StrictPositiveInt
    ] = Field(
        default_factory=list,
        max_length=20_000,
    )

    @field_validator("turn_key")
    @classmethod
    def validate_turn_key(cls, value: str):
        if value != value.strip():
            raise ValueError(
                "Turn key must not contain leading or trailing whitespace."
            )

        return value


class BranchMergeRequest(
    StrictBranchMergeModel
):
    idempotency_key: str = Field(
        min_length=1,
        max_length=64,
    )
    preview_token: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    expected: BranchMergeExpectedState
    selected_turns: list[
        BranchMergeSelectedTurn
    ] = Field(max_length=5_000)

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(
        cls,
        value: str,
    ):
        if value != value.strip():
            raise ValueError(
                "Idempotency key must not contain whitespace."
            )

        try:
            UUID(value)
        except (ValueError, AttributeError) as error:
            raise ValueError(
                "Idempotency key must be a valid UUID string."
            ) from error

        return value

    @model_validator(mode="after")
    def validate_total_message_limit(self):
        total_message_count = sum(
            len(turn.message_ids)
            for turn in self.selected_turns
        )

        if total_message_count > 20_000:
            raise ValueError(
                "A merge request may select at most 20,000 messages."
            )

        return self


class BranchMergeTurnResult(
    StrictBranchMergeModel
):
    turn_key: str = Field(
        min_length=1,
        max_length=200,
    )
    source_branch_message_ids: list[
        StrictPositiveInt
    ] = Field(default_factory=list)
    created_parent_message_ids: list[
        StrictPositiveInt
    ] = Field(default_factory=list)


class BranchMergeResponse(
    StrictBranchMergeModel
):
    status: Literal["completed"]
    replayed: bool
    operation_id: StrictPositiveInt
    idempotency_key: str
    branch_chat_id: StrictPositiveInt
    parent_chat_id: StrictPositiveInt
    inserted_turn_count: StrictNonnegativeInt
    inserted_message_count: StrictNonnegativeInt
    first_created_parent_message_id: Optional[
        StrictPositiveInt
    ] = None
    last_created_parent_message_id: Optional[
        StrictPositiveInt
    ] = None
    completed_at: str = Field(min_length=1)
    turns: list[
        BranchMergeTurnResult
    ] = Field(default_factory=list)


class BranchMergeErrorDetail(
    StrictBranchMergeModel
):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False
    refresh_preview: bool = False
    operation_id: Optional[
        StrictPositiveInt
    ] = None
