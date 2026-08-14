import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings


_bearer = HTTPBearer(auto_error=False)
_MIN_ADMIN_TOKEN_LENGTH = 24


def require_evals_admin(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not settings.pas_evals_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    secret = settings.pas_evals_admin_token
    expected = secret.get_secret_value() if secret is not None else ""
    if len(expected) < _MIN_ADMIN_TOKEN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal evaluations are not configured.",
        )

    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Evaluation administrator authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(
        credentials.credentials.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Evaluation administrator authentication failed.",
        )
