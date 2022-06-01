#!/usr/bin/env python

import re
import logging

import boto3
import botocore

from keyring import backend
from keyring import credentials

from datetime import datetime
from urllib.parse import urlparse


class CodeArtifactBackend(backend.KeyringBackend):
    REGEX = r'^(.+)-(\d{12})\.d\.codeartifact\.([^\.]+)\.amazonaws\.com$'

    priority = 9.9

    def get_credential(self, service, username):
        authorization_token = self.get_password(service, username)
        if authorization_token:
            return credentials.SimpleCredential('aws', authorization_token)

    def get_password(self, service, username):
        url = urlparse(service)

        # Do a quick check to see if this service URL applies to us.
        if url.hostname is None or not url.hostname.endswith('.amazonaws.com'):
            return

        # Split the hostname into its components.
        match = re.fullmatch(self.REGEX, url.hostname)

        # If it didn't match the regex, it doesn't apply to us.
        if not match:
            logging.warning("Not an AWS CodeArtifact repository URL!")
            return

        # Extract the domain, account and region for this repository.
        domain, account, region = match.group(1, 2, 3)

        # Split the path into its repository type and name.
        repository_type, repository_name = url.path.strip('/').split('/', 1)

        # Only continue if this was a PyPi repository.
        if repository_type != 'pypi':
            logging.warning(f'Not an AWS CodeArtifact PyPi repository: {service}')
            return

        # Figure out our local timezone from the current time.
        tzinfo = datetime.now().astimezone().tzinfo
        now = datetime.now(tz=tzinfo)

        # Create a CodeArtifact client for this repository's region.
        client = boto3.client('codeartifact', region_name=region)

        # Ask for an authorization token using the current AWS credentials.
        response = client.get_authorization_token(
            domain=domain, domainOwner=account, durationSeconds=3600
        )

        # Give up if the token has already expired.
        if response.get('expiration', now) <= now:
            logging.warning("Received an expired CodeArtifact token!")
            return

        return response.get('authorizationToken')

    def set_password(self, service, username, password):
        # Defer setting a password to the next backend
        raise NotImplementedError()

    def delete_password(self, service, username):
        # Defer deleting a password to the next backend
        raise NotImplementedError()
