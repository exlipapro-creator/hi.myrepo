# Security — Authentication & Authorization

## Authentication

hi.myrepo uses JWT-based authentication with role-based access control (RBAC).

### Token Structure

```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "role": "admin",
  "org_id": "org-uuid",
  "autonomy_level": 2,
  "exp": 1735689600,
  "iss": "hi.myrepo"
}
```

### Roles

| Role | Permissions |
|------|------------|
| admin | Full access to all resources, manage users, configure policies |
| member | Create/manage projects, view incidents, approve runbooks |
| viewer | Read-only access to all resources |

### Autonomy Levels

Users have an autonomy level that determines what actions they can authorize:

- Level 0-1: Observe only
- Level 2: Can approve recommendations
- Level 3: Can authorize guarded actions
- Level 4: Can authorize conditional autonomy

## Authorization

### API Endpoints

All API endpoints (except `/health` and `/`) require a valid JWT token in the `Authorization: Bearer <token>` header.

### Role-Based Access

Use the `require_role()` dependency to restrict endpoints:

```python
from app.security.auth import require_role

@router.delete("/{project_id}")
async def delete_project(
    project_id: uuid.UUID,
    user: TokenData = Depends(require_role("admin")),
):
    ...
```

### Autonomy-Based Access

Use `require_autonomy_level()` to restrict based on autonomy:

```python
from app.security.auth import require_autonomy_level

@router.post("/approve")
async def approve_action(
    user: TokenData = Depends(require_autonomy_level(3)),
):
    ...
```

## Security Controls

- **SSRF Protection**: URL validation blocks private networks, localhost, metadata endpoints
- **Rate Limiting**: Per-IP rate limiting via SlowAPI
- **Input Validation**: Pydantic models validate all inputs
- **Secret Isolation**: Secrets never appear in logs, UI, or AI prompts
- **Audit Logging**: Every consequential action is recorded
- **Webhook Verification**: Signature validation for GitHub/Vercel webhooks
- **Replay Protection**: Idempotency keys prevent duplicate event processing
