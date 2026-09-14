from netcup_backup.config import Config


def _make_config(**overrides) -> Config:
    base = dict(
        netcup_refresh_token="x" * 30,
        netcup_server_id="v123",
        ssh_host="rs2000.example",
        ssh_private_key="-" * 50,
        restic_repository="s3:abc.r2.cloudflarestorage.com/b",
        restic_password="secret",
        r2_access_key_id="ak",
        r2_secret_access_key="sk",
    )
    base.update(overrides)
    return Config(**base)


def test_paths_split():
    c = _make_config(restic_paths="/etc,/var,/home")
    assert c.backup_paths == ["/etc", "/var", "/home"]


def test_paths_default():
    c = _make_config()
    assert c.backup_paths == ["/"]


def test_excludes_split_and_default():
    c = _make_config()
    assert "/tmp" in c.exclude_paths
    assert "/proc" in c.exclude_paths


def test_restic_env_lines_include_secrets():
    c = _make_config(r2_keep=5)
    env = c.restic_env_lines
    assert "RESTIC_REPOSITORY=s3:abc.r2.cloudflarestorage.com/b" in env
    assert "RESTIC_PASSWORD=secret" in env
    assert "AWS_ACCESS_KEY_ID=ak" in env
    assert "AWS_SECRET_ACCESS_KEY=sk" in env
    assert "AWS_DEFAULT_REGION=auto" in env


def test_invalid_keep_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _make_config(r2_keep=0)
