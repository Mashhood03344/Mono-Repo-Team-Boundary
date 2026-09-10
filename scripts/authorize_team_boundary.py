# scripts/authorize_team_boundary.py

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import PurePosixPath
from typing import Iterable

TEAM_ROOT = "teams"

PLATFORM_ROOTS = {
    ".github",
    "scripts",
}

ORGANIZATION = "managed-platform"


class TeamBoundaryAuthorizationError(Exception):
    """Raised when a user is not authorized for a repository boundary."""


def normalize_path(file_path: str) -> str:
    return file_path.replace("\\", "/").strip("/")


def extract_required_team(changed_files: Iterable[str]) -> str | None:
    """
    Determine which GitHub team must authorize the change.

    Assumes structural boundary validation has already passed.
    """

    changed_files = list(changed_files)

    team_names = set()
    platform_change = False

    for file_path in changed_files:
        normalized = normalize_path(file_path)
        parts = PurePosixPath(normalized).parts

        if not parts:
            continue

        if parts[0] == TEAM_ROOT and len(parts) >= 2:
            team_names.add(parts[1])

        if parts[0] in PLATFORM_ROOTS:
            platform_change = True

    if len(team_names) == 1:
        return next(iter(team_names))

    if platform_change:
        return "platform"

    return None


def get_team_membership(
    organization: str,
    team_slug: str,
    username: str,
    token: str,
) -> dict:
    """
    Query GitHub for the user's membership in the required team.
    """

    url = (
        f"https://api.github.com/orgs/{organization}"
        f"/teams/{team_slug}/memberships/{username}"
    )

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "managed-platform-boundary-authorization",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)

    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise TeamBoundaryAuthorizationError(
                f"User '{username}' is not a member of "
                f"'{organization}/{team_slug}'."
            ) from exc

        raise TeamBoundaryAuthorizationError(
            f"GitHub membership lookup failed with HTTP {exc.code}."
        ) from exc

    except urllib.error.URLError as exc:
        raise TeamBoundaryAuthorizationError(
            f"GitHub membership lookup failed: {exc.reason}"
        ) from exc


def authorize(
    changed_files: Iterable[str],
    username: str,
    token: str,
) -> int:
    try:
        required_team = extract_required_team(changed_files)

        if required_team is None:
            print(
                "No protected team or platform boundary requires "
                "identity authorization."
            )
            print("PASS: Identity authorization not required.")
            return 0

        print(f"Required GitHub team: {required_team}")
        print(f"Pull request author: {username}")

        membership = get_team_membership(
            organization=ORGANIZATION,
            team_slug=required_team,
            username=username,
            token=token,
        )

        state = membership.get("state")

        if state != "active":
            raise TeamBoundaryAuthorizationError(
                f"User '{username}' does not have active membership in "
                f"'{ORGANIZATION}/{required_team}'. "
                f"Membership state: {state!r}"
            )

        print(
            f"PASS: '{username}' has active membership in "
            f"'{ORGANIZATION}/{required_team}'."
        )
        return 0

    except TeamBoundaryAuthorizationError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    changed_files = sys.argv[1:]

    username = os.environ.get("PR_AUTHOR")
    token = os.environ.get("BOUNDARY_TOKEN")

    if not username:
        print("ERROR: PR_AUTHOR environment variable is required.")
        raise SystemExit(1)

    if not token:
        print("ERROR: BOUNDARY_TOKEN environment variable is required.")
        raise SystemExit(1)

    raise SystemExit(
        authorize(
            changed_files=changed_files,
            username=username,
            token=token,
        )
    )