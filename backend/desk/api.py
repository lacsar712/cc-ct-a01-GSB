from datetime import datetime
from typing import Optional

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from desk.auth_utils import bearer_auth, create_access_token, verify_password
from desk.models import OffsetSubmission, Tool, User

api = NinjaAPI(title="数控刀补复核台", version="1.1")


class HealthOut(Schema):
    status: str


class LoginIn(Schema):
    username: str
    password: str


class LoginOut(Schema):
    token: str
    username: str
    role: str
    can_write: bool


class ToolIn(Schema):
    tool_code: str
    usable: bool = True


class DelistIn(Schema):
    reason: str


class ToolOut(Schema):
    id: int
    tool_code: str
    usable: bool
    delisted: bool
    delist_reason: str
    delisted_by: Optional[str]
    delisted_at: Optional[datetime]
    registered_by: Optional[str]
    created_at: datetime


class SubmissionIn(Schema):
    # 只能点选清册里的刀；空选由校验整笔退回
    tool_id: Optional[int] = None
    offset_um: int


class SubmissionOut(Schema):
    id: int
    tool_id: Optional[int]
    tool_code: str
    offset_um: int
    status: str
    verdict: str
    created_at: datetime
    reviewed_at: Optional[datetime]
    # 清册现状（仅展示用；单据刀号 tool_code 是锁死快照，不随后续摘牌变化）
    tool_delisted: bool = False
    tool_delist_reason: str = ""


def _require_writer(user: User) -> None:
    if not user.can_write:
        raise HttpError(403, "当前账号只读，不能操作清册或交刀补")


def _tool_out(row: Tool) -> ToolOut:
    return ToolOut(
        id=row.id,
        tool_code=row.tool_code,
        usable=row.usable,
        delisted=row.delisted,
        delist_reason=row.delist_reason,
        delisted_by=row.delisted_by.username if row.delisted_by_id else None,
        delisted_at=row.delisted_at,
        registered_by=row.registered_by.username if row.registered_by_id else None,
        created_at=row.created_at,
    )


def _to_out(row: OffsetSubmission) -> SubmissionOut:
    tool = getattr(row, "tool", None)
    return SubmissionOut(
        id=row.id,
        tool_id=row.tool_id,
        tool_code=row.tool_code,
        offset_um=row.offset_um,
        status=row.status,
        verdict=row.verdict or "",
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
        tool_delisted=bool(tool and tool.delisted),
        tool_delist_reason=(tool.delist_reason if tool else ""),
    )


@api.get("/health", response=HealthOut)
def health(request: HttpRequest):
    return {"status": "ok"}


@api.post("/auth/login", response=LoginOut)
def login(request: HttpRequest, body: LoginIn):
    try:
        user = User.objects.get(username=body.username)
    except User.DoesNotExist:
        raise HttpError(401, "用户名或密码错误")
    if not verify_password(body.password, user.password):
        raise HttpError(401, "用户名或密码错误")
    token = create_access_token(user)
    return {
        "token": token,
        "username": user.username,
        "role": user.role,
        "can_write": user.can_write,
    }


@api.get("/tools", response=list[ToolOut], auth=bearer_auth)
def list_tools(request: HttpRequest):
    rows = Tool.objects.select_related("registered_by", "delisted_by").all()
    return [_tool_out(r) for r in rows]


@api.post("/tools", response=ToolOut, auth=bearer_auth)
def register_tool(request: HttpRequest, body: ToolIn):
    user: User = request.auth
    _require_writer(user)
    tool_code = body.tool_code.strip()
    if not tool_code:
        raise HttpError(400, "刀号不能为空")
    if Tool.objects.filter(tool_code=tool_code).exists():
        raise HttpError(400, f"刀号 {tool_code} 已在清册中")
    row = Tool.objects.create(
        tool_code=tool_code,
        usable=body.usable,
        registered_by=user,
    )
    return _tool_out(row)


@api.post("/tools/{tool_id}/delist", response=ToolOut, auth=bearer_auth)
def delist_tool(request: HttpRequest, tool_id: int, body: DelistIn):
    user: User = request.auth
    _require_writer(user)
    reason = body.reason.strip()
    if not reason:
        raise HttpError(400, "摘牌必须写明原因")
    try:
        row = Tool.objects.select_for_update().get(pk=tool_id)
    except Tool.DoesNotExist:
        raise HttpError(404, "清册中没有这把刀")
    if row.delisted:
        raise HttpError(400, f"刀号 {row.tool_code} 已摘牌，不能重复摘牌")
    row.delisted = True
    row.usable = False
    row.delist_reason = reason
    row.delisted_by = user
    row.delisted_at = timezone.now()
    row.save(
        update_fields=[
            "delisted",
            "usable",
            "delist_reason",
            "delisted_by",
            "delisted_at",
        ]
    )
    return _tool_out(row)


@api.get("/submissions", response=list[SubmissionOut], auth=bearer_auth)
def list_submissions(request: HttpRequest):
    rows = OffsetSubmission.objects.select_related("tool").all()[:200]
    return [_to_out(r) for r in rows]


@api.get("/submissions/{submission_id}", response=SubmissionOut, auth=bearer_auth)
def get_submission(request: HttpRequest, submission_id: int):
    try:
        row = OffsetSubmission.objects.select_related("tool").get(pk=submission_id)
    except OffsetSubmission.DoesNotExist:
        raise HttpError(404, "刀补记录不存在")
    return _to_out(row)


@api.post("/submissions", response=SubmissionOut, auth=bearer_auth)
def create_submission(request: HttpRequest, body: SubmissionIn):
    user: User = request.auth
    _require_writer(user)

    # 空选：未从清册点任何刀，整笔退回
    if not body.tool_id:
        raise HttpError(400, "未从清册点选刀号，整笔退回")

    try:
        with transaction.atomic():
            # 行锁防并发：校验通过到落单之间被摘牌，也会整笔退回
            tool = Tool.objects.select_for_update().get(pk=body.tool_id)
            if tool.delisted:
                reason = f"：{tool.delist_reason}" if tool.delist_reason else ""
                raise HttpError(
                    400,
                    f"刀号 {tool.tool_code} 已摘牌{reason}，整笔退回",
                )
            if not tool.usable:
                raise HttpError(
                    400,
                    f"刀号 {tool.tool_code} 当前未勾可投，整笔退回",
                )
            row = OffsetSubmission.objects.create(
                tool=tool,
                tool_code=tool.tool_code,  # 刀号写入单据即锁死快照
                offset_um=body.offset_um,
                submitted_by=user,
                status=OffsetSubmission.Status.PENDING,
            )
    except Tool.DoesNotExist:
        raise HttpError(400, "点选的刀号不在清册中，整笔退回")
    return _to_out(row)
