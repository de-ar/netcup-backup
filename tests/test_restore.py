from netcup_backup.agent.restore import restore
from netcup_backup.config import Config


class FakeSsh:
    def __init__(self) -> None:
        self.last_cmd = ""

    def run(self, command: str, *, timeout: int = 300):
        self.last_cmd = command
        from netcup_backup.agent.ssh import CommandResult

        return CommandResult(exit_code=0, stdout="", stderr="")


def _make_config(**overrides) -> Config:
    base = dict(
        netcup_refresh_token="x" * 20,
        netcup_server_id="v123",
        ssh_host="h",
        ssh_private_key="-" * 40,
        restic_repository="s3:abc.r2.cloudflarestorage.com/b",
        restic_password="secret",
        r2_access_key_id="ak",
        r2_secret_access_key="sk",
    )
    base.update(overrides)
    return Config(**base)


def test_restore_defaults_to_latest_snapshot():
    ssh = FakeSsh()
    res = restore(ssh, _make_config(), target="/tmp/restic-restore-test")
    assert res.ok
    assert "restore latest --target /tmp/restic-restore-test" in ssh.last_cmd
    assert "s3:abc.r2.cloudflarestorage.com/b" in ssh.last_cmd


def test_restore_uses_given_snapshot_id():
    ssh = FakeSsh()
    res = restore(ssh, _make_config(), target="/tmp/out", snapshot="abcd1234")
    assert res.ok
    assert "restore abcd1234 --target /tmp/out" in ssh.last_cmd


def test_restore_appends_include_flags():
    ssh = FakeSsh()
    restore(
        ssh,
        _make_config(),
        target="/tmp/out",
        include=["/etc/hostname", "/etc/os-release"],
    )
    assert "--include /etc/hostname" in ssh.last_cmd
    assert "--include /etc/os-release" in ssh.last_cmd


def test_restore_quotes_untrusted_arguments():
    ssh = FakeSsh()
    restore(
        ssh,
        _make_config(),
        target="/tmp/out; rm -rf /",
        snapshot="latest",
        include=["/etc/hostname; cat /etc/shadow"],
    )
    assert "'/tmp/out; rm -rf /'" in ssh.last_cmd
    assert "'/etc/hostname; cat /etc/shadow'" in ssh.last_cmd


def test_restore_logs_and_returns_failure(caplog):
    class FailingSsh:
        def run(self, command: str, *, timeout: int = 300):
            from netcup_backup.agent.ssh import CommandResult

            return CommandResult(exit_code=1, stdout="", stderr="boom")

    res = restore(FailingSsh(), _make_config(), target="/tmp/out")
    assert not res.ok
    assert res.stderr == "boom"
