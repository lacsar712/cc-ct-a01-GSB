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


class Tool(models.Model):
    """机床清册中的一把刀。`usable` 是清册上「可不可投」的勾选。"""

    tool_code = models.CharField(max_length=32, unique=True)
    usable = models.BooleanField("可投", default=True)
    registered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registered_tools",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # 摘牌痕迹：未摘牌时这三个字段为空；摘牌后只追加，不再回改
    delisted = models.BooleanField("已摘牌", default=False, db_index=True)
    delist_reason = models.CharField("摘牌原因", max_length=200, blank=True, default="")
    delisted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delisted_tools",
    )
    delisted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["tool_code"]

    def __str__(self) -> str:
        flag = "可投" if self.usable and not self.delisted else "已摘牌"
        return f"{self.tool_code}（{flag}）"


class OffsetSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待复核"
        PROCESSING = "processing", "复核中"
        DONE = "done", "已完成"

    class Verdict(models.TextChoices):
        PASS = "合格", "合格"
        FAIL = "超差", "超差"

    # 点选来源：交刀补时只能从清册里仍可投的刀中点选
    tool = models.ForeignKey(
        Tool,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="submissions",
    )
    # 选中的刀号写入单据即锁死：即使之后摘牌，单据上的刀号也不变
    tool_code = models.CharField(max_length=32, db_index=True)
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
