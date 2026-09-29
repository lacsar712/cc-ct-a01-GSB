from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        MACHINIST = "machinist", "操作员"
        AUDITOR = "auditor", "复核员"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MACHINIST,
    )

    @property
    def can_write(self) -> bool:
        return self.role == self.Role.MACHINIST


class RosterTool(models.Model):
    """机床刀具清册中的一把刀：刀号 + 当前是否可投。"""

    class State(models.TextChoices):
        INVESTABLE = "investable", "可投"
        DELISTED = "delisted", "已摘牌"

    tool_code = models.CharField(max_length=32, unique=True)
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.INVESTABLE,
        db_index=True,
    )
    registered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registered_tools",
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    delisted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["tool_code"]

    def __str__(self) -> str:
        return f"{self.tool_code}（{self.get_state_display()}）"


class RosterEvent(models.Model):
    """清册操作留痕：登记 / 勾可投 / 摘牌。摘牌痕迹永久保留。"""

    class Action(models.TextChoices):
        REGISTERED = "registered", "登记"
        RELISTED = "relisted", "勾可投"
        DELISTED = "delisted", "摘牌"

    tool = models.ForeignKey(
        RosterTool,
        on_delete=models.CASCADE,
        related_name="events",
    )
    # 刀号快照：即便后续重新登记/改名，痕迹里仍保留当时刀号
    tool_code = models.CharField(max_length=32)
    action = models.CharField(max_length=16, choices=Action.choices)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roster_events",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.tool_code}"


class OffsetSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待复核"
        PROCESSING = "processing", "复核中"
        DONE = "done", "已完成"
        RETURNED = "returned", "已退回"

    class Verdict(models.TextChoices):
        PASS = "合格", "合格"
        FAIL = "超差", "超差"

    # 刀号写入单据即锁死的快照；刀此后被摘牌不影响本单
    tool_code = models.CharField(max_length=32, db_index=True)
    roster_tool = models.ForeignKey(
        RosterTool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )
    offset_um = models.IntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    verdict = models.CharField(
        max_length=8,
        choices=Verdict.choices,
        blank=True,
        default="",
    )
    return_reason = models.CharField(max_length=255, blank=True, default="")
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.tool_code} {self.offset_um}µm"
