from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_legacy_labels_and_memberships_survive_schema_upgrade():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [("tasks", "0001_initial"), ("students", "0001_initial")]
    try:
        executor.migrate(previous)
        old = executor.loader.project_state(previous).apps
        user = old.get_model("auth", "User").objects.create(username="legacy_owner")
        group = old.get_model("students", "StudyGroup").objects.create(name="КН-21", owner_id=user.pk)
        old.get_model("students", "GroupMembership").objects.create(user_id=user.pk, group_id=group.pk)
        policy = old.get_model("students", "GroupRolePolicy").objects.create(
            group_id=group.pk,
            role="deputy",
            can_invite=False,
            can_approve=True,
        )
        task = old.get_model("tasks", "Task").objects.create(
            title="Наявне завдання",
            subject="Алгоритми",
            topic="Сортування",
            deadline=timezone.now() + timedelta(days=3),
        )
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        new = executor.loader.project_state(latest).apps
        migrated = new.get_model("tasks", "Task").objects.get(pk=task.pk)
        assert migrated.legacy_subject == "Алгоритми"
        assert migrated.legacy_topic == "Сортування"
        assert migrated.subject_id is None
        assert migrated.topic_id is None
        migrated_policy = new.get_model("students", "GroupRolePolicy").objects.get(pk=policy.pk)
        assert migrated_policy.can_manage_tasks
        assert migrated_policy.can_manage_academics
        assert not migrated_policy.can_invite
        assert migrated_policy.can_approve
        membership = new.get_model("students", "GroupMembership").objects.get(user_id=user.pk)
        assert membership.group_id == group.pk
        other = new.get_model("students", "StudyGroup").objects.create(name="Друга група", owner_id=user.pk)
        new.get_model("students", "GroupMembership").objects.create(user_id=user.pk, group_id=other.pk)
        assert new.get_model("students", "GroupMembership").objects.filter(user_id=user.pk).count() == 2
    finally:
        MigrationExecutor(connection).migrate(latest)
