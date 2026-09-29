import django.db.models.deletion
from django.db import migrations, models


def backfill_tools(apps, schema_editor):
    """把旧单据上出现过的刀号补登进清册并回链，保持可投。"""
    Tool = apps.get_model("desk", "Tool")
    OffsetSubmission = apps.get_model("desk", "OffsetSubmission")
    for row in OffsetSubmission.objects.all():
        tool, _ = Tool.objects.get_or_create(
            tool_code=row.tool_code,
            defaults={"usable": True, "delisted": False},
        )
        if row.tool_id is None:
            row.tool = tool
            row.save(update_fields=["tool"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("desk", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Tool",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tool_code", models.CharField(max_length=32, unique=True)),
                ("usable", models.BooleanField(default=True, verbose_name="可投")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("delisted", models.BooleanField(db_index=True, default=False, verbose_name="已摘牌")),
                ("delist_reason", models.CharField(blank=True, default="", max_length=200, verbose_name="摘牌原因")),
                ("delisted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "delisted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="delisted_tools",
                        to="desk.user",
                    ),
                ),
                (
                    "registered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="registered_tools",
                        to="desk.user",
                    ),
                ),
            ],
            options={
                "ordering": ["tool_code"],
            },
        ),
        migrations.AddField(
            model_name="offsetsubmission",
            name="tool",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="submissions",
                to="desk.tool",
            ),
        ),
        migrations.RunPython(backfill_tools, noop),
    ]
