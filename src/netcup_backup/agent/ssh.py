from __future__ import annotations

import io
import logging
from collections.abc import Iterable
from dataclasses import dataclass

import paramiko

log = logging.getLogger(__name__)


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SshClient:
    def __init__(
        self,
        host: str,
        *,
        port: int = 22,
        user: str = "root",
        private_key_pem: str = "",
        host_keys_pem: str = "",
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._pkey = self._load_pkey(private_key_pem)
        self._host_keys = self._load_host_keys(host_keys_pem) if host_keys_pem else None

    def connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        if self._host_keys is not None:
            client.get_host_keys().add(self._host, "ssh-rsa", self._host_keys)
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.WarningPolicy())
        client.connect(
            hostname=self._host,
            port=self._port,
            username=self._user,
            pkey=self._pkey,
            allow_agent=False,
            look_for_keys=False,
            timeout=15,
        )
        return client

    def run(self, command: str, *, timeout: int = 300) -> CommandResult:
        client = self.connect()
        try:
            _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            code = stdout.channel.recv_exit_status()
            return CommandResult(exit_code=code, stdout=out, stderr=err)
        finally:
            client.close()

    def put(self, data: str | bytes, remote_path: str, *, mode: int = 0o600) -> None:
        client = self.connect()
        try:
            sftp = client.open_sftp()
            try:
                payload = data.encode("utf-8") if isinstance(data, str) else data
                with sftp.open(remote_path, "wb") as fp:
                    fp.write(payload)
                sftp.chmod(remote_path, mode)
            finally:
                sftp.close()
        finally:
            client.close()

    @staticmethod
    def _load_pkey(pem: str) -> paramiko.PKey:
        for loader in (
            paramiko.RSAKey.from_private_key,
            paramiko.Ed25519Key.from_private_key,
            paramiko.ECDSAKey.from_private_key,
        ):
            try:
                return loader(io.StringIO(pem))
            except paramiko.PasswordRequiredException:
                raise
            except Exception:
                continue
        raise ValueError("no supported private key found in SSH_PRIVATE_KEY")

    @staticmethod
    def _load_host_keys(pem: str) -> paramiko.RSAKey:
        return paramiko.RSAKey.from_private_key(io.StringIO(pem))


def write_atomic(path: str, lines: Iterable[str]) -> str:
    return "\n".join(lines) + "\n"
