from itertools import count

import pytest

from .profiles import complete_profile
from .services import create_group, create_invitation, request_to_join, review_join_request


@pytest.fixture(autouse=True)
def media_storage(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def student_factory(django_user_model):
    sequence = count()

    def create(*, complete=True):
        number = next(sequence)
        user = django_user_model.objects.create_user(username=f"student{number}", email=f"student{number}@example.com")
        if complete:
            complete_profile(user, first_name="Олена", last_name=f"Коваль{number}")
        return user

    return create


@pytest.fixture
def owner(student_factory):
    return student_factory()


@pytest.fixture
def group(owner):
    return create_group(owner, name="КН-21")


@pytest.fixture
def member_factory(owner, group, student_factory):
    def create():
        user = student_factory()
        invitation = create_invitation(owner, group.pk)
        application = request_to_join(user, invitation.token)
        review_join_request(owner, application.pk, approve=True)
        return user

    return create
