import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.chat.models import Channel, ChannelMembership, Message, MessageIssueLink
from apps.issues.models import Comment, Issue, IssueHistory, Watcher
from apps.issues.rank import rank_after, rank_first
from apps.orgs.models import Organization
from apps.projects.models import Component, Label, Project, ProjectMembership, Version
from apps.sprints.models import Sprint
from apps.teams.models import Team, TeamMembership
from apps.timesheets.models import TimeEntry
from apps.workflow.models import IssueType
from apps.workflow.services import create_default_board, create_default_workflow

DEMO_USERS = [
    # (username, email, display_name, job_title)
    ("hemanth", "hemanthaviraj6@gmail.com", "Hemanth Aviraj", "Engineering Lead"),
    ("priya", "priya.demo@trackflow.local", "Priya Sharma", "Senior Backend Engineer"),
    ("marcus", "marcus.demo@trackflow.local", "Marcus Chen", "Frontend Engineer"),
    ("aisha", "aisha.demo@trackflow.local", "Aisha Khan", "Product Manager"),
    ("liam", "liam.demo@trackflow.local", "Liam O'Connor", "QA Engineer"),
    ("sofia", "sofia.demo@trackflow.local", "Sofia Rossi", "DevOps Engineer"),
    ("daniel", "daniel.demo@trackflow.local", "Daniel Kim", "Backend Engineer"),
    ("nina", "nina.demo@trackflow.local", "Nina Petrova", "UX Designer"),
]
DEMO_PASSWORD = "password123"

ISSUE_TYPES = [
    ("Epic", "zap", "#8777D9", False),
    ("Story", "bookmark", "#36B37E", False),
    ("Task", "check-square", "#0C66E4", False),
    ("Bug", "bug", "#E5493A", False),
    ("Sub-task", "check-square", "#0C66E4", True),
]

EPIC_COLORS = ["#8777D9", "#00B8D9", "#36B37E", "#FF5630", "#FFAB00", "#6554C0"]

EPIC_TOPICS = {
    "TRK": [
        ("Onboarding revamp", "Streamline new-user signup and first-run experience"),
        ("Search & filters", "Faster, more relevant issue search across the app"),
        ("Notifications overhaul", "Real-time-feeling notifications without full websockets"),
        ("Reporting suite", "Burndown, velocity, and dashboard widgets"),
    ],
    "OPS": [
        ("CI/CD pipeline", "Faster, more reliable build and deploy pipeline"),
        ("Observability", "Logging, metrics and alerting across services"),
        ("Infra cost reduction", "Right-size infrastructure spend"),
    ],
}

STORY_SUMMARIES = [
    "Add {noun} to the {area}",
    "Fix broken {noun} on {area}",
    "Improve performance of {area}",
    "Investigate flaky {noun} in {area}",
    "Design {noun} for {area}",
    "Write tests for {area}",
    "Refactor {area} to use {noun}",
    "Update {area} copy and empty states",
    "Handle edge case in {area}",
    "Add validation to {noun} form",
]
NOUNS = ["pagination", "caching layer", "webhook", "avatar upload", "rate limiter", "audit log", "search index", "drag handle", "keyboard shortcut", "export button"]
AREAS = ["board", "backlog", "issue detail", "comments", "notifications", "project settings", "sprint report", "login flow", "API", "dashboard"]

PRIORITIES = ["highest", "high", "medium", "medium", "low", "lowest"]


class Command(BaseCommand):
    help = "Seed a demo organization with projects, teams, users, and sample issues."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete existing demo projects before reseeding."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(42)
        org = Organization.get_solo()
        self.stdout.write(f"Organization: {org.name}")

        if options["reset"]:
            # Issue.status/issue_type are PROTECTed (so stray admin deletes can't
            # silently orphan issues), which would otherwise block Project's
            # cascade into Workflow/WorkflowStatus. Clear issues first.
            reset_projects = Project.objects.filter(key__in=["TRK", "OPS"])
            Issue.objects.filter(project__in=reset_projects).delete()
            reset_projects.delete()
            self.stdout.write(self.style.WARNING("Deleted existing TRK/OPS projects."))

        users = self._seed_users()
        issue_types = self._seed_issue_types()
        teams = self._seed_teams(users)

        scrum_project = self._seed_project(
            org, key="TRK", name="TrackFlow Web App", project_type=Project.ProjectType.SCRUM,
            lead=users["hemanth"], users=users, avatar_color="#0C66E4",
        )
        kanban_project = self._seed_project(
            org, key="OPS", name="Platform Ops", project_type=Project.ProjectType.KANBAN,
            lead=users["sofia"], users=users, avatar_color="#36B37E",
        )

        self._seed_general_channel(org)

        for project in (scrum_project, kanban_project):
            statuses = self._seed_workflow(project)
            self._seed_board(project, statuses)
            self._seed_lookups(project, users)
            epics = self._seed_epics(project, issue_types, users, statuses)
            sprints = self._seed_sprints(project) if project.project_type == Project.ProjectType.SCRUM else []
            self._seed_issues(project, issue_types, statuses, users, epics, sprints)
            self._backfill_project_channel(project)
            self._seed_chat_messages(project, users)
            self._seed_time_entries(project, users)

        for team in teams.values():
            self._backfill_team_channel(team)

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
        self.stdout.write(f"Log in as any of: {', '.join(u[1] for u in DEMO_USERS)}")
        self.stdout.write(f"Password for all demo users: {DEMO_PASSWORD}")

    # -- users / teams -----------------------------------------------------

    def _seed_users(self):
        users = {}
        for username, email, display_name, job_title in DEMO_USERS:
            user, created = User.objects.get_or_create(
                email=email,
                defaults=dict(username=username, display_name=display_name, job_title=job_title),
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.is_staff = username == "hemanth"
                user.is_superuser = username == "hemanth"
                user.save()
            users[username] = user
        self.stdout.write(f"Users: {len(users)}")
        return users

    def _seed_issue_types(self):
        types = {}
        for name, icon, color, is_subtask in ISSUE_TYPES:
            it, _ = IssueType.objects.get_or_create(
                name=name, project=None,
                defaults=dict(icon=icon, color=color, is_subtask=is_subtask),
            )
            types[name] = it
        return types

    def _seed_teams(self, users):
        platform, _ = Team.objects.get_or_create(
            organization=Organization.get_solo(), name="Platform Team",
            defaults=dict(description="Owns core infra and backend services.", avatar_color="#36B37E"),
        )
        growth, _ = Team.objects.get_or_create(
            organization=Organization.get_solo(), name="Growth Team",
            defaults=dict(description="Owns onboarding, activation and growth surfaces.", avatar_color="#FF5630"),
        )
        platform_members = ["sofia", "daniel", "priya", "hemanth"]
        growth_members = ["aisha", "marcus", "nina", "liam"]
        for uname in platform_members:
            TeamMembership.objects.get_or_create(
                team=platform, user=users[uname],
                defaults=dict(role="lead" if uname == "sofia" else "member"),
            )
        for uname in growth_members:
            TeamMembership.objects.get_or_create(
                team=growth, user=users[uname],
                defaults=dict(role="lead" if uname == "aisha" else "member"),
            )
        return {"platform": platform, "growth": growth}

    # -- project scaffolding -------------------------------------------------

    def _seed_project(self, org, key, name, project_type, lead, users, avatar_color):
        project, _ = Project.objects.get_or_create(
            key=key,
            defaults=dict(
                organization=org, name=name, project_type=project_type, lead=lead,
                avatar_color=avatar_color, description=f"Demo {project_type} project.",
            ),
        )
        roles = {lead.username: ProjectMembership.Role.ADMIN}
        for uname, user in users.items():
            role = roles.get(uname, ProjectMembership.Role.MEMBER)
            ProjectMembership.objects.get_or_create(project=project, user=user, defaults=dict(role=role))
        return project

    def _seed_workflow(self, project):
        return create_default_workflow(project)

    def _seed_board(self, project, statuses):
        create_default_board(project, statuses)

    def _seed_lookups(self, project, users):
        for name, color in [("frontend", "#0C66E4"), ("backend", "#36B37E"), ("tech-debt", "#FF5630"), ("design", "#8777D9")]:
            Label.objects.get_or_create(project=project, name=name, defaults=dict(color=color))
        for name in ["API", "Web App", "Infrastructure"]:
            Component.objects.get_or_create(project=project, name=name, defaults=dict(lead=project.lead))
        Version.objects.get_or_create(
            project=project, name="v1.0",
            defaults=dict(release_date=timezone.now().date() - timedelta(days=30), released=True),
        )
        Version.objects.get_or_create(
            project=project, name="v1.1",
            defaults=dict(release_date=timezone.now().date() + timedelta(days=30), released=False),
        )

    def _seed_epics(self, project, issue_types, users, statuses):
        epics = []
        todo_status = statuses["To Do"]
        member_users = list(users.values())
        for i, (name, description) in enumerate(EPIC_TOPICS.get(project.key, [])):
            existing = Issue.objects.filter(project=project, issue_type=issue_types["Epic"], epic_name=name).first()
            if existing:
                epics.append(existing)
                continue
            last = Issue.objects.filter(project=project).order_by("-rank").first()
            epic_start = timezone.now().date() + timedelta(days=i * 16 - 35)
            epic = Issue.objects.create(
                project=project, issue_type=issue_types["Epic"], summary=name,
                description=_rich_text(description), status=todo_status,
                reporter=project.lead, assignee=random.choice(member_users),
                epic_name=name, epic_color=EPIC_COLORS[i % len(EPIC_COLORS)],
                priority=random.choice(PRIORITIES),
                rank=rank_after(last.rank) if last else rank_first(),
                start_date=epic_start,
                due_date=epic_start + timedelta(days=32),
            )
            epics.append(epic)
        return epics

    def _seed_sprints(self, project):
        now = timezone.now().date()
        sprints = []
        specs = [
            ("Sprint 1", now - timedelta(days=42), now - timedelta(days=28), Sprint.State.CLOSED),
            ("Sprint 2", now - timedelta(days=28), now - timedelta(days=14), Sprint.State.CLOSED),
            ("Sprint 3", now - timedelta(days=14), now, Sprint.State.ACTIVE),
            ("Sprint 4", now, now + timedelta(days=14), Sprint.State.FUTURE),
        ]
        for order, (name, start, end, state) in enumerate(specs):
            sprint, _ = Sprint.objects.get_or_create(
                project=project, name=name,
                defaults=dict(
                    goal=f"Ship the {project.name} improvements planned for {name}.",
                    start_date=start, end_date=end, state=state, order=order,
                    completed_at=timezone.now() - timedelta(days=(4 - order) * 14) if state == Sprint.State.CLOSED else None,
                ),
            )
            sprints.append(sprint)
        return sprints

    # -- issues --------------------------------------------------------------

    def _seed_issues(self, project, issue_types, statuses, users, epics, sprints):
        story_types = [issue_types["Story"], issue_types["Task"], issue_types["Bug"]]
        if Issue.objects.filter(project=project, issue_type__in=story_types).exists():
            self.stdout.write(f"Issues already seeded for {project.key}, skipping.")
            return

        member_users = list(users.values())
        status_list = list(statuses.values())
        n_issues = 60 if project.project_type == "scrum" else 45

        last = Issue.objects.filter(project=project).order_by("-rank").first()
        prev_rank = last.rank if last else None

        for i in range(n_issues):
            issue_type = random.choice(story_types)
            summary = random.choice(STORY_SUMMARIES).format(
                noun=random.choice(NOUNS), area=random.choice(AREAS)
            )
            status = self._weighted_status(status_list, sprints)
            assignee = random.choice(member_users + [None])
            epic = random.choice(epics + [None, None])
            sprint = None
            resolved_at = None
            if sprints:
                active_sprint = sprints[2]
                if status.category == "done":
                    # Include the active sprint so it has real completed points to
                    # burn down, not just the two closed sprints.
                    sprint = random.choice(sprints[:3]) if random.random() < 0.75 else None
                    if sprint is active_sprint and active_sprint.start_date:
                        days_into_sprint = (timezone.now().date() - active_sprint.start_date).days
                        resolved_at = timezone.now() - timedelta(days=random.randint(0, max(days_into_sprint, 0)))
                    else:
                        resolved_at = timezone.now() - timedelta(days=random.randint(1, 20))
                elif status.category == "in_progress":
                    sprint = active_sprint
                else:
                    sprint = random.choice([active_sprint, sprints[3], None])
            elif status.category == "done":
                resolved_at = timezone.now() - timedelta(days=random.randint(1, 20))

            rank = rank_after(prev_rank) if prev_rank else rank_first()
            issue = Issue.objects.create(
                project=project, issue_type=issue_type, summary=summary,
                description=_rich_text(f"Details for {summary.lower()}."),
                status=status, priority=random.choice(PRIORITIES),
                assignee=assignee, reporter=random.choice(member_users),
                epic=epic, sprint=sprint,
                story_points=random.choice([None, 1, 2, 3, 5, 8]),
                due_date=timezone.now().date() + timedelta(days=random.randint(-10, 30)) if random.random() < 0.3 else None,
                resolved_at=resolved_at,
                rank=rank,
            )
            prev_rank = issue.rank

            if project.labels.exists() and random.random() < 0.5:
                issue.labels.add(random.choice(list(project.labels.all())))
            if project.components.exists() and random.random() < 0.4:
                issue.components.add(random.choice(list(project.components.all())))

            if random.random() < 0.25:
                Comment.objects.create(
                    issue=issue, author=random.choice(member_users),
                    body=_rich_text(random.choice([
                        "Looks good to me, shipping this.",
                        "Can we get a screenshot before this is closed?",
                        "Blocked on the API change — following up.",
                        "Nice catch, fixed in the latest commit.",
                    ])),
                )
            if random.random() < 0.2:
                Watcher.objects.get_or_create(issue=issue, user=random.choice(member_users))

            # a few sub-tasks off of ~15% of parent issues
            if not issue_type.is_subtask and random.random() < 0.15:
                for j in range(random.randint(1, 3)):
                    sub_rank = rank_after(prev_rank)
                    sub = Issue.objects.create(
                        project=project, issue_type=issue_types["Sub-task"],
                        summary=f"{summary} — subtask {j + 1}",
                        status=random.choice(status_list), priority="medium",
                        assignee=assignee, reporter=issue.reporter, parent=issue,
                        rank=sub_rank,
                    )
                    prev_rank = sub.rank

        self.stdout.write(f"Issues seeded for {project.key}: {Issue.objects.filter(project=project).count()}")
        self._seed_recent_activity(project, users)

    def _seed_recent_activity(self, project, users):
        """A handful of backdated IssueHistory rows so the dashboard's Recent
        Activity widget has something to show right after a fresh seed."""
        member_users = list(users.values())
        candidates = list(
            Issue.objects.filter(project=project, issue_type__is_subtask=False).order_by("-updated_at")[:15]
        )
        if not candidates:
            return
        transitions = [
            ("status", "To Do", "In Progress"),
            ("status", "In Progress", "In Review"),
            ("status", "In Review", "Done"),
            ("priority", "medium", "high"),
            ("assignee", "", ""),
        ]
        rows = []
        for i in range(10):
            issue = random.choice(candidates)
            field, old, new = random.choice(transitions)
            user = random.choice(member_users)
            if field == "assignee":
                new = random.choice(member_users).display_name
            rows.append(
                IssueHistory(
                    issue=issue, user=user, field_changed=field, old_value=old, new_value=new,
                    timestamp=timezone.now() - timedelta(hours=random.randint(1, 96)),
                )
            )
        IssueHistory.objects.bulk_create(rows)

    # -- chat -----------------------------------------------------------------

    def _seed_general_channel(self, org):
        Channel.objects.get_or_create(
            organization=org, channel_type=Channel.ChannelType.GENERAL,
            defaults=dict(name="general", description="Workspace-wide announcements and chat."),
        )

    def _backfill_project_channel(self, project):
        """The auto-create signal only fires for newly-created projects; this covers
        projects that already existed before the chat app did."""
        if Channel.objects.filter(linked_project=project).exists():
            return
        channel = Channel.objects.create(
            organization=project.organization, name=project.key.lower(),
            description=f"Discussion for {project.name}", channel_type=Channel.ChannelType.PROJECT,
            linked_project=project, created_by=project.lead,
        )
        if project.lead:
            ChannelMembership.objects.get_or_create(
                channel=channel, user=project.lead, defaults={"role": ChannelMembership.Role.OWNER}
            )

    def _backfill_team_channel(self, team):
        if Channel.objects.filter(linked_team=team).exists():
            return
        Channel.objects.create(
            organization=team.organization, name=team.name.lower().replace(" ", "-"),
            description=f"Discussion for {team.name}", channel_type=Channel.ChannelType.TEAM,
            linked_team=team,
        )

    def _seed_chat_messages(self, project, users):
        channel = Channel.objects.filter(linked_project=project).first()
        if not channel or channel.messages.exists():
            return

        member_users = list(users.values())
        sample_issue = Issue.objects.filter(
            project=project, issue_type__is_subtask=False, issue_type__name__in=["Task", "Bug", "Story"]
        ).order_by("?").first()

        lines = [
            "Morning! Anyone free to pair on the login flow bug this afternoon?",
            "Deployed the latest build to staging, looks good so far.",
            "Heads up — the board's looking a little full in In Progress, let's clear some out.",
            "Nice work on the sprint demo yesterday, team.",
        ]
        base_time = timezone.now() - timedelta(days=2)
        messages = []
        for i, text in enumerate(lines):
            messages.append(
                Message(
                    channel=channel, author=random.choice(member_users),
                    body=_rich_text(text), created_at=base_time + timedelta(hours=i * 5),
                )
            )
        Message.objects.bulk_create(messages)

        if sample_issue:
            linking_message = Message.objects.create(
                channel=channel, author=random.choice(member_users),
                body=_rich_text(f"We should track this — {sample_issue.summary.lower()}"),
                created_at=timezone.now() - timedelta(hours=3),
            )
            MessageIssueLink.objects.create(message=linking_message, issue=sample_issue, created_task=False)
            system_message = Message.objects.create(
                channel=channel, author=project.lead or random.choice(member_users),
                body=_rich_text(f"✅ Linked to {sample_issue.key}: {sample_issue.summary}"),
                is_system=True, created_at=timezone.now() - timedelta(hours=2, minutes=55),
            )
            MessageIssueLink.objects.create(message=system_message, issue=sample_issue, created_task=False)

    # -- timesheets -------------------------------------------------------------

    def _seed_time_entries(self, project, users):
        if TimeEntry.objects.filter(project=project).exists():
            return
        member_users = list(users.values())
        candidates = list(
            Issue.objects.filter(project=project, issue_type__is_subtask=False).order_by("?")[:12]
        )
        rows = []
        today = timezone.now().date()
        for issue in candidates:
            for _ in range(random.randint(1, 3)):
                work_date = today - timedelta(days=random.randint(0, 6))
                hours = random.choice([0.5, 1, 1.5, 2, 3])
                user = issue.assignee or random.choice(member_users)
                rows.append(
                    TimeEntry(
                        user=user, issue=issue, project=project,
                        description=f"Work on {issue.summary.lower()}",
                        duration=timedelta(hours=hours), is_billable=random.random() < 0.8,
                        is_running=False, created_via=TimeEntry.CreatedVia.MANUAL,
                        work_date=work_date,
                    )
                )
        TimeEntry.objects.bulk_create(rows)

    def _weighted_status(self, status_list, sprints):
        # skew toward To Do/In Progress if there's no active sprint context, else spread out
        weights = []
        for s in status_list:
            if s.category == "todo":
                weights.append(3)
            elif s.category == "in_progress":
                weights.append(2)
            else:
                weights.append(3)
        return random.choices(status_list, weights=weights, k=1)[0]


def _rich_text(text: str) -> dict:
    """Minimal Tiptap/ProseMirror doc JSON wrapping a single paragraph."""
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }
