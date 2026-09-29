from django.core.management.base import BaseCommand
from django.utils import timezone

from desk.auth_utils import hash_password
from desk.models import OffsetSubmission, RosterEvent, RosterTool, User


class Command(BaseCommand):
    help = "创建默认账号、清册刀号与种子刀补记录"

    def handle(self, *args, **options):
        machinist, _ = User.objects.update_or_create(
            username="machinist",
            defaults={
                "role": User.Role.MACHINIST,
                "password": hash_password("machine123456"),
                "is_active": True,
            },
        )
        User.objects.update_or_create(
            username="auditor",
            defaults={
                "role": User.Role.AUDITOR,
                "password": hash_password("audit123456"),
                "is_active": True,
            },
        )

        # 清册：T01 / T09 登进清册并勾为可投
        roster = {}
        for tool_code in ("T01", "T09"):
            tool, created = RosterTool.objects.get_or_create(
                tool_code=tool_code,
                defaults={
                    "state": RosterTool.State.INVESTABLE,
                    "registered_by": machinist,
                },
            )
            if created:
                RosterEvent.objects.create(
                    tool=tool,
                    tool_code=tool.tool_code,
                    action=RosterEvent.Action.REGISTERED,
                    actor=machinist,
                )
            roster[tool_code] = tool

        now = timezone.now()
        seeds = [
            ("T01", 5, OffsetSubmission.Verdict.PASS),
            ("T09", 20, OffsetSubmission.Verdict.FAIL),
        ]
        for tool_code, offset_um, verdict in seeds:
            OffsetSubmission.objects.update_or_create(
                tool_code=tool_code,
                offset_um=offset_um,
                defaults={
                    "status": OffsetSubmission.Status.DONE,
                    "verdict": verdict,
                    "roster_tool": roster.get(tool_code),
                    "submitted_by": machinist,
                    "reviewed_at": now,
                },
            )

        self.stdout.write(self.style.SUCCESS("seed_offset_desk 完成"))
