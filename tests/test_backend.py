# Keyring backend tests.

import pytest

import boto3
import botocore

import keyring
import keyrings.codeartifact

from datetime import datetime


@pytest.fixture
def backend():
    backend = keyrings.codeartifact.CodeArtifactBackend()
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
        "https://unknown.amazonaws.com/",
        "https://DOMAIN-ACCOUNT.d.codeartifact.REGION.amazonaws.com/",
        "https://domain-000000000000.d.codeartifact.region.amazonaws.com/maven/repository",
    ],
)
def test_get_credential_invalid_host(backend, service):
    assert keyring.get_credential(service, None) == None


def test_get_credential_unsupported_host(backend):
    assert keyring.get_credential("https://example.com/", None) == None


def test_get_credential_supported_host(backend, monkeypatch):
    def _make_api_call(client, *args, **kwargs):
        # We should only ever call GetAuthorizationToken
        assert args[0] == "GetAuthorizationToken"

        # We should only ever supply these parameters.
        assert args[1]["domain"] == "domain"
        assert args[1]["domainOwner"] == "000000000000"
        assert args[1]["durationSeconds"] == 3600

        tzinfo = datetime.now().astimezone().tzinfo
        expiration = datetime.now(tz=tzinfo)

        return {
            "authorizationToken": "TOKEN",
            "expiration": expiration,
        }

    monkeypatch.setattr(botocore.client.BaseClient, "_make_api_call", _make_api_call)

    credentials = keyring.get_credential(
        "https://domain-000000000000.d.codeartifact.region.amazonaws.com/pypi/repository",
        None,
    )

    assert credentials.username == "aws"
    assert credentials.password == "TOKEN"
