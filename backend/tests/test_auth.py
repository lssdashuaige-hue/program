import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.auth import (
    AuthenticationServiceUnavailable,
    AuthenticatedUser,
    InvalidAccessToken,
    SupabaseAuthService,
    require_authenticated_user,
)
from app.config import Settings, get_settings


def test_supabase_auth_validates_with_auth_server() -> None:
    user_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/user"
        assert request.headers["apikey"] == "publishable-key"
        assert request.headers["authorization"] == "Bearer user-access-token"
        return httpx.Response(
            200,
            json={"id": str(user_id), "email": "user@example.com"},
        )

    service = SupabaseAuthService(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        transport=httpx.MockTransport(handler),
    )

    user = asyncio.run(service.authenticate("user-access-token"))

    assert user == AuthenticatedUser(
        id=user_id,
        access_token="user-access-token",
        email="user@example.com",
    )
    assert "user-access-token" not in repr(user)


def test_supabase_auth_rejects_invalid_token_without_leaking_it() -> None:
    service = SupabaseAuthService(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(401, json={"message": "bad token"})
        ),
    )

    with pytest.raises(InvalidAccessToken) as raised:
        asyncio.run(service.authenticate("private-invalid-token"))

    assert "private-invalid-token" not in str(raised.value)


def test_supabase_auth_fails_closed_on_invalid_upstream_shape() -> None:
    service = SupabaseAuthService(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"email": "missing-id"})
        ),
    )

    with pytest.raises(AuthenticationServiceUnavailable):
        asyncio.run(service.authenticate("user-access-token"))


def test_missing_bearer_is_rejected_before_configuration_check() -> None:
    test_app = FastAPI()

    @test_app.get("/private")
    async def private(
        user: AuthenticatedUser = Depends(require_authenticated_user),
    ) -> dict[str, str]:
        return {"id": str(user.id)}

    test_app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)

    response = TestClient(test_app).get("/private")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
