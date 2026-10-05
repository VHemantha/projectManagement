import hmac

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.issues.models import Issue
from apps.projects.keys import get_issue_or_404
from trackflow.naming import clean_name

from . import services
from .models import PRECHECK_TYPES, AIFeedback, AIFinding, AIPrecheck, JobFolder, folder_id_from

MAX_DIRECTION_ITEMS = 40


def _job(request, key: str) -> Issue:
    issue = get_issue_or_404(key, Issue.objects.select_related("project__client", "status", "drive_folder"))
    if not services.can_open_job(request.user, issue):
        raise PermissionDenied("You can't open this task, so you can't see or run its pre-check.")
    return issue


def _runs(issue):
    return issue.prechecks.select_related("requested_by")


def _full(run):
    run = (
        AIPrecheck.objects.select_related("requested_by")
        .prefetch_related("findings__evidence", "findings__feedback__user")
        .get(pk=run.pk)
    )
    return services.serialize_run(run)


class JobPrecheckView(APIView):
    """GET /api/precheck/jobs/<key>/ — what the job card's pre-check panel shows: whether the
    job is set up, the latest run in full, and the list of earlier runs."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, key):
        issue = _job(request, key)
        runs = list(_runs(issue).filter(kind=AIPrecheck.Kind.PRECHECK)[:20])
        draft = _runs(issue).filter(kind=AIPrecheck.Kind.DRAFT).first()
        return Response({
            "job": issue.key,
            "setup": services.setup_for(issue),
            "latest": _full(runs[0]) if runs else None,
            "history": [services.serialize_run(r, full=False) for r in runs],
            # The latest "draft the Direction Note" request, if any: running, done or failed.
            "draft": {"status": draft.status, "failure_reason": draft.failure_reason, "created_at": draft.created_at} if draft else None,
        })


class JobSetupView(APIView):
    """PUT /api/precheck/jobs/<key>/setup/ — link the job's Drive folder and set its Direction
    Note items."""

    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, key):
        issue = _job(request, key)
        errors = {}
        if "drive_folder_url" in request.data:
            raw = str(request.data.get("drive_folder_url") or "").strip()
            if not raw:
                JobFolder.objects.filter(issue=issue).delete()
            else:
                folder_id = folder_id_from(raw)
                if not folder_id:
                    errors["drive_folder_url"] = ["Paste the link to the job's Google Drive folder."]
                else:
                    JobFolder.objects.update_or_create(
                        issue=issue, defaults={"folder_id": folder_id, "folder_url": raw[:500], "updated_by": request.user}
                    )
        if "precheck_type" in request.data:
            wanted = str(request.data.get("precheck_type") or "general")
            if wanted not in {v for v, _ in PRECHECK_TYPES}:
                errors["precheck_type"] = ["Choose one of the pre-check types offered."]
            elif not JobFolder.objects.filter(issue=issue).update(precheck_type=wanted) and wanted != "general":
                errors["precheck_type"] = ["Link the task's Drive folder first."]
        if "direction_items" in request.data:
            items = request.data.get("direction_items")
            if not isinstance(items, list) or len(items) > MAX_DIRECTION_ITEMS:
                errors["direction_items"] = [f"Give a list of at most {MAX_DIRECTION_ITEMS} items."]
            else:
                texts = []
                for item in items:
                    text = " ".join(str(item.get("text", "") if isinstance(item, dict) else item).split())
                    if text and text not in texts:
                        texts.append(clean_name(text, max_length=500, what="A Direction Note item"))
                services.save_direction_items(issue, texts, request.user)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        issue = _job(request, key)
        return Response(services.setup_for(issue))


class RunListView(APIView):
    """POST /api/precheck/runs/ {job: key} — the "Run pre-check" button. Returns the new run
    at once; progress and the result arrive as events."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        issue = _job(request, str(request.data.get("job", "")))
        refused = _refuse_to_start(issue)
        if refused:
            return refused
        run = services.start_run(issue, request.user)
        return Response(_full(run), status=status.HTTP_201_CREATED)


def _refuse_to_start(issue):
    """The folder is never invented: without it nothing runs. A missing Direction Note is fine —
    the AI drafts one. One run at a time per job."""
    setup = services.setup_for(issue)
    if not setup["ready"]:
        return Response(
            {"detail": "This job needs a Google Drive folder before the pre-check can run.", "missing": setup["missing"]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if _runs(issue).filter(status=AIPrecheck.Status.RUNNING).exists():
        return Response({"detail": "A pre-check is already running for this task."}, status=status.HTTP_409_CONFLICT)
    return None


class JobDraftView(APIView):
    """POST /api/precheck/jobs/<key>/draft/ — ask the AI to draft Direction Note items from the
    client's past jobs and the job folder, without running the pre-check. The items are added
    to the job, marked as AI-drafted, for a person to edit."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, key):
        issue = _job(request, key)
        refused = _refuse_to_start(issue)
        if refused:
            return refused
        run = services.start_run(issue, request.user, kind=AIPrecheck.Kind.DRAFT)
        return Response({"run_id": run.run_id, "status": run.status, "failure_reason": run.failure_reason}, status=status.HTTP_201_CREATED)


class RunDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, run_id):
        run = get_object_or_404(AIPrecheck.objects.select_related("issue"), run_id=run_id)
        if not services.can_open_job(request.user, run.issue):
            raise PermissionDenied("You can't open this task, so you can't see its pre-check.")
        return Response(_full(run))


class FindingDispositionView(APIView):
    """POST /api/precheck/findings/<id>/disposition/ {disposition} — a person's decision on a
    finding: accepted, rejected, not_applicable, needs_clarification, or cleared (undo)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        finding = get_object_or_404(AIFinding.objects.select_related("precheck__issue__project"), pk=pk)
        if not services.can_open_job(request.user, finding.precheck.issue):
            raise PermissionDenied("You can't open this task.")
        disposition = str(request.data.get("disposition", ""))
        if disposition not in AIFeedback.Disposition.values:
            return Response({"disposition": ["Choose accepted, rejected, not_applicable, needs_clarification or cleared."]}, status=400)
        AIFeedback.objects.create(finding=finding, user=request.user, disposition=disposition)
        services._announce(finding.precheck)
        return Response({"id": finding.id, "disposition": services.current_disposition(finding)})


# --- for the precheck-agent service only -------------------------------------------------------

class ServiceTokenPermission(permissions.BasePermission):
    message = "Invalid service token."

    def has_permission(self, request, view):
        token = request.headers.get("X-Precheck-Token", "")
        return bool(settings.PRECHECK_SERVICE_TOKEN) and hmac.compare_digest(token, settings.PRECHECK_SERVICE_TOKEN)


class InternalJobView(APIView):
    """GET /api/precheck/internal/jobs/<id>/ — the job card, Direction Note items and Drive
    folder, read by the agent's load_job node."""

    authentication_classes = []
    permission_classes = [ServiceTokenPermission]

    def get(self, request, issue_id):
        issue = get_object_or_404(Issue.objects.select_related("project__client", "status", "drive_folder"), pk=issue_id)
        return Response(services.job_payload(issue))


class InternalEventView(APIView):
    """POST /api/precheck/internal/events/ — progress, completed and failed events from the
    agent. There is no event that changes a job."""

    authentication_classes = []
    permission_classes = [ServiceTokenPermission]

    def post(self, request):
        accepted = services.record_event(request.data)
        return Response({"accepted": accepted}, status=status.HTTP_200_OK if accepted else status.HTTP_409_CONFLICT)
