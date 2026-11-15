"""Repeatable local demo data. Existing accounts and records are never reset."""

from datetime import date, datetime, time, timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import Semester, Subject, Topic
from notifications.models import Notification
from students.models import GroupInvitation, GroupMembership, GroupRole, JoinRequest, StudyGroup
from students.profiles import complete_profile
from students.services import create_group
from tasks.models import SubmissionLink, Task, TaskAttachment, TaskComment, TaskProgress

DEMO_PASSWORD = "StudHub-demo-2026!"
DEMO_ACCOUNTS = (
    ("owner", "Марія", "Коваленко"),
    ("deputy", "Олег", "Сидоренко"),
    ("student", "Нікіта", "Савін"),
    ("anna", "Анна", "Шевченко"),
    ("ihor", "Ігор", "Петренко"),
    ("anastasia", "Анастасія", "Левченко"),
    ("applicant", "Ірина", "Мельник"),
    ("guest", "Андрій", "Бондар"),
)
SUBJECTS = (
    ("Міжнародне право", "Чернецька О.В.", "Державне та міжнародне право"),
    ("Методологія досліджень", "Шилінгов В.С.", "Методи й організація наукової діяльності"),
    ("Теорія національної безпеки", "Минюк О.Ю.", "Безпека держави та суспільства"),
    ("Державний розвиток", "Мельник О.П.", "Публічне управління та національна стійкість"),
    ("Іноземна мова", "Коваль І.М.", "Англійська мова для навчання і роботи"),
    ("Інформаційні системи", "Петренко А.В.", "Інформатика й цифрові інструменти"),
)


def ensure(model, *, defaults=None, **lookup):
    """Keep the first matching record, including any changes made while testing."""
    existing = model.objects.filter(**lookup).order_by("pk").first()
    return existing if existing is not None else model.objects.create(**lookup, **(defaults or {}))


def period(day):
    if day.month >= 9:
        return f"Осінній семестр {day.year}", date(day.year, 9, 1), date(day.year + 1, 1, 31), day.year
    if day.month == 1:
        return f"Осінній семестр {day.year - 1}", date(day.year - 1, 9, 1), date(day.year, 1, 31), day.year - 1
    return f"Весняний семестр {day.year}", date(day.year, 2, 1), date(day.year, 8, 31), day.year - 1


class Command(BaseCommand):
    help = "Додати демо-групи StudHub, акаунти й навчальні дані в локальну базу без перезаписування."

    def add_arguments(self, parser):
        parser.add_argument("--attach-user-id", type=int, help="Також додати існуючий акаунт до демо-груп.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Демо-дані можна додавати лише з DEBUG=True.")
        user_model = get_user_model()
        attached = None
        if options["attach_user_id"]:
            try:
                attached = user_model.objects.get(pk=options["attach_user_id"])
            except user_model.DoesNotExist as exc:
                raise CommandError("Акаунт для додавання до демо-груп не знайдено.") from exc
        users = {}
        for alias, first, last in DEMO_ACCOUNTS:
            username, email = f"studhub_demo_{alias}", f"{alias}@studhub.test"
            if user_model.objects.filter(email__iexact=email).exclude(username=username).exists():
                raise CommandError(f"Адреса {email} вже належить іншому акаунту; зміни скасовано.")
            user, created = user_model.objects.get_or_create(username=username, defaults={"email": email})
            if not created and (user.email.casefold() != email or user.is_staff or user.is_superuser):
                raise CommandError(f"Конфлікт із наявним акаунтом {username}; зміни скасовано.")
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
                complete_profile(user, first_name=first, last_name=last)
                EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
            users[alias] = user
        owner, deputy = users["owner"], users["deputy"]
        groups = []
        for name, creator, description in (
            ("[Демо] ПМНБ-26-1", owner, "Державний податковий університет · тестовий навчальний простір"),
            ("[Демо] IT Community", deputy, "Навчальна IT-спільнота · тестовий навчальний простір"),
        ):
            group = StudyGroup.objects.filter(owner=creator, name=name).order_by("pk").first()
            if group is None:
                group = create_group(creator, name=name, description=description, course=2)
            groups.append(group)
        members = [users[alias] for alias, _, _ in DEMO_ACCOUNTS[:6]]
        for index, group in enumerate(groups):
            for user in members:
                role = (
                    GroupRole.DEPUTY
                    if (user == deputy and index == 0) or (user == users["student"] and index == 1)
                    else GroupRole.STUDENT
                )
                ensure(GroupMembership, group=group, user=user, defaults={"role": role})
            if attached and attached not in members:
                ensure(
                    GroupMembership,
                    group=group,
                    user=attached,
                    defaults={"role": GroupRole.DEPUTY if index == 0 else GroupRole.STUDENT},
                )
        recipients = members + ([attached] if attached and attached not in members else [])
        today = timezone.localdate()
        current = period(today)
        previous = period(current[1] - timedelta(days=1))
        future = period(current[2] + timedelta(days=1))
        current_tasks = []
        for group_index, group in enumerate(groups):
            for kind, (name, start, end, academic_year) in (
                ("current", current),
                ("archive", previous),
                ("future", future),
            ):
                semester = ensure(
                    Semester,
                    group=group,
                    name=name,
                    defaults={
                        "academic_year_start": academic_year,
                        "starts_on": start,
                        "ends_on": end,
                        "is_active": kind == "current" and not group.semesters.filter(is_active=True).exists(),
                    },
                )
                disciplines = (
                    SUBJECTS[: 6 if group_index == 0 else 3]
                    if kind == "current"
                    else SUBJECTS[: 2 if kind == "archive" else 1]
                )
                for subject_index, (subject_name, teacher, description) in enumerate(disciplines):
                    subject = ensure(
                        Subject,
                        semester=semester,
                        name=subject_name,
                        defaults={
                            "teacher_name": teacher,
                            "description": description,
                            "teacher_email": f"teacher{subject_index + 1}@example.com",
                            "teacher_contact": "Контакти для демонстрації інтерфейсу",
                        },
                    )
                    topic = ensure(
                        Topic, subject=subject, name="Основи та практичні приклади", defaults={"position": 1}
                    )
                    for task_index in range(4 if kind == "current" else 2):
                        work_types = (
                            Task.WorkType.MODULE,
                            Task.WorkType.INDEPENDENT,
                            Task.WorkType.SEMINAR,
                            Task.WorkType.TEST,
                        )
                        labels = ("МКР №1", "Самостійна робота №2", "Семінар №3", "Тест №4")
                        day = (
                            today + timedelta(days=(-5, -1, 3, 8)[task_index] + subject_index)
                            if kind == "current"
                            else start + timedelta(days=12 + task_index * 7)
                        )
                        task = ensure(
                            Task,
                            subject=subject,
                            title=f"{labels[task_index]} — {subject_name}",
                            defaults={
                                "topic": topic,
                                "deadline": timezone.make_aware(datetime.combine(day, time(23, 59))),
                                "work_type": work_types[task_index],
                                "priority": Task.Priority.HIGH if task_index == 0 else Task.Priority.NORMAL,
                                "is_required": task_index != 3,
                                "created_by": group.owner,
                                "description": "Тестове завдання для перевірки StudHub.\n\n1. Опрацюйте матеріали теми.\n2. Підготуйте відповіді та приклади.\n3. Перевірте власний статус виконання.\n\nЦі дані можна редагувати під час тестування.",
                            },
                        )
                        if kind == "current":
                            current_tasks.append(task)
                        for member_index, user in enumerate(recipients):
                            status = TaskProgress.Status.values[(task_index + subject_index + member_index) % 4]
                            ensure(TaskProgress, task=task, user=user, defaults={"status": status})
        sample = current_tasks[0]
        for author, body in (
            (owner, "Матеріали додано. Якщо виникнуть запитання, пишіть у коментарях."),
            (users["student"], "Дякую! Починаю роботу над завданням."),
        ):
            ensure(TaskComment, task=sample, author=author, defaults={"body": body})
        if not sample.attachments.filter(name="Демо-матеріали.txt").exists():
            attachment = TaskAttachment(task=sample, name="Демо-матеріали.txt", uploaded_by=owner)
            attachment.file.save(
                "demo-materials.txt",
                ContentFile("Демонстраційний матеріал StudHub.\nФайл доступний учасникам групи.\n".encode()),
                save=True,
            )
        ensure(SubmissionLink, task=sample, url="https://classroom.google.com/")
        invite = ensure(GroupInvitation, group=groups[0], created_by=owner, email="")
        personal_invite = ensure(
            GroupInvitation,
            group=groups[0],
            created_by=owner,
            email=users["applicant"].email,
            defaults={"max_uses": 1, "use_count": 1},
        )
        ensure(JoinRequest, group=groups[0], user=users["applicant"], defaults={"invitation": personal_invite})
        ensure(
            JoinRequest,
            group=groups[1],
            user=users["guest"],
            defaults={"invitation": ensure(GroupInvitation, group=groups[1], created_by=deputy, email="")},
        )
        for user in recipients:
            for index, (kind, title) in enumerate(
                (
                    (Notification.Kind.TASK_CREATED, "Нове завдання у групі"),
                    (Notification.Kind.DEADLINE, "Зверніть увагу на дедлайн"),
                    (Notification.Kind.TASK_UPDATED, "Оновлено навчальні матеріали"),
                )
            ):
                task = current_tasks[index]
                ensure(
                    Notification,
                    recipient=user,
                    task=task,
                    group=task.group,
                    kind=kind,
                    defaults={
                        "title": title,
                        "body": task.title,
                        "read_at": timezone.now() if index == 2 else None,
                    },
                )
        self.stdout.write(self.style.SUCCESS("Демо-дані готові. Наявні дані та паролі не перезаписані."))
        self.stdout.write("Групи: " + ", ".join(group.name for group in groups))
        self.stdout.write("Акаунти: owner@studhub.test, deputy@studhub.test, student@studhub.test")
        self.stdout.write(f"Пароль нових демо-акаунтів: {DEMO_PASSWORD}")
        self.stdout.write(f"Групи доступні на /groups/. Запрошення для тесту: /invitations/{invite.token}/")
        if attached:
            self.stdout.write("Існуючий акаунт додано до демо-груп; його власні дані збережені.")
