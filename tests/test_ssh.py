import paramiko
import pytest

from netcup_backup.agent.ssh import SshClient

# A throwaway, unencrypted ed25519 test key -- never used against any real host.
TEST_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n"
    "QyNTUxOQAAACCeSkUsrhmkosOr1ldcQmjpodoupmPTqQM6jkSwQSqyKwAAAIiA4RyrgOEc\n"
    "qwAAAAtzc2gtZWQyNTUxOQAAACCeSkUsrhmkosOr1ldcQmjpodoupmPTqQM6jkSwQSqyKw\n"
    "AAAEAef3q7mEMM84Uv7rDO8hRmp2DIu2Q3yCe0uBleaxfB7J5KRSyuGaSiw6vWV1xCaOmh\n"
    "2i6mY9OpAzqORLBBKrIrAAAAAAECAwQF\n"
    "-----END OPENSSH PRIVATE KEY-----\n"
)


def _flattened(pem: str) -> str:
    lines = pem.strip().split("\n")
    return lines[0] + "".join(lines[1:-1]) + lines[-1]


def test_normalize_passes_through_well_formed_key():
    normalized = SshClient._normalize(TEST_KEY)
    key = SshClient._load_pkey(normalized)
    assert isinstance(key, paramiko.Ed25519Key)


def test_normalize_reconstructs_flattened_key():
    # This is exactly what Coolify's multiline env var handling did to the key
    # in production: newlines between header/body/footer got dropped.
    flattened = _flattened(TEST_KEY)
    assert "\n" not in flattened

    normalized = SshClient._normalize(flattened)
    key = SshClient._load_pkey(normalized)
    assert isinstance(key, paramiko.Ed25519Key)


def test_normalize_handles_literal_escaped_newlines():
    escaped = TEST_KEY.replace("\n", "\\n")
    normalized = SshClient._normalize(escaped)
    key = SshClient._load_pkey(normalized)
    assert isinstance(key, paramiko.Ed25519Key)


def test_normalize_handles_crlf_line_endings():
    crlf = TEST_KEY.replace("\n", "\r\n")
    normalized = SshClient._normalize(crlf)
    key = SshClient._load_pkey(normalized)
    assert isinstance(key, paramiko.Ed25519Key)


def test_normalize_strips_wrapping_quotes():
    quoted = '"' + TEST_KEY.strip() + '"'
    normalized = SshClient._normalize(quoted)
    key = SshClient._load_pkey(normalized)
    assert isinstance(key, paramiko.Ed25519Key)


def test_load_pkey_raises_on_garbage():
    with pytest.raises(ValueError, match="no supported private key found"):
        SshClient._load_pkey("not a key at all")
