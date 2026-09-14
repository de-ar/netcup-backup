from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import paramiko

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SshConnection:
    host: str
    port: int
    user: str
    private_key: str
    host_keys: str = ""


@dataclass(frozen=True)
class Upload:
    data: str | bytes
    remote_path: str
    mode: int = 0o644


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SshClient:
    def __init__(self, conn: SshConnection) -> None:
        self._conn = conn
        self._pkey = self._load_pkey(self._normalize(conn.private_key))
        self._host_keys = self._load_host_keys(self._normalize(conn.host_keys)) if conn.host_keys else None

    def connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        if self._host_keys is not None:
            client.get_host_keys().add(self._conn.host, "ssh-rsa", self._host_keys)
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.WarningPolicy())
        client.connect(
            hostname=self._conn.host,
            port=self._conn.port,
            username=self._conn.user,
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

    def put(self, upload: Upload) -> None:
        client = self.connect()
        try:
            sftp = client.open_sftp()
            try:
                payload = (
                    upload.data.encode("utf-8") if isinstance(upload.data, str) else upload.data
                )
                with sftp.open(upload.remote_path, "wb") as fp:
                    fp.write(payload)
                sftp.chmod(upload.remote_path, upload.mode)
            finally:
                sftp.close()
        finally:
            client.close()

    @staticmethod
    def _normalize(value: str) -> str:
        v = value.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        return v.replace("\\r\n", "\n").replace("\\n", "\n").replace("\\r", "\n")

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
        log.error(
            "SSH_PRIVATE_KEY could not be parsed (len=%d, head=%r, tail=%r)",
            len(pem),
            pem[:30],
            pem[-30:],
        )
        raise ValueError("no supported private key found in SSH_PRIVATE_KEY")

    @staticmethod
    def _load_host_keys(pem: str) -> paramiko.RSAKey:
        return paramiko.RSAKey.from_private_key(io.StringIO(pem))
