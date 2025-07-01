# test_keyring.py -- keyring tests

import pytest

import keyring

from urllib.parse import urlunparse
from datetime import datetime, timedelta

from keyrings.codeartifact import CodeArtifactBackend


def codeartifact_url(domain, owner, region, path):
    netloc = f"{domain}-{owner}.d.codeartifact.{region}.amazonaws.com"
    return urlunparse(("https", netloc, path, "", "", ""))


def codeartifact_pypi_url(domain, owner, region, name):
    return codeartifact_url(domain, owner, region, f"/pypi/{name}/")


@pytest.fixture
def backend():
    backend = CodeArtifactBackend()
    original = keyring.get_keyring()

    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(original)


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
