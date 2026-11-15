# Завдання

Модель і відповідність екранам описані в [доменній схемі](../docs/domain-model.md).
`Task.subject` — зв'язок з `academics.Subject`, `Task.topic` — необов'язковий
зв'язок з `academics.Topic` цього ж предмета. Група й семестр визначаються
через предмет. Додано тип роботи, пріоритет, автора, вкладення, коментарі зі
згадками та особистий прогрес кожного студента.

```python
from datetime import timedelta
from django.utils import timezone
from tasks.services import create_group_task, set_task_status
from tasks.models import TaskProgress

task = create_group_task(
    user,  # чинний учасник із правом can_manage_tasks
    title="Лабораторна робота №1",
    subject=subject,  # збережений academics.Subject
    deadline=timezone.now() + timedelta(days=7),
    submission_links=["https://classroom.google.com/"],
)
set_task_status(user, task.pk, status=TaskProgress.Status.IN_PROGRESS)
```

CRUD `create_task`, `update_task`, `get_task`, `list_tasks`, `delete_task`
є внутрішнім шаром без авторизації; майбутні HTTP views мають перевіряти
групу й дозволи. `create_group_task`, `set_task_status` і `add_comment`
виконують перевірки доступу. Оновлення полів і заміна посилань транзакційні.
Для справжніх рядкових блокувань у production потрібна БД із підтримкою
`select_for_update`; SQLite їх не надає.

Текст попередніх предметів і тем збережено в `legacy_subject`/`legacy_topic`.
Прив'язка старих завдань до навчального плану виконується через Django admin;
міграція не вгадує групу за назвою предмета.
