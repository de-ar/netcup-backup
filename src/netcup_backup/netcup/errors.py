from __future__ import annotations


class NetcupError(RuntimeError):
    pass


class NetcupBusy(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"busy {status}: {body}")
        self.status = status
        self.body = body
