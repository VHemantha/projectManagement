"""GET /api/users/hierarchy/ — who sits where, for the People page's org chart.

There is no reporting-line field (no "manager" on a user), so the hierarchy is derived:
- organisation admins (staff) at the top;
- under them, each team with its leads and then its members (sub-teams carry parent_id so the
  chart can nest them under their parent team);
- workers who are in no team in a final "no team" group.

Admins are only shown at the top (with the teams they belong to), not repeated inside teams.
A worker in several teams appears under each of them.
"""
from rest_framework import generics, permissions
from rest_framework.response import Response

from apps.teams.models import Team, TeamMembership

from .models import User
from .serializers import UserSerializer


def _node(request, user, role: str, team_names: list[str]) -> dict:
    return {**UserSerializer(user, context={"request": request}).data, "role": role, "teams": team_names}


class UserHierarchyView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        users = list(User.objects.filter(is_active=True).order_by("display_name", "id"))
        memberships = list(
            TeamMembership.objects.filter(user__is_active=True).select_related("team").order_by("team__name")
        )
        teams_of: dict[int, list[str]] = {}
        for m in memberships:
            teams_of.setdefault(m.user_id, []).append(m.team.name)

        admins = [_node(request, u, "admin", teams_of.get(u.id, [])) for u in users if u.is_staff]
        by_id = {u.id: u for u in users}

        teams = []
        for team in Team.objects.order_by("name"):
            rows = [
                m for m in memberships if m.team_id == team.id and m.user_id in by_id and not by_id[m.user_id].is_staff
            ]
            rows.sort(key=lambda m: (by_id[m.user_id].display_name.lower(), m.user_id))
            teams.append(
                {
                    "id": team.id,
                    "name": team.name,
                    "avatar_color": team.avatar_color,
                    "parent_id": team.parent_id,
                    "leads": [
                        _node(request, by_id[m.user_id], "lead", teams_of[m.user_id])
                        for m in rows
                        if m.role == TeamMembership.Role.LEAD
                    ],
                    "members": [
                        _node(request, by_id[m.user_id], "member", teams_of[m.user_id])
                        for m in rows
                        if m.role != TeamMembership.Role.LEAD
                    ],
                }
            )

        no_team = [_node(request, u, "member", []) for u in users if not u.is_staff and u.id not in teams_of]
        return Response(
            {
                "derived": True,
                "basis": "Admins are organisation staff; everyone else is grouped by team membership "
                "(team leads first). There is no reporting-line field.",
                "admins": admins,
                "teams": teams,
                "no_team": no_team,
            }
        )
