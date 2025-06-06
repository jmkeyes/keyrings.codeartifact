import pytest
from keyrings.clients.tsh import TeleportCAClient


@pytest.fixture
def teleport_client():
    return TeleportCAClient(
        account="123456789012",
        domain="my-domain",
        region="us-west-2",
        teleport_proxy="teleport.example.com:443",
        tsh_app_name="my-app",
        tsh_aws_role_name="my-role",
    )
