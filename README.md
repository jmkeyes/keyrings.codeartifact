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


### Options
- `aws_access_key_id` Specifies the key ID used to authenticate with AWS.
- `aws_secret_access_key` Specifies the secret key used to authenticate with AWS.
- `profile_name` Specifies the name of a specific profile to use with the AWS client.

For more explanation of these options see the [AWS CLI documentation](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html).

Example:
```ini
[codeartifact]
profile_name=profile_name
aws_access_key_id=xxxxxxxxx
aws_secret_access_key=xxxxxxxxx
```
