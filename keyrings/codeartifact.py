# codeartifact.py -- keyring backend

import re
import boto3
import logging

from datetime import datetime
from urllib.parse import urlparse

from keyring import backend, credentials
from keyring.util.platform_ import config_root

from typing import NamedTuple
from configparser import RawConfigParser


class Qualifier(NamedTuple):
    domain: str = None
    account: str = None
    region: str = None
    name: str = None


class CodeArtifactKeyringConfig:
    DEFAULT_SECTION = "codeartifact"
    SECTION_RE = re.compile(r"^codeartifact ?")

    QUALIFIER_FIELDS = "|".join(Qualifier._fields)
    QUALIFIER_RE = re.compile(
        rf"""
        (?P<key>{QUALIFIER_FIELDS})= # Key is one of the fields.
        (?P<quote>["']?)             # The opening quote.
        (?P<value>[\S\s]*?)          # The value of the field.
        (?P=quote)                   # The closing quote.
        (?:$| )                      # A space or end-of-string.
    """,
        re.VERBOSE | re.IGNORECASE,
    )

    def __init__(self, config_file):
        # Customize RawConfigParser to allow inline comments.
        config_parser = RawConfigParser(inline_comment_prefixes=("#", ";"))

        # Anything in the [codeartifact] section is a default.
        config_parser.default_section = self.DEFAULT_SECTION

        # Load the configuration file.
        config_parser.read(config_file)

        # Collect the defaults before we go further.
        self.defaults = config_parser.defaults()

        # A generator to extract only the sections we want.
        def codeartifact_sections(sections):
            for section in sections:
                if not self.SECTION_RE.match(section):
                    # Not a relevant section.
                    continue

                # Find any key=value pairs in the section name.
                matches = [m for m in self.QUALIFIER_RE.finditer(section)]

                # Group those matches into pairs by extracting the pairs.
                pairs = [p.group("key", "value") for p in matches]

                # Build a qualifier from the key/value pairs.
                key = Qualifier(**{k: v for k, v in pairs})

                # Now extract this section's configuration.
                value = config_parser[section]

                yield key, value

        # Collect only the sections we actually care about.
        sections = codeartifact_sections(config_parser.sections())

        # Expand the generator into a dictionary.
        self.config = dict(sections)

    def lookup(self, domain=None, account=None, region=None, name=None):
        key = Qualifier(domain, account, region, name)

        # Return the defaults if we didn't have anything to look up.
        if not self.config.keys() or key == Qualifier():
            # If defaults were not provided, return None.
            return self.defaults

        # Rank candidate keys based on a 0-4 scale.
        def score(candidate):
            return sum(
                [
                    key.domain == candidate.domain,
                    key.account == candidate.account,
                    key.region == candidate.region,
                    key.name == candidate.name,
                ]
            )

        # Find the key with the highest score.
        found_key = max(self.config.keys(), key=score)

        # Return the most specific match.
        return self.config.get(found_key)


class CodeArtifactBackend(backend.KeyringBackend):
    HOST_REGEX = r"^(.+)-(\d{12})\.d\.codeartifact\.([^\.]+)\.amazonaws\.com$"
    PATH_REGEX = r"^/pypi/([^/]+)/?"

    priority = 9.9

    def __init__(self, config_file=None):
        super().__init__()

        if not config_file:
            config_file = config_root() / "keyringrc.cfg"

        self.config = CodeArtifactKeyringConfig(config_file)

    def get_credential(self, service, username):
        authorization_token = self.get_password(service, username)
        if authorization_token:
            return credentials.SimpleCredential("aws", authorization_token)

    def get_password(self, service, username):
        url = urlparse(service)

        # Do a quick check to see if this service URL applies to us.
        if url.hostname is None or not url.hostname.endswith(".amazonaws.com"):
            return

        # Split the hostname into its components.
        host_match = re.fullmatch(self.HOST_REGEX, url.hostname)

        # If it didn't match the regex, it doesn't apply to us.
        if not host_match:
            logging.warning("Not an AWS CodeArtifact repository URL!")
            return

        # Extract the domain, account and region for this repository.
        domain, account, region = host_match.group(1, 2, 3)

        # Validate path and extract repo name
        path_match = re.fullmatch(self.PATH_REGEX, url.path)
        if not path_match:
            logging.warning(f"Invalid CodeArtifact PyPI path: {url.path}")
            return

        repository_name = path_match.group(1)

        # Load our configuration file.
        config = self.config.lookup(
            domain=domain,
            account=account,
            region=region,
            name=repository_name,
        )

        # Create session with any supplied configuration.
        session = boto3.Session(
            region_name=region,
            profile_name=config.get("profile_name"),
            aws_access_key_id=config.get("aws_access_key_id"),
            aws_secret_access_key=config.get("aws_secret_access_key"),
        )

        # Create a CodeArtifact client for this repository's region.
        client = session.client("codeartifact", region_name=region)

        # Authorization tokens should be good for an hour by default.
        token_duration = int(config.get("token_duration", 3600))

        # Ask for an authorization token using the current AWS credentials.
        response = client.get_authorization_token(
            domain=domain, domainOwner=account, durationSeconds=token_duration
        )

        # Figure out our local timezone from the current time.
        tzinfo = datetime.now().astimezone().tzinfo
        now = datetime.now(tz=tzinfo)

        # Give up if the token has already expired.
        if response.get("expiration", now) <= now:
            logging.warning("Received an expired CodeArtifact token!")
            return

        return response.get("authorizationToken")

    def set_password(self, service, username, password):
        # Defer setting a password to the next backend
        raise NotImplementedError()

    def delete_password(self, service, username):
        # Defer deleting a password to the next backend
        raise NotImplementedError()
