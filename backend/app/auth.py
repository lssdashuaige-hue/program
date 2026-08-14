from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings


AUTH_REQUEST_TIMEOUT_SECONDS = 5.0
_bearer = HTTPBearer(auto_error=False)


class InvalidAccessToken(RuntimeError):
    """Raised when Supabase Auth rejects a user access token."""


class AuthenticationServiceUnavailable(RuntimeError):
    """Raised when PAS cannot safely validate a user with Supabase Auth."""


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: UUID
    access_token: str = field(repr=False)


class SupabaseAuthService:
    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._supabase_url = supabase_url.rstrip("/")
        self._publishable_key = publishable_key
        self._transport = transport

    async def authenticate(self, access_token: str) -> AuthenticatedUser:
        try:
            async with httpx.AsyncClient(
                timeout=AUTH_REQUEST_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"{self._supabase_url}/auth/v1/user",
                    headers={
                        "Accept": "application/json",
                        "apikey": self._publishable_key,
                        "Authorization": f"Bearer {access_token}",
                    },
                )
        except httpx.RequestError as error:
            raise AuthenticationServiceUnavailable(
                "Supabase Auth could not be reached."
            ) from error

        if response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }:
            raise InvalidAccessToken("Supabase Auth rejected the access token.")

        if response.status_code != status.HTTP_200_OK:
            raise AuthenticationServiceUnavailable(
                "Supabase Auth returned an unexpected response."
            )

        try:
            payload = response.json()
            user_id = UUID(str(payload["id"]))
        except (KeyError, TypeError, ValueError) as error:
            raise AuthenticationServiceUnavailable(
                "Supabase Auth returned an invalid user response."
            ) from error

        return AuthenticatedUser(id=user_id, access_token=access_token)


def _authentication_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="请先登录后再访问你的探索记录。",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_authenticated_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    if (
        credentials is None
        or credentials.scheme.casefold() != "bearer"
        or not credentials.credentials
    ):
        raise _authentication_required()

    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAS 的登录验证服务尚未配置。",
        )

    service = SupabaseAuthService(
        supabase_url=settings.supabase_url,
        publishable_key=settings.supabase_publishable_key,
    )
    try:
        return await service.authenticate(credentials.credentials)
    except InvalidAccessToken as error:
        raise _authentication_required() from error
    except AuthenticationServiceUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAS 暂时无法确认登录状态，请稍后重试。",
        ) from error


async def optional_authenticated_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser | None:
    """Validate a supplied bearer token while preserving anonymous exploration."""

    if credentials is None:
        return None
    if credentials.scheme.casefold() != "bearer" or not credentials.credentials:
        raise _authentication_required()
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAS 的登录验证服务尚未配置。",
        )

    service = SupabaseAuthService(
        supabase_url=settings.supabase_url,
        publishable_key=settings.supabase_publishable_key,
    )
    try:
        return await service.authenticate(credentials.credentials)
    except InvalidAccessToken as error:
        raise _authentication_required() from error
    except AuthenticationServiceUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAS 暂时无法确认登录状态，请稍后重试。",
        ) from error
