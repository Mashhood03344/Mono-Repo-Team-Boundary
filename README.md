# Managed Analytics Monorepo

This repository demonstrates a governed multi-team Databricks monorepo with
team-boundary enforcement, pull-request-isolated development deployments,
environment promotion, and immutable release controls.

## Repository Structure

```text
.github/
scripts/
teams/
  data-ingestion/
  monitoring/
  dpt/
```

Each workload team owns its directory under `teams/`.

Shared CI/CD workflows, validation logic, and repository governance under
`.github/**` and `scripts/**` are platform-owned.

## GitHub Organization Teams

The repository uses the following GitHub organization teams:

- `platform`
- `data-ingestion`
- `monitoring`
- `dpt`

Workload teams have repository Write access so that they can collaborate within
the same monorepo.

Repository Write access does not represent ownership of every path in the
repository. Ownership is enforced separately through repository governance and
CI authorization controls.

## Team Boundary Enforcement

Pull requests are validated in two stages.

### 1. Structural Boundary Validation

The structural validator determines which repository boundary is being modified.

It enforces the following rules:

- A pull request may modify at most one `teams/<team>/` boundary.
- A team-scoped pull request cannot also modify platform-controlled paths.
- `.github/**` and `scripts/**` are treated as platform-owned paths.
- Team changes and platform-governance changes must be submitted separately.

Examples:

```text
teams/monitoring/**      -> monitoring boundary
teams/dpt/**             -> dpt boundary
teams/data-ingestion/**  -> data-ingestion boundary

.github/**               -> platform boundary
scripts/**               -> platform boundary
```

### 2. Identity-Aware Authorization

Structural validation alone does not prove that the pull request author owns the
boundary being modified.

A GitHub App is therefore used to verify the pull request author's active
GitHub team membership.

The GitHub App has only:

```text
Organization permission:
Members -> Read-only

Repository access:
None
```

During CI, the workflow generates a short-lived GitHub App installation token
and queries GitHub organization membership.

For a team-scoped pull request:

```text
teams/monitoring/**      -> managed-platform/monitoring
teams/dpt/**             -> managed-platform/dpt
teams/data-ingestion/**  -> managed-platform/data-ingestion
```

For platform-controlled paths:

```text
.github/**               -> managed-platform/platform
scripts/**               -> managed-platform/platform
```

The pull request author must have active membership in the required team.

If the membership lookup fails, returns an inactive membership, or the GitHub
API request cannot be completed, authorization fails closed.

## CODEOWNERS

CODEOWNERS maps protected repository paths to the corresponding GitHub teams.

This provides automatic ownership and review routing for team and platform
changes.

CODEOWNERS is not treated as the sole authorization mechanism.

The effective enforcement model combines CODEOWNERS with CI validation,
identity-aware authorization, required status checks, and repository rulesets.

## Main Branch Governance

The `main` branch is protected using a GitHub repository ruleset.

The current controls include:

- Pull requests are required before merging.
- `Validate Team Boundary` is a required status check.
- Force pushes are blocked.
- Branch deletion is restricted.

Because the current lab uses a single primary platform owner, mandatory human
approval is not currently required by the ruleset.

The required CI authorization check remains the merge gate.

## Databricks Deployment Flow

Development deployments use pull-request isolation.

```text
Feature Branch
      |
      v
Pull Request
      |
      +--> Structural boundary validation
      |
      +--> Identity-aware authorization
      |
      +--> Isolated DEV deployment
      |
      v
Merge to main
      |
      +--> DEV PR cleanup
      |
      v
QA Release
      |
      v
PROD Promotion
```

## DEV Pull Request Isolation

DEV deployments use pull-request-specific Databricks bundle paths.

Example:

```text
/Workspace/Users/<identity>/dev/pr-<PR_ID>/asset_bundle/.bundle/<team>
```

This prevents separate development pull requests from sharing the same
Databricks bundle deployment state.

When the pull request is closed or merged, the DEV cleanup workflow destroys the
corresponding isolated PR resources.

## QA Release Promotion

QA deployment resolves an exact Git commit SHA from the promoted revision.

The workflow:

1. Resolves the requested release revision.
2. Verifies the revision is valid.
3. Checks out the exact SHA.
4. Validates the Databricks bundle.
5. Deploys the bundle to QA.
6. Verifies that the checked-out revision matches the expected release SHA.
7. Creates the immutable QA release tag.

Example:

```text
monitoring/qa-2
```

## PROD Promotion

PROD does not rebuild or redeploy from the latest branch state.

Instead, PROD resolves its source from the previously created QA release tag.

```text
monitoring/qa-2
        |
        v
Exact Git SHA
        |
        v
PROD deployment
        |
        v
monitoring/prod-2
```

This ensures that PROD receives the same Git revision that was validated and
deployed in QA.

## Immutable Release Tags

Release tags follow a team/environment naming convention.

Examples:

```text
monitoring/qa-2
monitoring/prod-2

dpt/qa-2
dpt/prod-2

data-ingestion/qa-2
data-ingestion/prod-2
```

A GitHub tag ruleset protects tags matching:

```text
*/qa-*
*/prod-*
```

The ruleset currently enforces:

- New release-tag creation is allowed.
- Existing protected tags cannot be updated.
- Existing protected tags cannot be deleted.
- Force pushes to protected tags are blocked.

This creates immutable QA and PROD release references.

## Release Promotion Invariant

For a single promotion:

```text
QA tag SHA == PROD tag SHA
```

For example:

```text
monitoring/qa-2
monitoring/prod-2
```

were both created from the same immutable source revision.

The PROD workflow therefore promotes the exact artifact revision validated in
QA instead of rebuilding from current repository state.

## Security Model

The repository intentionally separates repository access from path ownership.

A workload engineer may have repository Write access while still being
unauthorized to modify another team's deployment boundary.

The effective authorization model is:

```text
GitHub Teams
      +
CODEOWNERS
      +
Repository Rulesets
      +
Structural Path Validation
      +
GitHub App Membership Authorization
      +
Required Status Checks
      =
Merge-Time Team Boundary Enforcement
```

This means repository-level Write access alone is not enough to successfully
promote unauthorized changes into `main`.

## Validation Performed

The controls were tested with two separate GitHub identities.

### Negative Authorization Test

A user belonging to the `monitoring` team attempted to modify:

```text
teams/dpt/**
```

Observed flow:

```text
monitoring member
        |
        v
modifies teams/dpt/**
        |
        v
structural validator detects dpt boundary
        |
        v
required GitHub team = dpt
        |
        v
PR author is not a dpt member
        |
        v
identity authorization fails
        |
        v
required status check fails
        |
        v
merge blocked
```

The workflow returned an authorization failure identifying that the pull request
author was not a member of `managed-platform/dpt`.

### Positive Authorization Test

The same monitoring-only user modified:

```text
teams/monitoring/**
```

Observed flow:

```text
monitoring member
        |
        v
modifies teams/monitoring/**
        |
        v
structural validator detects monitoring boundary
        |
        v
required GitHub team = monitoring
        |
        v
active membership confirmed
        |
        v
identity authorization passes
```

This validated both the allow and deny paths of the team authorization control.

## Release Tag Protection Validation

Protected release-tag behavior was tested directly.

### Update Attempt

An existing protected tag was force-moved locally and pushed.

Example:

```text
dpt/qa-1
```

GitHub rejected the update with a repository ruleset violation:

```text
Cannot update this protected ref.
```

The remote tag remained on its original SHA.

### Deletion Attempt

A remote deletion of the same protected tag was attempted.

GitHub rejected the operation:

```text
Cannot delete this tag.
```

The tag remained present remotely.

### Creation Test

The normal release workflow successfully created new protected tags:

```text
monitoring/qa-2
monitoring/prod-2
```

This proved the intended behavior:

```text
New protected tag creation -> ALLOWED
Protected tag update        -> BLOCKED
Protected tag deletion      -> BLOCKED
```

## GitHub App Authentication

Identity authorization uses a GitHub App rather than a personal access token.

This avoids tying the authorization mechanism to a long-lived credential owned
by an individual user.

The GitHub App uses:

```text
Organization permissions:
Members -> Read-only

Repository access:
None
```

The workflow generates a short-lived installation token only when membership
authorization is required.

### GitHub App authentication compatibility note

The GitHub App currently uses the numeric App ID when generating the installation token.

Client ID authentication was tested in two independent ways:

1. Using `actions/create-github-app-token`
2. Using a directly generated RS256 JWT against the GitHub API

Both approaches returned:

```text
401
'Issuer' claim ('iss') must be an Integer

### Authentication Compatibility Note

The implementation currently uses the numeric GitHub App ID when generating the
installation token.

Client-ID-based JWT authentication was tested both through
`actions/create-github-app-token` and through a direct independently generated
RS256 JWT.

In the tested GitHub runtime, both Client ID approaches returned:

```text
401
'Issuer' claim ('iss') must be an Integer
```

The numeric App ID was therefore retained as a compatibility workaround.

The architecture still uses a GitHub App, short-lived installation tokens, and
least-privilege organization permissions.

## Sparse Checkout

Team developers can use Git sparse checkout to reduce the local working tree to
their team directory.

Example for a monitoring engineer:

```bash
git sparse-checkout init --cone
git sparse-checkout set teams/monitoring
```

Result:

```text
teams/monitoring
```

Sparse checkout is used only for developer ergonomics.

It is **not** considered a security boundary.

A user with repository access can still retrieve other repository paths.
Security enforcement occurs through merge-time identity authorization.

## Test Branches

Some test branches are intentionally retained as evidence of specific governance
and deployment scenarios.

Examples include branches used to validate:

- DPT boundary rejection for a monitoring-only user.
- Monitoring boundary authorization success.
- Team deployment boundaries.
- Data-ingestion boundaries.
- GitHub App identity authorization.

These branches are historical test evidence only.

The authoritative implementation remains the current `main` branch.

## Key Design Principles

The project follows several platform-engineering principles.

### Least Privilege

The GitHub App receives only the organization membership permission required for
authorization.

### Fail Closed

Membership authorization failures prevent the required CI check from passing.

### Separation of Concerns

Structural repository validation and identity authorization are implemented as
separate responsibilities.

### Immutable Promotion

QA and PROD promotion use exact Git revisions rather than rebuilding from moving
branch state.

### Defense in Depth

No single mechanism is relied upon for team ownership.

Repository governance combines:

```text
GitHub organization teams
CODEOWNERS
repository rulesets
path validation
identity authorization
required status checks
immutable tags
```

### Runtime Validation

Controls were not considered complete solely because their configuration looked
correct.

Positive and negative runtime tests were performed to verify actual enforcement
behavior.

## Current Scope

The project currently demonstrates:

- Multi-team GitHub monorepo governance.
- GitHub organization team-based ownership.
- CODEOWNERS integration.
- Identity-aware merge authorization.
- GitHub App authentication.
- Short-lived installation tokens.
- Least-privilege membership lookup.
- Required CI authorization checks.
- Main-branch rulesets.
- Pull-request-isolated Databricks DEV deployments.
- Automatic DEV PR cleanup.
- Exact-SHA QA deployment.
- QA-to-PROD immutable promotion.
- Environment-specific Databricks Asset Bundles.
- Immutable release-tag enforcement.
- Positive and negative security validation.
- Sparse checkout for team-local developer workflows.

## Final Architecture

```text
                    GitHub Organization
                           |
          +----------------+----------------+
          |                |                |
        dpt          monitoring      data-ingestion
          |                |                |
          +----------------+----------------+
                           |
                    Shared Repository
                           |
              +------------+------------+
              |                         |
         teams/<team>/            Platform Paths
                              .github/** + scripts/**
              |                         |
              +------------+------------+
                           |
                  Pull Request Validation
                           |
              +------------+------------+
              |                         |
       Structural Boundary       Identity Authorization
            Validation              GitHub App
              |                         |
              +------------+------------+
                           |
                  Required Status Check
                           |
                           v
                          main
                           |
                           v
                 PR-Isolated DEV Cleanup
                           |
                           v
                     QA Deployment
                    Exact Commit SHA
                           |
                           v
                     team/qa-N
                           |
                           v
                    PROD Promotion
                     Same Git SHA
                           |
                           v
                    team/prod-N
```

## Project Status

The primary governance, authorization, deployment, promotion, and release
immutability objectives of this proof of concept have been implemented and
validated.

Further work should be driven by a concrete production requirement rather than
adding additional controls solely for demonstration purposes.