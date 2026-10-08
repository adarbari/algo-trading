"""The API over the golden ``api_golden`` store (tests/conftest.py), and a test Supabase
project (``tokens``: an ES256 key pair published as a JWKS, the legacy HS256 secret, a token
minter and a JWKS fetch that counts its calls; no network)."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm

from algotrade.storage.configs.files import FileConfigStore
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.conftest import REPO_ROOT
from tests.helpers.api_store import as_user


@pytest.fixture(scope="session")
def ids(api_golden: tuple[ReadStore, dict[str, str]]) -> dict[str, str]:
    return api_golden[1]


@pytest.fixture(scope="session")
def client(api_golden: tuple[ReadStore, dict[str, str]]) -> TestClient:
    return TestClient(
        create_app(ApiSettings("memory://", "config"), api_golden[0], authenticator=as_user())
    )


# A user feature of alice's (config/users/alice/features/vol.toml): hv20 in percent.
USER_FEATURES = """[hv20_pct]
expr = "price_stats.hv20 * 100"
dtype = "float"
unit = "pct_points"
description = "20-session historical volatility, in percent"
null_meaning = "hv20 is null"
"""


# The registry of the multi-user configs: alice, bob and carol are traders who signed up with
# these emails (config/users/<id>/identity.toml), ana is the admin.
USERS_TOML = """[[user]]
id = "ana"
role = "admin"

[[user]]
id = "alice"
role = "trader"

[[user]]
id = "bob"
role = "trader"

[[user]]
id = "carol"
role = "trader"
"""


@pytest.fixture(scope="session")
def user_configs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A config root over the repo's site configs with four users (``USERS_TOML``), each
    with an identity email, where alice has a user feature and carol one of the same name
    with another formula (bob has none)."""
    root: Path = tmp_path_factory.mktemp("configs")
    for item in (REPO_ROOT / "config" / "site").iterdir():
        if item.name != "users.toml" and not item.name.endswith(".local.toml"):
            (root / "site" / item.name).parent.mkdir(exist_ok=True)
            (root / "site" / item.name).symlink_to(item)
    (root / "site" / "users.toml").write_text(USERS_TOML)
    (root / "users" / "alice" / "features").mkdir(parents=True)
    (root / "users" / "alice" / "features" / "vol.toml").write_text(USER_FEATURES)
    (root / "users" / "carol" / "features").mkdir(parents=True)
    # Same name, the opposite sign: the reverse order.
    carol = USER_FEATURES.replace("price_stats.hv20 * 100", "0 - price_stats.hv20 * 100")
    (root / "users" / "carol" / "features" / "vol.toml").write_text(carol)
    for user in ("ana", "alice", "bob", "carol"):
        (root / "users" / user).mkdir(parents=True, exist_ok=True)
        (root / "users" / user / "identity.toml").write_text(f'email = "{user}@example.com"\n')
    return root


@pytest.fixture(scope="session")
def user_client(
    api_golden: tuple[ReadStore, dict[str, str]], user_configs: Path
) -> Callable[[str], TestClient]:
    """A client for ``user`` over configs where alice has a feature."""

    def client_for(user: str) -> TestClient:
        store = replace(api_golden[0], configs=FileConfigStore(user_configs))
        settings = ApiSettings("memory://", str(user_configs), user)
        return TestClient(create_app(settings, store, authenticator=as_user(user)))

    return client_for


SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
KID = "k1"


@dataclass
class Fetch:
    """An injected JWKS fetch: serves ``document`` (or raises ``failure``) and counts calls."""

    document: Mapping[str, Any]
    failure: Exception | None = None
    calls: int = 0

    def __call__(self) -> Mapping[str, Any]:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.document


@dataclass
class Tokens:
    """A test Supabase project: an ES256 key published under ``KID`` and an HS256 secret."""

    private: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    secret: str = "test-hs256-secret-of-at-least-32-bytes"

    def jwk(self, kid: str = KID, alg: str = "ES256") -> dict[str, Any]:
        public = ECAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        return {**public, "kid": kid, "alg": alg, "use": "sig"}

    def jwks(self, *kids: str) -> dict[str, Any]:
        return {"keys": [self.jwk(k) for k in kids or (KID,)]}

    def fetch(self, *kids: str) -> Fetch:
        return Fetch(self.jwks(*kids))

    def claims(self, **changes: Any) -> dict[str, Any]:
        """A signed-in user's claims; a change to ``None`` drops the claim."""
        now = int(time.time())
        base = {
            "iss": ISSUER,
            "aud": "authenticated",
            "sub": "7b1c1d2e-0000-4000-8000-000000000001",
            "role": "authenticated",
            "email": "ana@example.com",
            "iat": now,
            "exp": now + 3600,
            "is_anonymous": False,
        }
        merged = {**base, **changes}
        return {k: v for k, v in merged.items() if v is not None}

    def mint(
        self, alg: str = "ES256", kid: str | None = KID, key: Any = None, **claims: Any
    ) -> str:
        if key is None:
            key = self.secret if alg == "HS256" else self.private
        headers = {"kid": kid} if kid is not None else None
        return jwt.encode(self.claims(**claims), key, algorithm=alg, headers=headers)


@pytest.fixture(scope="session")
def tokens() -> Tokens:
    return Tokens()
