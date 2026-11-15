# studhub
crm and task manager for students group

Run tests with pytest and pytest-django:

```bash
uv sync --group dev
uv run pytest
```

Tests use a separate Django test database and an in-memory email backend.

Domain models and Figma screen mapping: [docs/domain-model.md](docs/domain-model.md).

Apps: `students` (profiles and groups), `academics` (curriculum), `tasks`
(assignments and individual progress), `notifications` (inbox), `dashboard`
(presentation layer).

```bash
uv run python manage.py migrate
uv run python manage.py check
```

Existing task labels are preserved as `legacy_subject` / `legacy_topic`;
assign those tasks to the correct curriculum in Django admin.

Run the Django interface locally (no frontend build is required):

```bash
uv run python manage.py runserver
```

Open `http://127.0.0.1:8000/`. The workspace supports desktop and mobile,
group/semester switching, task search and statuses, curriculum forms,
comments and authorized file downloads. See [docs/domain-model.md](docs/domain-model.md)
for all routes and current behavior.

Local test accounts and sample curriculum: [docs/demo.md](docs/demo.md).
Repopulate missing demo records with `uv run python manage.py seed_demo`.
