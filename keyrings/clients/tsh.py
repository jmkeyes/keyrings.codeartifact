import subprocess
import re
import os

import logging

logging.getLogger("keyrings.codeartifact")


class TeleportCAClient:
    def __init__(
        self,
        account: str,
        domain: str,
        region: str,
        teleport_proxy: str = None,
        tsh_app_name: str = None,
        tsh_aws_role_name: str = None,
        **kwargs,
    ):
        """
        Initialize the teleport codeartifact client.
        This class is responsible for managing the Teleport login and app authentication
        to retrieve the CodeArtifact authorization token.
        """
        self.region = region
        self.domain = domain
        self.account = account
        self.tsh_aws_role_name = tsh_aws_role_name
        self.tsh_app_name = tsh_app_name
        self.teleport_proxy = teleport_proxy

    def _get_teleport_path_status(self):
        """Check if the tsh command is available in the system path."""
        try:
            subprocess.run(
                ["tsh", "version"],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                "Error checking tsh command. Confirm it is installed and available via PATH: %s"
                % e.stderr.strip()
            ) from e

    def _get_teleport_login_status(self):
        """Check if the user is logged into Teleport."""
        try:
            subprocess.run(
                ["tsh", "status"],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logging.debug("Error checking Teleport login status: %s", e.stderr.strip())
            return False

    def _teleport_login(self):
        """Login to Teleport using the tsh command."""
        try:
            login_command = f"tsh login --proxy={self.teleport_proxy}"
            subprocess.run(
                login_command.split(" "),
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logging.debug("Error logging into Teleport: %s", e.stderr.strip())
            return False

    def _get_teleport_app_auth_status(self):
        """Check if the user is authenticated for the Teleport app."""
        try:
            subprocess.run(
                ["tsh", "app", "config", f"{self.tsh_app_name}"],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logging.debug(
                "Error checking Teleport app auth status: %s", e.stderr.strip()
            )
            return False

    def _teleport_app_login(self):
        """Login to the Teleport app using the tsh command."""
        try:
            login_command = (
                f"tsh app login {self.tsh_app_name} --aws-role {self.tsh_aws_role_name}"
            )
            subprocess.run(
                login_command.split(" "),
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logging.debug("Error logging into Teleport app: %s", e.stderr.strip())
            return False

    def _get_ca_token(self):
        """use tsh prefixed aws cli command to generate codeartifact token"""
        try:
            get_ca_token_command = f"tsh aws codeartifact get-authorization-token --domain {self.domain} --domain-owner {self.account} --query authorizationToken --region {self.region} --output text"
            get_ca_token_command_list = get_ca_token_command.split(" ")
            tsh_output = subprocess.run(
                get_ca_token_command_list,
                capture_output=True,
                text=True,
                check=True,
            )
            return tsh_output.stdout.strip()
        except subprocess.CalledProcessError as e:
            logging.debug("Error getting CA token: %s", e.stderr.strip())

    def get_authorization_token(self):
        """Get the CodeArtifact authorization token."""
        if not self._get_teleport_login_status():
            self._teleport_login()
        if not self._get_teleport_app_auth_status():
            self._teleport_app_login()
        return self._get_ca_token()
