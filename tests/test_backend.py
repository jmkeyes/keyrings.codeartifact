# test_backend.py -- backend tests

import re

import boto3
import pytest

from io import StringIO
from pathlib import Path
from urllib.parse import urlunparse
from datetime import datetime, timedelta

from botocore.stub import Stubber

from contextlib import contextmanager
from tempfile import NamedTemporaryFile

from keyrings.codeartifact import default_role_session_name, make_codeartifact_client
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
        # Passing an assume-role ARN and explicit session name through.
        (
            """
            [codeartifact]
            assume_role_arn = arn:aws:iam::000000000000:role/role
            assume_role_session_name = SESSION-NAME
            """,
            {
                "assume_role_arn": "arn:aws:iam::000000000000:role/role",
                "assume_role_session_name": "SESSION-NAME",
            },
        ),
        # A session name is only forwarded alongside a role ARN.
        (
            """
            [codeartifact]
            assume_role_session_name = SESSION-NAME
            """,
            {
                "assume_role_arn": None,
                "assume_role_session_name": None,
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


def test_default_role_session_name():
    # The default name is derived from the caller's STS UserId; any characters
    # AWS doesn't permit in a RoleSessionName are sanitized away.
    sts_client = boto3.session.Session(region_name=REGION_NAME).client(
        "sts", region_name=REGION_NAME
    )

    stubber = Stubber(sts_client)
    stubber.add_response(
        "get_caller_identity",
        {
            "UserId": "AROAEXAMPLEID:weird session/name",
            "Account": "000000000000",
            "Arn": "arn:aws:sts::000000000000:assumed-role/role/weird",
        },
        {},
    )
    stubber.activate()

    name = default_role_session_name(sts_client)

    assert name == "keyrings.codeartifact-AROAEXAMPLEID-weird-session-name"
    assert len(name) <= 64
    assert re.fullmatch(r"[\w+=,.@-]+", name)
    stubber.assert_no_pending_responses()


@pytest.mark.parametrize(
    "session_name_options",
    [
        # An explicitly configured role session name.
        {"assume_role_session_name": "SESSION-NAME"},
        # No session name: a default identifying the caller is generated.
        {},
    ],
)
def test_make_codeartifact_client_assumes_role(monkeypatch, session_name_options):
    role_arn = "arn:aws:iam::000000000000:role/role"

    # Build real clients up front so we can attach a stub to STS.
    real_session = boto3.session.Session(region_name=REGION_NAME)
    sts_client = real_session.client("sts", region_name=REGION_NAME)
    codeartifact_client = real_session.client("codeartifact", region_name=REGION_NAME)

    sts_stubber = Stubber(sts_client)

    explicit_session_name = session_name_options.get("assume_role_session_name")
    if explicit_session_name:
        expected_session_name = explicit_session_name
    else:
        # Without a configured name, the default is derived from the caller's
        # STS UserId via GetCallerIdentity.
        sts_stubber.add_response(
            "get_caller_identity",
            {
                "UserId": "AIDAEXAMPLEUSERID",
                "Account": "000000000000",
                "Arn": "arn:aws:iam::000000000000:user/example",
            },
            {},
        )
        expected_session_name = "keyrings.codeartifact-AIDAEXAMPLEUSERID"

    sts_stubber.add_response(
        "assume_role",
        {
            "Credentials": {
                "AccessKeyId": "TEMP-ACCESS-KEY-ID",
                "SecretAccessKey": "TEMP-SECRET-ACCESS-KEY",
                "SessionToken": "TEMP-SESSION-TOKEN",
                "Expiration": current_time() + timedelta(hours=1),
            },
        },
        {"RoleArn": role_arn, "RoleSessionName": expected_session_name},
    )
    sts_stubber.activate()

    created_sessions = []

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            created_sessions.append(self)

        def client(self, service, **kwargs):
            return sts_client if service == "sts" else codeartifact_client

    # Swap the session factory so we control the clients that get created.
    monkeypatch.setattr(boto3.session, "Session", FakeSession)

    options = {"region_name": REGION_NAME, "assume_role_arn": role_arn}
    options.update(session_name_options)

    client = make_codeartifact_client(options)

    # The returned client is built from the assumed role's session.
    assert client is codeartifact_client
    sts_stubber.assert_no_pending_responses()

    # The final session was created from the temporary credentials.
    assert created_sessions[-1].kwargs["aws_access_key_id"] == "TEMP-ACCESS-KEY-ID"
    assert (
        created_sessions[-1].kwargs["aws_secret_access_key"] == "TEMP-SECRET-ACCESS-KEY"
    )
    assert created_sessions[-1].kwargs["aws_session_token"] == "TEMP-SESSION-TOKEN"
