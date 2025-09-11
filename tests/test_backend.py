# test_backend.py -- backend tests

from contextlib import contextmanager
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlunparse

import pytest
from botocore.stub import Stubber

from keyrings.codeartifact import (
    CodeArtifactBackend,
    CodeArtifactKeyringConfig,
    make_codeartifact_client,
)

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


def test_get_credential_supported_host():
    def make_client(options):
        client = make_codeartifact_client(options)
        stubber = Stubber(client)

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


@pytest.mark.parametrize(
    ("env_vars", "config_content", "expected_options"),
    [
        # Environment variables override config file
        (
            {
                "AWS_PROFILE": "env-profile",
                "AWS_REGION": "env-region",
                "AWS_ACCESS_KEY_ID": "env-key",
                "AWS_SECRET_ACCESS_KEY": "env-secret",
                "AWS_SESSION_TOKEN": "env-token",
            },
            """
            [codeartifact]
            profile_name = config-profile
            aws_access_key_id = config-key
            aws_secret_access_key = config-secret
            aws_session_token = config-token
            """,
            {
                "profile_name": "env-profile",
                "region_name": "env-region",
                "aws_access_key_id": "env-key",
                "aws_secret_access_key": "env-secret",
                "aws_session_token": "env-token",
            },
        ),
        # AWS_DEFAULT_REGION fallback
        (
            {"AWS_DEFAULT_REGION": "default-region"},
            "",
            {"region_name": "default-region"},
        ),
        # AWS_SECURITY_TOKEN fallback
        (
            {
                "AWS_ACCESS_KEY_ID": "key",
                "AWS_SECRET_ACCESS_KEY": "secret",
                "AWS_SECURITY_TOKEN": "security-token",
            },
            "",
            {
                "aws_access_key_id": "key",
                "aws_secret_access_key": "secret",
                "aws_session_token": "security-token",
            },
        ),
        # Config file values when no env vars
        (
            {},
            """
            [codeartifact]
            profile_name = config-profile
            aws_access_key_id = config-key
            aws_secret_access_key = config-secret
            """,
            {
                "profile_name": "config-profile",
                "aws_access_key_id": "config-key",
                "aws_secret_access_key": "config-secret",
            },
        ),
        # Region precedence: AWS_REGION takes priority over parsed region
        ({"AWS_REGION": "env-region"}, "", {"region_name": "env-region"}),
        # Only session token without keys should not include token
        ({"AWS_SESSION_TOKEN": "token-only"}, "", {}),
    ],
)
def test_environment_variable_precedence(
    monkeypatch, env_vars: dict, config_content: str, expected_options: str
):
    # Clear existing environment variables and set test ones
    for env_key in [
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
    ]:
        monkeypatch.delenv(env_key, raising=False)

    for env_key, env_value in env_vars.items():
        monkeypatch.setenv(env_key, env_value)

    class DummyClient:
        def get_authorization_token(self, *args, **kwargs):
            return {}

    def make_client(options):
        # Assert that we received specific options.
        for key, value in expected_options.items():
            assert value == options.get(key)

        # Ignore the rest.
        return DummyClient()

    with config_from_string(config_content) as config_file:
        config = CodeArtifactKeyringConfig(config_file=config_file.name)
        backend = CodeArtifactBackend(config=config, make_client=make_client)
        url = codeartifact_pypi_url("domain", "000000000000", "region", "name")
        backend.get_credential(url, None)
