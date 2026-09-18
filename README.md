# TrackFlow

A functional clone of Jira Software (Cloud): Django/DRF API + React/TypeScript frontend, built
to look and behave like real Jira — same layout regions, same interaction patterns, same
information density.

## Stack

- **Backend**: Django 5, Django REST Framework, SimpleJWT, drf-spectacular, django-filter,
  Celery (eager-mode by default), Channels (stubbed, see below)
- **Frontend**: React 19 + TypeScript + Vite, React Router, TanStack Query, Zustand,
  TanStack Table v9, @dnd-kit, Tiptap, Radix UI primitives, Recharts, CSS Modules

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo      # creates a demo org, 2 projects, teams, users, ~140 issues
python manage.py runserver
```

API docs (Swagger UI) at http://localhost:8000/api/docs/. Django admin at
http://localhost:8000/admin/. Re-run `seed_demo --reset` any time to wipe and regenerate the
demo projects (TRK, OPS) with fresh dates/data.

**Demo login** (also printed by `seed_demo`): any of the seeded emails (e.g.
`hemanthaviraj6@gmail.com`) with password `password123`. That user is also a Django
superuser, so it works for `/admin/` too.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` and `/media` to
`http://127.0.0.1:8000`, so run the backend first.

### Database

Defaults to **SQLite** (`backend/db.sqlite3`) so the app runs with zero external services.
A `docker-compose.yml` at the repo root provisions Postgres 16 + Redis 7 if you'd rather run
against those — set `DB_ENGINE=postgres` (and fill in the `DB_*` vars) in `backend/.env`,
then `docker compose up -d` before migrating.

## What's implemented

- **Auth & workspace**: email/password signup+login (JWT), profile page with avatar upload
- **Projects**: list (sortable table), create wizard (Scrum/Kanban), project sidebar,
  settings (General / People & roles / Workflow)
- **Issues**: global create modal, detail view as both a slide-over modal and a full page,
  inline-editable summary/description (Tiptap rich text), sub-tasks, issue linking,
  drag-and-drop attachments, comments, full activity history, watch/unwatch
- **Backlog & Sprints**: ranked drag-and-drop backlog and sprint sections, epic filter panel,
  quick-add, start/complete sprint (with incomplete-issue carry-over)
- **Boards**: one reusable `<KanbanBoard>` powering four scopes — project board (scrum active
  sprint or kanban), single-epic board, team board (aggregated across projects), and a
  personal "Your work" board — with swimlanes, WIP limits, column collapse, and quick filters
- **Tables**: one reusable `<IssueTable>` (sortable/resizable/hideable columns, manual "group
  by" sectioning, inline status/assignee/priority editing) powering the project Issues
  navigator, a Team's Issues tab (+ workload chart), and a per-person workload page
- **People & Teams**: team CRUD with membership management, a People directory, individual
  workload pages (open/done/overdue stats) linked from avatars throughout the app
- **Search & filters**: Ctrl/Cmd+K quick search (issues + projects), saved filters
- **Notifications**: in-app bell (polling) for assignment, comment, and status-change events
- **Timeline**: drag-to-move/resize Gantt bars for epics
- **Reports**: sprint burndown + velocity charts
- **Dashboard**: assigned-to-me, recent activity feed, personal status breakdown pie chart

## Architecture overview

```
backend/
  trackflow/        Django project: settings, root URLconf, Celery app
  apps/
    orgs/            Organization (single-tenant for v1) + seed_demo management command
    accounts/        custom User model (email login), auth endpoints
    projects/        Project, ProjectMembership, Label, Component, Version
    workflow/        IssueType, Workflow/WorkflowStatus/WorkflowTransition, Board
    issues/          Issue (+ Comment/Attachment/IssueLink/History/Watcher), rank.py
    sprints/         Sprint, burndown/velocity endpoints
    teams/           Team, TeamMembership
    notifications/   Notification + trigger hooks (assign/comment/status-change)
    search/          saved Filter, quick-search endpoint
    reports/         Dashboard, DashboardWidget (models only — see below)

frontend/src/
  design-system/     tokens.css + primitives (Avatar, Button, Dialog, Tabs, Skeleton, ...)
  app/               router, AppShell (global sidebar + top nav), ProtectedRoute, ErrorBoundary
  api/               axios client (JWT refresh interceptor) + React Query hooks per resource
  store/             Zustand stores (auth, cross-app UI state — modals, quick search)
  lib/               shared TanStack Table v9 feature-set configs
  features/          one folder per feature area (auth, projects, issues, board, backlog,
                      tables, teams, people, search, notifications, timeline, reports,
                      dashboard)
```

### Key design decisions

- **Multi-tenancy**: a single `Organization` row is auto-created (`Organization.get_solo()`).
  Models FK down through it, so real multi-org support is additive later, not a rewrite.
- **Real-time updates**: Django Channels is wired into `INSTALLED_APPS`/`ASGI_APPLICATION`
  but gated behind `REALTIME_ENABLED` (off by default). The frontend polls with TanStack
  Query instead. Turning on live board/notification push is a documented follow-up.
- **Ranking**: drag-and-drop ordering (backlog, board columns) uses a LexoRank-style
  base-36 string rank (`apps/issues/rank.py`) so reordering one card never rewrites its
  neighbors. A single `Issue.move()` API action handles rank + optional status/sprint change
  in one call, used by both the backlog and every board.
- **Cross-project boards**: the Team and "Your work" boards aggregate issues from projects
  with different workflows, so their columns are generic status *categories*
  (To Do/In Progress/Done) rather than one project's concrete status IDs; dropping a card
  resolves the right concrete status per-issue via each project's board config.
- **Rich text**: issue descriptions and comments are stored as Tiptap/ProseMirror JSON in a
  `JSONField` and rendered with Tiptap on the frontend.
- **Auth**: SimpleJWT access + refresh tokens. The frontend keeps both in a Zustand store
  persisted to `localStorage`, with an axios interceptor that transparently refreshes on a
  401 — a standard SPA tradeoff (no httpOnly cookie), acceptable for this project's scope.
- **"Group by" in tables**: implemented by hand (partition sorted rows into labeled sections)
  rather than TanStack's grouped-row-model, which targets collapsible pivot trees rather than
  a flat, section-headed issue list.

## Tests

```bash
# backend (43 tests: rank algorithm, issue CRUD/history, sprints, notifications, reports, teams)
cd backend && ./.venv/Scripts/python.exe -m pytest

# frontend (Vitest + React Testing Library: KanbanBoard, IssueTable, design-system primitives)
cd frontend && npm test
```

## Known follow-ups (documented, not yet implemented)

- Real-time push via Channels (currently polling-based).
- Full JQL-style query bar (the structured filter panel covers the core need); saved filters
  can be created but aren't yet re-applied from the Filters page.
- Per-project custom issue types (system types — Epic/Story/Task/Bug/Sub-task — are seeded
  globally; the schema already supports a per-project override).
- Workflow editor is currently read-only in Project Settings (add/remove/reorder statuses and
  custom transitions are a fast-follow).
- Dashboard is a fixed single layout rather than the configurable `Dashboard`/`DashboardWidget`
  models (which exist in the schema for that future work).
- Custom mobile layout is out of scope; the app is responsive down to tablet width.
