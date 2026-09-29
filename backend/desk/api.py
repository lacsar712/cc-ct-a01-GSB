from datetime import datetime
from typing import Optional

from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from desk.auth_utils import bearer_auth, create_access_token, verify_password
from desk.models import OffsetSubmission, RosterEvent, RosterTool, User
from desk import services

api = NinjaAPI(title="数控刀补复核台", version="1.0")


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


# ---------- 清册 ----------


class RegisterIn(Schema):
    tool_code: str
    investable: bool = True


class ToolOut(Schema):
    id: int
    tool_code: str
    state: str
    state_label: str
    registered_at: Optional[datetime]
    delisted_at: Optional[datetime]
    registered_by: Optional[str]


class EventOut(Schema):
    id: int
    tool_id: int
    tool_code: str
    action: str
    action_label: str
    actor: Optional[str]
    created_at: datetime


# ---------- 刀补单据 ----------


class SubmissionIn(Schema):
    # 只能从「仍可投」的刀里点选；不传/为空选 → 整笔退回
    roster_tool_id: Optional[int] = None
    offset_um: int


class SubmissionOut(Schema):
    id: int
    tool_code: str
    roster_tool_id: Optional[int]
    offset_um: int
    status: str
    verdict: str
    return_reason: str
    created_at: datetime
    reviewed_at: Optional[datetime]


def _require_write(user: User) -> None:
    if not user.can_write:
        raise HttpError(403, "当前账号只读，不能改清册或交刀补")


def _tool_out(tool: RosterTool) -> ToolOut:
    return ToolOut(
        id=tool.id,
        tool_code=tool.tool_code,
        state=tool.state,
        state_label=tool.get_state_display(),
        registered_at=tool.registered_at,
        delisted_at=tool.delisted_at,
        registered_by=tool.registered_by.username if tool.registered_by else None,
    )


def _event_out(ev: RosterEvent) -> EventOut:
    return EventOut(
        id=ev.id,
        tool_id=ev.tool_id,
        tool_code=ev.tool_code,
        action=ev.action,
        action_label=ev.get_action_display(),
        actor=ev.actor.username if ev.actor else None,
        created_at=ev.created_at,
    )


def _to_out(row: OffsetSubmission) -> SubmissionOut:
    return SubmissionOut(
        id=row.id,
        tool_code=row.tool_code,
        roster_tool_id=row.roster_tool_id,
        offset_um=row.offset_um,
        status=row.status,
        verdict=row.verdict or "",
        return_reason=row.return_reason or "",
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
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


# ---------- 清册接口 ----------


@api.get("/roster/tools", response=list[ToolOut], auth=bearer_auth)
def list_tools(request: HttpRequest):
    # 操作员、复核员均可翻阅清册
    return [_tool_out(t) for t in RosterTool.objects.select_related("registered_by")]


@api.get("/roster/events", response=list[EventOut], auth=bearer_auth)
def list_events(request: HttpRequest):
    # 摘牌/登记痕迹对两角色可见
    return [
        _event_out(ev)
        for ev in RosterEvent.objects.select_related("actor", "tool")[:200]
    ]


@api.post("/roster/tools", response=ToolOut, auth=bearer_auth)
def register_tool(request: HttpRequest, body: RegisterIn):
    user: User = request.auth
    _require_write(user)
    try:
        tool = services.register_tool(body.tool_code, user, body.investable)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return _tool_out(tool)


@api.post("/roster/tools/{tool_id}/delist", response=ToolOut, auth=bearer_auth)
def delist_tool(request: HttpRequest, tool_id: int):
    user: User = request.auth
    _require_write(user)
    try:
        tool = RosterTool.objects.get(pk=tool_id)
    except RosterTool.DoesNotExist:
        raise HttpError(404, "清册中没有这把刀")
    try:
        tool = services.delist_tool(tool, user)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return _tool_out(tool)


@api.post("/roster/tools/{tool_id}/relist", response=ToolOut, auth=bearer_auth)
def relist_tool(request: HttpRequest, tool_id: int):
    user: User = request.auth
    _require_write(user)
    try:
        tool = RosterTool.objects.get(pk=tool_id)
    except RosterTool.DoesNotExist:
        raise HttpError(404, "清册中没有这把刀")
    try:
        tool = services.relist_tool(tool, user)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return _tool_out(tool)


# ---------- 刀补单据接口 ----------


@api.get("/submissions", response=list[SubmissionOut], auth=bearer_auth)
def list_submissions(request: HttpRequest):
    rows = OffsetSubmission.objects.all()[:200]
    return [_to_out(r) for r in rows]


@api.get("/submissions/{submission_id}", response=SubmissionOut, auth=bearer_auth)
def get_submission(request: HttpRequest, submission_id: int):
    try:
        row = OffsetSubmission.objects.get(pk=submission_id)
    except OffsetSubmission.DoesNotExist:
        raise HttpError(404, "刀补记录不存在")
    return _to_out(row)


@api.post("/submissions", response=SubmissionOut, auth=bearer_auth)
def create_submission(request: HttpRequest, body: SubmissionIn):
    user: User = request.auth
    _require_write(user)
    # 刀号只能从仍可投的刀里点选；不合规由服务层整笔退回并写明原因
    row = services.submit_offset(user, body.roster_tool_id, body.offset_um)
    return _to_out(row)
