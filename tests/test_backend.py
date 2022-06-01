
import pytest

import boto3
import keyring
import keyrings.codeartifact

from datetime import datetime


class MockCodeArtifactClient:
    def __init__(self, expiration, authorization_token):
        self.authorization_token = authorization_token
        self.expiration = expiration

    def get_authorization_token(self, **kwargs):
        return {
            'authorizationToken': self.authorization_token,
            'expiration': self.expiration,
        }

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

@pytest.mark.parametrize('service', [
    'https://unknown.amazonaws.com/',
    'https://DOMAIN-ACCOUNT.d.codeartifact.REGION.amazonaws.com/',
    'https://domain-000000000000.d.codeartifact.region.amazonaws.com/maven/repository',
])
def test_get_credential_invalid_host(backend, service):
    assert keyring.get_credential(service, None) == None

def test_get_credential_unsupported_host(backend):
    assert keyring.get_credential("https://example.com/", None) == None

def test_get_credential_supported_host(backend, monkeypatch):
    def mock(*args, **kwargs):
        tzinfo = datetime.now().astimezone().tzinfo
        expiration = datetime.now(tz=tzinfo)
        return MockCodeArtifactClient(expiration, 'TOKEN')

    monkeypatch.setattr(boto3, "client", mock)

    credentials = keyring.get_credential(
        'https://domain-000000000000.d.codeartifact.region.amazonaws.com/pypi/repository',
        None
    )

    assert credentials.username == 'aws'
    assert credentials.password == 'TOKEN'
