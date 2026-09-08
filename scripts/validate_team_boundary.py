# Validator for Team Boundaries in a Monorepo

from pathlib import PurePosixPath
from typing import Iterable, Set


TEAM_ROOT = "teams"

PLATFORM_ROOTS = {
    ".github",
    "scripts",
}


class TeamBoundaryValidationError(Exception):
    """Raised when changed files violate monorepo ownership boundaries."""


def normalize_path(file_path: str) -> str:
    """
    Normalize Windows-style paths and remove leading/trailing slashes.
    """
    return file_path.replace("\\", "/").strip("/")


def extract_team_from_path(file_path: str) -> str | None:
    """
    Return the team name from a path like:

        teams/data-ingestion/src/query.sql

    Returns None when the path is outside teams/.
    """

    normalized = normalize_path(file_path)
    parts = PurePosixPath(normalized).parts

    if len(parts) < 2:
        return None

    if parts[0] != TEAM_ROOT:
        return None

    team_name = parts[1].strip()

    if not team_name:
        raise TeamBoundaryValidationError(
            f"Invalid team path: {file_path}"
        )

    return team_name


def is_platform_path(file_path: str) -> bool:
    """
    Return True when the file belongs to a protected platform-owned path.

    Examples:
        .github/workflows/validate.yml
        scripts/helper.py
    """

    normalized = normalize_path(file_path)
    parts = PurePosixPath(normalized).parts

    if not parts:
        return False

    return parts[0] in PLATFORM_ROOTS


def get_affected_teams(changed_files: Iterable[str]) -> Set[str]:
    """
    Determine which teams/<team>/ boundaries are affected.
    """

    affected_teams = set()

    for file_path in changed_files:
        team = extract_team_from_path(file_path)

        if team:
            affected_teams.add(team)

    return affected_teams


def get_platform_files(changed_files: Iterable[str]) -> list[str]:
    """
    Return all changed files that belong to protected platform paths.
    """

    return [
        file_path
        for file_path in changed_files
        if is_platform_path(file_path)
    ]


def validate_boundaries(changed_files: Iterable[str]) -> tuple[str, str | None]:
    """
    Validate monorepo ownership boundaries.

    Returns:
        ("TEAM", team_name)
        ("PLATFORM", None)
        ("OTHER", None)

    Raises:
        TeamBoundaryValidationError when boundaries are violated.
    """

    changed_files = list(changed_files)

    if not changed_files:
        raise TeamBoundaryValidationError(
            "No changed files were provided."
        )

    affected_teams = get_affected_teams(changed_files)
    platform_files = get_platform_files(changed_files)

    # Rule 1:
    # A PR cannot modify more than one team boundary.
    if len(affected_teams) > 1:
        teams = "\n".join(
            f"  - {team}" for team in sorted(affected_teams)
        )

        raise TeamBoundaryValidationError(
            "PR modifies multiple team deployment boundaries:\n"
            f"{teams}\n\n"
            "A pull request may modify only one teams/<team>/ boundary."
        )

    # Rule 2:
    # A team-scoped change cannot modify platform-controlled paths.
    if affected_teams and platform_files:
        team = next(iter(affected_teams))

        files = "\n".join(
            f"  - {file_path}" for file_path in platform_files
        )

        raise TeamBoundaryValidationError(
            f"Team-scoped PR for '{team}' also modifies "
            "platform-controlled paths:\n"
            f"{files}\n\n"
            "Team changes and platform-governance changes "
            "must be submitted separately."
        )

    # Exactly one team and no platform paths.
    if len(affected_teams) == 1:
        return "TEAM", next(iter(affected_teams))

    # Platform-only PR.
    if platform_files:
        return "PLATFORM", None

    # Files outside both known boundaries.
    return "OTHER", None


def run_validation(changed_files: Iterable[str]) -> int:
    """
    CLI-friendly wrapper.

    Returns:
        0 on success
        1 on validation failure
    """

    try:
        change_type, team = validate_boundaries(changed_files)

        if change_type == "TEAM":
            print(f"Detected team boundary: {team}")
            print("PASS: Team boundary validation succeeded.")

        elif change_type == "PLATFORM":
            print("Detected platform-owned change.")
            print("PASS: Platform boundary validation succeeded.")
            print(
                "Platform approval must be enforced "
                "through GitHub governance."
            )

        else:
            print(
                "No team or protected platform boundary "
                "was modified."
            )
            print("PASS: Boundary validation succeeded.")

        return 0

    except TeamBoundaryValidationError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    import sys

    raise SystemExit(
        run_validation(sys.argv[1:])
    )