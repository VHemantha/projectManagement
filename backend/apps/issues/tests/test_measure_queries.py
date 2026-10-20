"""Boards, lists and the main pages load with a fixed number of database queries, however many
tasks there are. The task list once made three extra queries per task (preparer, reviewer,
person responsible): ~900 for a 300-task board."""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Label, Project
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db

URLS = [
    "/api/issues/?project=TST&page_size=300",
    "/api/issues/?page_size=300",
    "/api/projects/",
    "/api/projects/TST/",
    "/api/reports/nav-tree/",
    "/api/teams/",
    "/api/users/",
    "/api/notifications/",
    "/api/activity/recent/",
]


def add_tasks(client, project, people, task, label, n):
    for i in range(n):
        assert client.post("/api/issues/", {"project": "TST", "summary": f"Job {i}", "issue_type_id": task.id}, format="json").status_code == 201
    for i, issue in enumerate(Issue.objects.filter(preparer__isnull=True)):
        issue.assignee, issue.preparer, issue.reviewer, issue.current_responsible = people[i % 6], people[(i + 1) % 6], people[(i + 2) % 6], people[(i + 3) % 6]
        issue.save()
        issue.labels.add(label)


def count(client, url):
    with CaptureQueriesContext(connection) as ctx:
        assert client.get(url).status_code == 200
    return len(ctx.captured_queries)


def test_the_number_of_queries_does_not_grow_with_the_number_of_tasks():
    people = [User.objects.create_user(username=f"u{i}", email=f"u{i}@x.com", password="x") for i in range(6)]
    project = Project.objects.create(organization=Organization.get_solo(), key="TST", name="Test", lead=people[0])
    wf = Workflow.objects.create(project=project)
    WorkflowStatus.objects.create(workflow=wf, name="To do", category="todo", order=0)
    WorkflowStatus.objects.create(workflow=wf, name="Done", category="done", order=1)
    task, _ = IssueType.objects.get_or_create(name="Task", project=None, defaults={"is_subtask": False})
    label = Label.objects.create(project=project, name="L")
    client = APIClient()
    client.force_authenticate(people[0])

    add_tasks(client, project, people, task, label, 5)
    few = {url: count(client, url) for url in URLS}
    add_tasks(client, project, people, task, label, 20)
    many = {url: count(client, url) for url in URLS}
    assert many == few
    assert few["/api/issues/?project=TST&page_size=300"] <= 4
