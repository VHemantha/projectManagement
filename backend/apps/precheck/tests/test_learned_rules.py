"""Teaching the pre-check what it missed, for a type of check (AFIT, 29 Oct 2026): a rule taught once
reaches every later pre-check of that type (and entity type), from a task or from the AI rules page."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.precheck import services
from apps.precheck.models import JobFolder, PrecheckLesson
from apps.teams.models import Team, TeamMembership

from .test_direction_drafting import make_job

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_agent(settings, monkeypatch):
    settings.PRECHECK_SERVICE_TOKEN = "test-token"
    monkeypatch.setattr(services, "_call_agent", lambda path, body: {})


def person(name, staff=False):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="x", display_name=name.title(), is_staff=staff)


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def set_type(issue, nature, entity=""):
    folder = JobFolder.objects.get(issue=issue)
    folder.precheck_type, folder.accountant_settings = nature, {"entity_type": entity} if entity else {}
    folder.save()


def offered(issue):
    return [lesson["note"] for lesson in services.job_payload(Issue.objects.get(pk=issue.pk))["lessons"]]


def test_a_rule_from_the_ai_rules_page_reaches_every_later_check_of_that_type():
    admin, owner = person("ada", staff=True), person("owen")
    smith, jones, cafe = make_job(owner, "Smith", "SmithRent"), make_job(owner, "Jones", "JonesRent"), make_job(owner, "Cafe", "CafeBiz")
    set_type(smith, "residential_rental")
    set_type(jones, "residential_rental", "trust")
    set_type(cafe, "general")
    r = api(admin).post("/api/precheck/lessons/", {"kind": "missed", "item": "Landlord insurance",
                                                  "note": "Ask for the landlord insurance schedule for each rental property.",
                                                  "precheck_type": "residential_rental"}, format="json")
    assert r.status_code == 201 and r.data["status"] == "active" and r.data["precheck_type_label"] == "Residential rental"
    assert r.data["source"] == "library" and r.data["task"] == ""
    trust_only = api(admin).post("/api/precheck/lessons/", {"kind": "missed", "note": "Ask for the trust deed and any variations.",
                                                           "precheck_type": "", "entity_type": "trust"}, format="json")
    assert trust_only.status_code == 201 and trust_only.data["entity_label"] == "Trust"
    rule = "Ask for the landlord insurance schedule for each rental property."
    deed = "Ask for the trust deed and any variations."
    assert rule in offered(smith) and deed not in offered(smith)  # a rental, not a trust
    assert rule in offered(jones) and deed in offered(jones)  # a rental trust: both
    assert rule not in offered(cafe) and deed not in offered(cafe)  # another type of check


def test_when_the_ai_decides_the_type_its_last_run_counts_and_before_any_run_every_type_is_offered():
    admin, owner = person("ada", staff=True), person("owen")
    issue = make_job(owner, "Smith", "SmithRent")  # "Decide from the questionnaire"
    services.add_rule(admin, kind="missed", item="", note="Rental rule: ask for the insurance schedule.", precheck_type="residential_rental")
    services.add_rule(admin, kind="missed", item="", note="Business rule: ask for the stock count.", precheck_type="general")
    assert len(offered(issue)) == 2  # no run yet: the agent picks by meaning
    from .test_requests_and_lessons import finished  # a run that found a residential rental

    finished(issue, owner)
    assert offered(issue) == ["Rental rule: ask for the insurance schedule."]


def test_teaching_from_a_task_can_name_the_type_of_check():
    owner = person("owen")
    issue = make_job(owner, "Smith", "SmithRent")
    r = api(owner).post(f"/api/precheck/jobs/{issue.key}/lessons/", {"kind": "missed", "item": "Bond", "note": "Ask whether a bond was lodged.",
                                                                    "scope": "client", "precheck_type": "residential_rental", "entity_type": "ltc"},
                        format="json")
    assert r.status_code == 201 and (r.data["precheck_type"], r.data["entity_type"]) == ("residential_rental", "ltc")
    bad = api(owner).post(f"/api/precheck/jobs/{issue.key}/lessons/", {"kind": "missed", "note": "Something else.", "precheck_type": "car"}, format="json")
    assert bad.status_code == 400


def test_anyone_may_propose_a_rule_a_lead_or_admin_approves_it():
    staff, lead = person("sam"), person("lena")
    team = Team.objects.create(organization=make_job(lead, "Smith", "SmithRent").project.organization, name="Rentals")
    TeamMembership.objects.create(team=team, user=lead, role="lead")
    r = api(staff).post("/api/precheck/lessons/", {"kind": "missed", "note": "Ask for the depreciation schedule."}, format="json")
    assert r.status_code == 201 and r.data["status"] == "pending"
    lesson = PrecheckLesson.objects.get(pk=r.data["id"])
    assert api(staff).patch(f"/api/precheck/lessons/{lesson.pk}/", {"status": "active"}, format="json").status_code == 403
    assert api(lead).patch(f"/api/precheck/lessons/{lesson.pk}/", {"status": "active"}, format="json").status_code == 200
    listing = api(lead).get("/api/precheck/lessons/?status=active").data
    assert listing["can_approve"] and [x["id"] for x in listing["lessons"]] == [lesson.pk]
    assert api(staff).get("/api/precheck/lessons/").data["can_approve"] is False
    assert api(staff).post("/api/precheck/lessons/", {"kind": "missed", "note": "no"}, format="json").status_code == 400
