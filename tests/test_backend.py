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

from contextlib import contextmanager
from tempfile import NamedTemporaryFile

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


@contextmanager
def config_from_string(content: str):
    """
    Generates a temporary configuration file from a string.
    """
    with NamedTemporaryFile(mode="w+") as cfg:
        cfg.write(content)
        cfg.flush()
        yield cfg


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
    def make_client(options):
        session = boto3.session.Session(
            profile_name=options.pop("profile_name", None),
            region_name=options.get("region_name"),
        )

        client = session.client("codeartifact", **options)
        stubber = botocore.stub.Stubber(client)

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

        stubber.add_response("get_authorization_token", response, parameters)
        stubber.activate()

        return client

    config = CodeArtifactKeyringConfig(config_file=StringIO())
    backend = CodeArtifactBackend(config=config, make_client=make_client)

    url = codeartifact_pypi_url("domain", "000000000000", "region", "name")
    credentials = backend.get_credential(url, None)

    assert credentials.username == "aws"
    assert credentials.password == "TOKEN"


@pytest.mark.parametrize(
    ("configuration", "assertions"),
    [
        # The effective default options.
        (
            """
            # Empty configuration file.
            """,
            {
                "region_name": "region",
                "profile_name": None,
                "aws_access_key_id": None,
                "aws_secret_access_key": None,
            },
        ),
        # Overriding profile and providing access/secret keys.
        (
            """
            [codeartifact]
            profile_name = PROFILE-NAME
            aws_access_key_id = ACCESS-KEY-ID
            aws_secret_access_key = SECRET-ACCESS-KEY
            """,
            {
                "profile_name": "PROFILE-NAME",
                "aws_access_key_id": "ACCESS-KEY-ID",
                "aws_secret_access_key": "SECRET-ACCESS-KEY",
            },
        ),
        # Only accepting both access/secret keys together.
        (
            """
            [codeartifact]
            aws_access_key_id = ACCESS-KEY-ID
            """,
            {
                "aws_access_key_id": None,
                "aws_secret_access_key": None,
            },
        ),
        # Overriding profile name in multi-block configuration.
        (
            """
            [codeartifact]
            profile_name = DEFAULT-PROFILE

            [codeartifact name="name"]
            profile_name = PROFILE-OVERRIDDEN
            """,
            {
                "profile_name": "PROFILE-OVERRIDDEN",
            },
        ),
        # Turning off SSL verification by default.
        (
            """
            [codeartifact]
            verify = off
            """,
            {
                "verify": False,
            },
        ),
        # Turning on SSL verification using a custom certificate.
        (
            """
            [codeartifact]
            verify = ./path/to/certificate.pem
            """,
            {
                "verify": "./path/to/certificate.pem",
            },
        ),
    ],
)
def test_backend_default_options(configuration, assertions):
    class DummyClient:
        def get_authorization_token(self, *args, **kwargs):
            return {}

    def make_client(options):
        # Assert that we received specific options.
        for key, value in assertions.items():
            assert value == options.get(key)

        # Ignore the rest.
        return DummyClient()

    with config_from_string(configuration) as config_file:
        config = CodeArtifactKeyringConfig(config_file=config_file.name)
        backend = CodeArtifactBackend(config=config, make_client=make_client)
        url = codeartifact_pypi_url("domain", "000000000000", "region", "name")
        credentials = backend.get_credential(url, None)
