from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from desk.models import OffsetSubmission, RosterEvent, RosterTool


def evaluate_verdict(offset_um: int) -> str:
    if abs(offset_um) <= settings.OFFSET_TOLERANCE_UM:
        return OffsetSubmission.Verdict.PASS
    return OffsetSubmission.Verdict.FAIL


def apply_verdict(submission: OffsetSubmission) -> None:
    submission.verdict = evaluate_verdict(submission.offset_um)
    submission.status = OffsetSubmission.Status.DONE
    submission.reviewed_at = timezone.now()
    submission.save(
        update_fields=["verdict", "status", "reviewed_at"],
    )


def _log_event(tool: RosterTool, action: str, actor) -> RosterEvent:
    return RosterEvent.objects.create(
        tool=tool,
        tool_code=tool.tool_code,
        action=action,
        actor=actor,
    )


def register_tool(tool_code: str, actor, investable: bool = True) -> RosterTool:
    """把刀号登进清册；默认勾为可投，不勾则登记即摘牌。均留痕。"""
    tool_code = tool_code.strip()
    if not tool_code:
        raise ValueError("刀号不能为空")
    try:
        with transaction.atomic():
            tool = RosterTool.objects.create(
                tool_code=tool_code,
                state=(
                    RosterTool.State.INVESTABLE
                    if investable
                    else RosterTool.State.DELISTED
                ),
                registered_by=actor,
                delisted_at=None if investable else timezone.now(),
            )
            _log_event(tool, RosterEvent.Action.REGISTERED, actor)
            if not investable:
                _log_event(tool, RosterEvent.Action.DELISTED, actor)
    except IntegrityError:
        existing = RosterTool.objects.filter(tool_code=tool_code).first()
        if existing and existing.state == RosterTool.State.DELISTED:
            raise ValueError(f"刀号 {tool_code} 已摘牌，可在清册台重新勾可投")
        raise ValueError(f"刀号 {tool_code} 已在清册中")
    return tool


def delist_tool(tool: RosterTool, actor) -> RosterTool:
    """摘牌：可投 -> 已摘牌，留摘牌痕迹。不影响已写入单据的锁死刀号。"""
    with transaction.atomic():
        locked = RosterTool.objects.select_for_update().get(pk=tool.pk)
        if locked.state == RosterTool.State.DELISTED:
            raise ValueError(f"刀号 {locked.tool_code} 已摘牌，无需重复摘牌")
        locked.state = RosterTool.State.DELISTED
        locked.delisted_at = timezone.now()
        locked.save(update_fields=["state", "delisted_at"])
        _log_event(locked, RosterEvent.Action.DELISTED, actor)
    return locked


def relist_tool(tool: RosterTool, actor) -> RosterTool:
    """重新勾可投：已摘牌 -> 可投，留勾可投痕迹。"""
    with transaction.atomic():
        locked = RosterTool.objects.select_for_update().get(pk=tool.pk)
        if locked.state == RosterTool.State.INVESTABLE:
            raise ValueError(f"刀号 {locked.tool_code} 当前已可投")
        locked.state = RosterTool.State.INVESTABLE
        locked.delisted_at = None
        locked.save(update_fields=["state", "delisted_at"])
        _log_event(locked, RosterEvent.Action.RELISTED, actor)
    return locked


def _returned(actor, offset_um: int, reason: str, *, tool_code: str = "", tool=None):
    return OffsetSubmission.objects.create(
        tool_code=tool_code,
        roster_tool=tool,
        offset_um=offset_um,
        submitted_by=actor,
        status=OffsetSubmission.Status.RETURNED,
        return_reason=reason,
    )


def submit_offset(actor, roster_tool_id, offset_um: int) -> OffsetSubmission:
    """
    交刀补：刀号只能从「仍可投」的刀里点选。
    空选 / 刀不在册 / 已摘牌 —— 整笔退回并写明原因；
    命中可投刀 —— 进待复核，并把刀号快照锁死进单据。
    """
    if roster_tool_id is None:
        return _returned(
            actor,
            offset_um,
            "未从仍可投的刀中点选刀号（空选），整笔退回",
        )

    with transaction.atomic():
        try:
            tool = RosterTool.objects.select_for_update().get(pk=roster_tool_id)
        except RosterTool.DoesNotExist:
            return _returned(actor, offset_um, "所选刀号不在清册，整笔退回")

        if tool.state != RosterTool.State.INVESTABLE:
            return _returned(
                actor,
                offset_um,
                f"刀号 {tool.tool_code} 已摘牌、不可投，整笔退回",
                tool_code=tool.tool_code,
                tool=tool,
            )

        return OffsetSubmission.objects.create(
            # 刀号在此快照锁死：此后摘牌/重勾都改不了这张单
            tool_code=tool.tool_code,
            roster_tool=tool,
            offset_um=offset_um,
            submitted_by=actor,
            status=OffsetSubmission.Status.PENDING,
        )
