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
