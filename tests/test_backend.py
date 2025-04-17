# test_backend.py -- backend tests

import pytest

import keyring

from io import StringIO
from urllib.parse import urlunparse
from botocore.client import BaseClient
from datetime import datetime, timedelta
from keyrings.codeartifact import CodeArtifactBackend, CodeArtifactKeyringConfig


@pytest.fixture
def mocked_keyring_config(mocker):
    mock_config_instance = mocker.create_autospec(
        CodeArtifactKeyringConfig, spec_set=True
    )
    mock_config = mocker.patch("keyrings.codeartifact.CodeArtifactKeyringConfig")
    mock_config.return_value = mock_config_instance
    return mock_config_instance


@pytest.fixture
def backend(mocked_keyring_config):
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


def make_check_codeartifact_api_call(*, config, domain, domain_owner):
    assumed_role = False
    assume_role = config.get("assume_role")
    assume_session_name = config.get("assume_session_name")
    should_assume_role = assume_role is not None

    def _make_api_call(client, *args, **kwargs):
        nonlocal assumed_role
        if should_assume_role and not assumed_role:
            # We should only ever call GetAuthorizationToken
            assert args[0] == "AssumeRole"

            # We should only ever supply these parameters.
            assert args[1]["RoleArn"] == assume_role
            if assume_session_name is not None:
                assert args[1]["RoleSessionName"] == assume_session_name
            assumed_role = True
            return {
                "Credentials": {
                    "AccessKeyId": "",
                    "SecretAccessKey": "",
                    "SessionToken": "",
                }
            }
        else:
            assert assumed_role == should_assume_role

            # We should only ever call GetAuthorizationToken
            assert args[0] == "GetAuthorizationToken"

            # We should only ever supply these parameters.
            assert args[1]["domain"] == domain
            assert args[1]["domainOwner"] == domain_owner
            assert args[1]["durationSeconds"] == 3600

            tzinfo = datetime.now().astimezone().tzinfo
            current_time = datetime.now(tz=tzinfo)

            # Compute the expiration based on the current timestamp.
            expiration = timedelta(seconds=args[1]["durationSeconds"])

            return {
                "authorizationToken": "TOKEN",
                "expiration": current_time + expiration,
            }

    return _make_api_call


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


@pytest.mark.parametrize(
    ["config"],
    [
        ({},),
        (
            {
                "assume_role": "arn:aws:iam::000000000000:role/some-role",
                "assume_role_session_name": "SomeSessionName",
            },
        ),
    ],
)
def test_get_credential_supported_host(
    backend, config, mocked_keyring_config, monkeypatch
):
    domain = "domain"
    domain_owner = "000000000000"

    monkeypatch.setattr(
        BaseClient,
        "_make_api_call",
        make_check_codeartifact_api_call(
            config=config, domain=domain, domain_owner=domain_owner
        ),
    )
    mocked_keyring_config.lookup.return_value = config

    url = codeartifact_pypi_url(domain, domain_owner, "region", "name")
    credentials = backend.get_credential(url, None)

    assert credentials.username == "aws"
    assert credentials.password == "TOKEN"
