# test_backend.py -- backend tests

import pytest

import os
import boto3
import botocore.stub

import keyring

from io import StringIO
from pathlib import Path
from urllib.parse import urlunparse
from datetime import datetime, timedelta

from keyrings.codeartifact import CodeArtifactBackend, CodeArtifactKeyringConfig

REGION_NAME = "ca-central-1"
CONFIG_DIR = Path(__file__).parent / "config"


def current_time():
    # Compute time zone information to calculate offset.
    tzinfo = datetime.now().astimezone().tzinfo
    return datetime.now(tz=tzinfo)


def codeartifact_url(domain, owner, region, path):
    netloc = f"{domain}-{owner}.d.codeartifact.{region}.amazonaws.com"
    return urlunparse(("https", netloc, path, "", "", ""))


def codeartifact_pypi_url(domain, owner, region, name):
    return codeartifact_url(domain, owner, region, f"/pypi/{name}/")


class StubbingSession:
    class Client:
        def __init__(self, service, **kwargs):
            self.client = boto3.client(service, **kwargs)
            self.stub = botocore.stub.Stubber(self.client)

        def stub():
            return self.stub

        def __getattr__(self, attr):
            delegate = getattr(self.client, attr)

            def wrapper(*args, **kwargs):
                with self.stub as stub:
                    return delegate(*args, **kwargs)

            return delegate

    def __init__(self, **kwargs):
        self.default_kwargs = kwargs
        self.clients = {}

    def client(self, service, **client_kwargs):
        kwargs = {}
        kwargs.update(self.default_kwargs)
        kwargs.update(client_kwargs)

        if not self.clients.get(service):
            self.clients[service] = StubbingSession.Client(service, **kwargs)

        return self.clients[service]


@pytest.fixture
def default_backend():
    backend = CodeArtifactBackend()
    original = keyring.get_keyring()

    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(original)


def test_set_password_raises(default_backend):
    with pytest.raises(NotImplementedError):
        keyring.set_password("service", "username", "password")


def test_delete_password_raises(default_backend):
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
def test_get_credential_unsupported_host(default_backend, service):
    assert not keyring.get_credential(service, None)


@pytest.mark.parametrize(
    "service",
    [
        codeartifact_url("domain", "000000000000", "region", "/pkg"),
        codeartifact_url("domain", "000000000000", "region", "/pypi/"),
        codeartifact_url("domain", "000000000000", "region", "/pkg/simple/"),
    ],
)
def test_get_credential_invalid_path(default_backend, service):
    assert not keyring.get_credential(service, None)


def test_get_credential_supported_host():
    session = StubbingSession(region_name=REGION_NAME)
    client = session.client("codeartifact", region_name=REGION_NAME)

    parameters = {
        "domain": "domain",
        "domainOwner": "000000000000",
        "durationSeconds": 3600,
    }

    # The response we expect from the API.
    response = {
        "authorizationToken": "TOKEN",
        # Compute the expiration based on the current timestamp.
        "expiration": current_time() + timedelta(seconds=3600),
    }

    client.stub.add_response("get_authorization_token", response, parameters)
    client.stub.activate()

    config = CodeArtifactKeyringConfig(config_file=StringIO())
    backend = CodeArtifactBackend(config=config, session=session)

    url = codeartifact_pypi_url("domain", "000000000000", "region", "name")
    credentials = backend.get_credential(url, None)

    assert credentials.username == "aws"
    assert credentials.password == "TOKEN"

    client.stub.assert_no_pending_responses()