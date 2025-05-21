# test_config.py -- config parsing tests

import pytest

from io import StringIO
from os.path import dirname, join

from keyrings.codeartifact import CodeArtifactKeyringConfig


@pytest.fixture
def config_file():
    working_directory = dirname(__file__)

    def _config_file(path):
        return join(working_directory, "config", path)

    return _config_file


@pytest.mark.parametrize(
    "parameters",
    [
        (None, None, None, None),
        ("domain", "owner", "region", "name"),
        ("domain", "00000000", "ca-central-1", "repository"),
    ],
)
def test_parse_single_section_only(config_file, parameters):
    config = CodeArtifactKeyringConfig(config_file("single_section.cfg"))

    # A single section has only one configuration.
    values = config.lookup(*parameters)

    assert values.get("token_duration") == "1800"
    assert values.get("profile_name") == "default_profile"
    assert values.get("aws_access_key_id") == "default_access_key_id"
    assert values.get("aws_secret_access_key") == "default_access_secret_key"


@pytest.mark.parametrize(
    "config_data",
    [
        # Empty configuration file.
        "",
        # Foreign backend configuration.
        """
        [other-backend]
        config_key = we-should-ignore
        """,
        # Section header only.
        """
        [codeartifact]
        """,
    ],
)
def test_bogus_config_returns_empty_configuration(config_data):
    config = CodeArtifactKeyringConfig(StringIO(config_data))
    values = config.lookup()
    assert values == {}


@pytest.mark.parametrize(
    "query, expected",
    [
        (
            {"account": "000000000000"},
            {
                "token_duration": "600",
                "aws_access_key_id": "not_access_key",
                "aws_secret_access_key": "not_secret_key",
            },
        ),
        (
            {"domain": "specific"},
            {"token_duration": "1800", "profile_name": "domain_specific"},
        ),
        (
            {"account": "000000000000", "name": "development"},
            {"token_duration": "1800", "profile_name": "development_profile"},
        ),
        (
            {"account": "000000000000", "name": "testing"},
            {"token_duration": "1800", "profile_name": "testing_profile"},
        ),
        (
            {"account": "000000000000", "name": "production"},
            {"token_duration": "1800", "profile_name": "production_profile"},
        ),
    ],
)
def test_multiple_sections_with_defaults(config_file, query, expected):
    path = config_file("multiple_sections_with_default.cfg")
    config = CodeArtifactKeyringConfig(path)
    values = config.lookup(**query)

    for key, value in expected.items():
        assert values.get(key) == value


@pytest.mark.parametrize(
    "query, expected",
    [
        (
            {"account": "000000000000", "name": "development"},
            {"token_duration": None, "profile_name": "development_profile"},
        ),
        (
            {"account": "000000000000", "name": "testing"},
            {"token_duration": None, "profile_name": "testing_profile"},
        ),
        (
            {"account": "000000000000", "name": "production"},
            {"token_duration": None, "profile_name": "production_profile"},
        ),
    ],
)
def test_multiple_sections_no_defaults(config_file, query, expected):
    path = config_file("multiple_sections_no_default.cfg")
    config = CodeArtifactKeyringConfig(path)
    values = config.lookup(**query)

    for key, value in expected.items():
        assert values.get(key) == value
