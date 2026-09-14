from netcup_backup.agent.prune import forget_and_prune


class FakeSsh:
    def __init__(self) -> None:
        self.last_cmd = ""

    def run(self, command: str, *, timeout: int = 300):
        self.last_cmd = command
        from netcup_backup.agent.ssh import CommandResult

        return CommandResult(exit_code=0, stdout="", stderr="")


def test_forget_and_prune_composes_command():
    from netcup_backup.config import Config

    cfg = Config(
        netcup_refresh_token="x" * 20,
        netcup_server_id="v123",
        ssh_host="h",
        ssh_private_key="-" * 40,
        restic_repository="s3:abc.r2.cloudflarestorage.com/b",
        restic_password="secret",
        r2_access_key_id="ak",
        r2_secret_access_key="sk",
        r2_keep=7,
    )
    ssh = FakeSsh()
    res = forget_and_prune(ssh, cfg)
    assert res.ok
    assert "forget --keep-last 7 --prune" in ssh.last_cmd
    assert "s3:abc.r2.cloudflarestorage.com/b" in ssh.last_cmd
