"""Netscape cookies.txt 解析与脱敏摘要。"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class CookieRecord:
    domain: str
    expires_at: int
    name: str
    value: str


def parse_netscape_cookies(
    path: str | os.PathLike[str],
    *,
    now: float | None = None,
    domain_suffix: str | None = None,
) -> list[CookieRecord]:
    """读取有效 cookie；跳过注释、格式错误和已过期项。"""
    try:
        lines = Path(path).expanduser().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    current = time.time() if now is None else now
    records: list[CookieRecord] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_") :]
        elif not line or line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain = parts[0].lstrip(".").lower()
        if domain_suffix:
            suffix = domain_suffix.lstrip(".").lower()
            if domain != suffix and not domain.endswith(f".{suffix}"):
                continue
        try:
            expires = int(parts[4])
        except ValueError:
            expires = 0
        if expires and expires < current:
            continue
        name, value = parts[5], parts[6]
        if name:
            records.append(
                CookieRecord(
                    domain=domain,
                    expires_at=expires,
                    name=name,
                    value=value,
                )
            )
    return records


def build_cookie_header(records: list[CookieRecord]) -> str:
    return "; ".join(f"{record.name}={record.value}" for record in records)


def cookie_summary(records: list[CookieRecord]) -> tuple[int, str | None]:
    """返回 (有效 cookie 数, 最近过期时间 ISO 8601)。"""
    expiries = [record.expires_at for record in records if record.expires_at > 0]
    expires_at = (
        datetime.fromtimestamp(min(expiries), tz=UTC).isoformat(timespec="seconds")
        if expiries
        else None
    )
    return len(records), expires_at
