# test_backend.py -- backend tests

import pytest

import keyring

from io import StringIO
from urllib.parse import urlunparse
from botocore.client import BaseClient
from datetime import datetime, timedelta
from keyrings.codeartifact import CodeArtifactBackend


@pytest.fixture
def backend():
    # Find the system-wide keyring.
    original = keyring.get_keyring()

    # Use our keyring backend with an empty configuration.
    backend = CodeArtifactBackend(config_file=StringIO())

    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(original)


def codeartifact_url(domain, owner, region, path):
    netloc = f"{domain}-{owner}.d.codeartifact.{region}.amazonaws.com"
    return urlunparse(("https", netloc, path, "", "", ""))


def codeartifact_pypi_url(domain, owner, region, name):
    return codeartifact_url(domain, owner, region, f"/pypi/{name}/")


def test_set_password_raises(backend):
    with pytest.raises(NotImplementedError):
        keyring.set_password("service", "username", "password")


def test_delete_password_raises(backend):
    with pytest.raises(NotImplementedError):
        keyring.delete_password("service", "username")


@pytest.mark.parametrize(
    "service",
    [
        "https://example.com/",
        "https://unknown.amazonaws.com/",
        codeartifact_url("domain", "owner", "region", "/maven/repo/"),
    ],
)
def test_get_credential_unsupported_host(backend, service):
    assert not keyring.get_credential(service, None)


@pytest.mark.parametrize(
    "service",
    [
        codeartifact_url("domain", "000000000000", "region", "/pkg"),
        codeartifact_url("domain", "000000000000", "region", "/pypi/"),
        codeartifact_url("domain", "000000000000", "region", "/pkg/simple/"),
    ],
)
def test_get_credential_invalid_path(backend, service):
    assert not keyring.get_credential(service, None)


def test_get_credential_supported_host(backend, monkeypatch):
    def _make_api_call(client, *args, **kwargs):
        # We should only ever call GetAuthorizationToken
        assert args[0] == "GetAuthorizationToken"

        # We should only ever supply these parameters.
        assert args[1]["domain"] == "domain"
        assert args[1]["domainOwner"] == "000000000000"
        assert args[1]["durationSeconds"] == 3600

        tzinfo = datetime.now().astimezone().tzinfo
        current_time = datetime.now(tz=tzinfo)

        # Compute the expiration based on the current timestamp.
        expiration = timedelta(seconds=args[1]["durationSeconds"])

        return {
            "authorizationToken": "TOKEN",
            "expiration": current_time + expiration,
        }

    monkeypatch.setattr(BaseClient, "_make_api_call", _make_api_call)
    url = codeartifact_pypi_url("domain", "000000000000", "region", "name")
    credentials = backend.get_credential(url, None)

    assert credentials.username == "aws"
    assert credentials.password == "TOKEN"
