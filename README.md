AWS CodeArtifact Keyring Backend
================================

The `keyrings.codeartifact` package provides authentication for publishing and consuming packages within a private
PyPi repository hosted on [AWS CodeArtifact](https://aws.amazon.com/codeartifact/); it contains an extension to the
[keyring](https://pypi.org/project/keyring/) library that will automatically inject a time-limited access token.

Installation
------------
To install this package, install the "keyrings.codeartifact" package using `pip`:

```
pip install keyrings.codeartifact
```

Usage
-----
The `keyring` library has been integrated with recent versions of pip and twine. Once installed, this library will
automatically supply credentials whenever pip/twine (or other keyring-enabled package) attempts to use a repository
hosted within CodeArtifact. It will use any appropriate AWS credentials provided in `~/.aws/credentials` by default.

```
--index-url https://${DOMAIN}-${ACCOUNT}.d.codeartifact.${REGION}.amazonaws.com/pypi/${REPOSITORY}/simple/
```

Config
------
This backend provides a number of configuration options to modify the behaviour of the AWS client.

These configuration options can be specified within a `[codeartifact]` section of the `keyringrc.cfg`.

Run `keyring diagnose` to find its as the location; it varies between different platforms.

Available options:

  - `profile_name`: Use a specific AWS profile to authenticate with AWS.
  - `token_duration`: Validity period (in seconds) for retieved authorization tokens.
  - `aws_access_key_id`: Use a specific AWS access key to authenticate with AWS.
  - `aws_secret_access_key`: Use a specific AWS secret access key to authenticate with AWS.

For more explanation of these options see the [AWS CLI documentation](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html).

An example `keyringrc.cfg` section:

```ini
[codeartifact]
# Tokens should only be valid for 30 minutes.
token_duration=1800

# Use the 'default' profile name.
profile_name=default

# Use the following access keys.
aws_access_key_id=xxxxxxxxx
aws_secret_access_key=xxxxxxxxx
```
