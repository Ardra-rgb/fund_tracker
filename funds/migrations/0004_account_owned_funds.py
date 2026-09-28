from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_existing_funds_to_first_user(apps, schema_editor):
    database = schema_editor.connection.alias
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    Member = apps.get_model("funds", "Member")
    CollectionPeriod = apps.get_model("funds", "CollectionPeriod")
    first_user = User.objects.using(database).order_by("pk").first()

    unowned_members = Member.objects.using(database).filter(owner__isnull=True)
    unowned_periods = CollectionPeriod.objects.using(database).filter(owner__isnull=True)
    if first_user is None:
        if unowned_members.exists() or unowned_periods.exists():
            raise RuntimeError(
                "Create an account before migrating existing fund records so they can be assigned."
            )
        return

    unowned_members.update(owner_id=first_user.pk)
    unowned_periods.update(owner_id=first_user.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("funds", "0003_collectionperiod"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fund_members",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="collectionperiod",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="collection_periods",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            assign_existing_funds_to_first_user,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="collectionperiod",
            name="unique_collection_period",
        ),
        migrations.AlterField(
            model_name="member",
            name="member_id",
            field=models.CharField(max_length=20),
        ),
        migrations.AlterField(
            model_name="member",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fund_members",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="collectionperiod",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="collection_periods",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="member",
            constraint=models.UniqueConstraint(
                fields=("owner", "member_id"),
                name="unique_owner_member_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="collectionperiod",
            constraint=models.UniqueConstraint(
                fields=("owner", "start_month", "end_month"),
                name="unique_owner_period_range",
            ),
        ),
    ]