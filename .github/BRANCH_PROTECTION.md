# Branch Protection Rules

Recommended GitHub branch protection settings for `main` branch.

## Settings to Enable

### Require Pull Request Reviews
- **Require approvals**: 1 (increase to 2 for critical projects)
- **Dismiss stale reviews**: Enabled
- **Require review from Code Owners**: Enabled (create CODEOWNERS file)

### Require Status Checks
- **Require branches to be up to date**: Enabled
- **Status checks that must pass**:
  - `test`
  - `docker-build`
  - Security check
  - Linting

### Require Conversation Resolution
- **Enabled**: All PR conversations must be resolved before merge

### Require Signed Commits
- **Optional**: Recommended for high-security projects

### Include Administrators
- **Disabled**: Even administrators must follow rules

### Restrict Deletions
- **Enabled**: Prevent accidental branch deletion

### Allow Force Pushes
- **Disabled**: Prevent history rewriting

### Require Linear History
- **Enabled**: Enforce rebase or squash merges (cleaner history)

## Implementation

Configure in GitHub repository settings:
`Settings > Branches > Add rule > Branch name pattern: main`

## CODEOWNERS File

Create `.github/CODEOWNERS`:
```
# Code owners for review
* @seanebones-lang
/src/dms/ @seanebones-lang
/tests/ @seanebones-lang
```

## Workflow

1. Developer creates feature branch from `main`
2. Makes changes and commits
3. Opens pull request to `main`
4. CI checks run automatically
5. Code review required (1+ approval)
6. All conversations resolved
7. Merge to `main` (squash or rebase)

