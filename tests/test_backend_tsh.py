import subprocess

from unittest.mock import patch, MagicMock
import pytest

from keyrings.clients.tsh import TeleportCAClient


@patch("subprocess.run")
def test_get_teleport_path_status_success(mock_run, teleport_client):
    # Mock subprocess.run to return successfully
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_run.return_value = mock_process

    # Call the method
    result = teleport_client._get_teleport_path_status()

    # Verify the result
    assert result is True
    mock_run.assert_called_once_with(
        ["tsh", "version"], capture_output=True, text=True, check=True
    )


@patch("subprocess.run")
def test_get_teleport_path_status_failure(mock_run, teleport_client):
    # Mock subprocess.run to raise CalledProcessError
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["tsh", "version"], stderr="tsh: command not found"
    )

    # Call the method and verify it raises the expected exception
    with pytest.raises(RuntimeError) as excinfo:
        teleport_client._get_teleport_path_status()

    assert "Error checking tsh command" in str(excinfo.value)


@patch("subprocess.run")
def test_get_teleport_login_status_success(mock_run, teleport_client):
    # Mock subprocess.run to return successfully
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_run.return_value = mock_process

    # Call the method
    result = teleport_client._get_teleport_login_status()

    # Verify the result
    assert result is True
    mock_run.assert_called_once_with(
        ["tsh", "status"], capture_output=True, text=True, check=True
    )


@patch("subprocess.run")
def test_get_teleport_login_status_failure(mock_run, teleport_client):
    # Mock subprocess.run to raise CalledProcessError
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["tsh", "status"], stderr="Not logged in"
    )

    # Call the method
    result = teleport_client._get_teleport_login_status()

    # Verify the result
    assert result is False


@patch("subprocess.run")
def test_get_ca_token_success(mock_run, teleport_client):
    # Mock subprocess.run to return successfully with a token
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "mock-token-value"
    mock_run.return_value = mock_process

    # Call the method
    result = teleport_client._get_ca_token()

    # Verify the result
    assert result == "mock-token-value"
    mock_run.assert_called_once_with(
        [
            "tsh",
            "aws",
            "codeartifact",
            "get-authorization-token",
            "--domain",
            "my-domain",
            "--domain-owner",
            "123456789012",
            "--query",
            "authorizationToken",
            "--region",
            "us-west-2",
            "--output",
            "text",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch.object(TeleportCAClient, "_get_teleport_login_status")
@patch.object(TeleportCAClient, "_teleport_login")
@patch.object(TeleportCAClient, "_get_teleport_app_auth_status")
@patch.object(TeleportCAClient, "_teleport_app_login")
@patch.object(TeleportCAClient, "_get_ca_token")
def test_get_authorization_token_flow(
    mock_get_ca_token,
    mock_teleport_app_login,
    mock_get_teleport_app_auth_status,
    mock_teleport_login,
    mock_get_teleport_login_status,
    teleport_client,
):
    # Configure mocks for full flow
    mock_get_teleport_login_status.return_value = False
    mock_teleport_login.return_value = True
    mock_get_teleport_app_auth_status.return_value = False
    mock_teleport_app_login.return_value = True
    mock_get_ca_token.return_value = "mock-token-value"

    # Call the method
    result = teleport_client.get_authorization_token()

    # Verify the result and that all methods were called
    assert result == "mock-token-value"
    mock_get_teleport_login_status.assert_called_once()
    mock_teleport_login.assert_called_once()
    mock_get_teleport_app_auth_status.assert_called_once()
    mock_teleport_app_login.assert_called_once()
    mock_get_ca_token.assert_called_once()
