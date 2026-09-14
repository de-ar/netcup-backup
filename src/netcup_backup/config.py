from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    netcup_refresh_token: str = Field(min_length=10)
    netcup_server_id: str = Field(min_length=1)
    netcup_keep: int = Field(default=1, ge=1, le=3)

    backup_cron: str = Field(default="0 3 * * *")

    ssh_host: str = Field(min_length=1)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str = Field(default="root", min_length=1)
    ssh_private_key: str = Field(min_length=1)
    ssh_host_keys: str = Field(default="")

    restic_bin: str = Field(default="/usr/local/bin/restic")
    restic_repository: str = Field(min_length=1)
    restic_password: str = Field(min_length=1)
    restic_paths: str = Field(default="/")
    restic_exclude: str = Field(default="/tmp,/proc,/sys,/run,/var/cache")
    restic_cron: str = Field(default="30 3 * * *")

    r2_access_key_id: str = Field(min_length=1)
    r2_secret_access_key: str = Field(min_length=1)
    aws_default_region: str = Field(default="auto")

    r2_keep: int = Field(default=4, ge=1, le=365)
    prune_cron: str = Field(default="0 4 * * 0")

    health_host: str = Field(default="0.0.0.0")
    health_port: int = Field(default=8080, ge=1, le=65535)

    log_level: str = Field(default="INFO")

    @field_validator("netcup_server_id")
    @classmethod
    def lowercase_id(cls, v: str) -> str:
        return v.strip()

    @property
    def backup_paths(self) -> list[str]:
        return [p.strip() for p in self.restic_paths.split(",") if p.strip()]

    @property
    def exclude_paths(self) -> list[str]:
        return [p.strip() for p in self.restic_exclude.split(",") if p.strip()]

    @property
    def restic_env_lines(self) -> list[str]:
        return [
            f"RESTIC_REPOSITORY={self.restic_repository}",
            f"RESTIC_PASSWORD={self.restic_password}",
            f"AWS_ACCESS_KEY_ID={self.r2_access_key_id}",
            f"AWS_SECRET_ACCESS_KEY={self.r2_secret_access_key}",
            f"AWS_DEFAULT_REGION={self.aws_default_region}",
        ]
