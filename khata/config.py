from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    db_path: Path
    media_dir: Path
    secret: str
    user: str
    tz: str

    @classmethod
    def load(cls) -> Config:
        db_path = Path(os.getenv("KHATA_DB_PATH", REPO_ROOT / "data" / "khata.db"))
        media_dir = Path(os.getenv("KHATA_MEDIA_DIR", REPO_ROOT / "data" / "media"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            db_path=db_path,
            media_dir=media_dir,
            secret=os.getenv("KHATA_SECRET", "dev-insecure-secret"),
            user=os.getenv("KHATA_USER", "default"),
            tz=os.getenv("KHATA_TZ", "Asia/Kolkata"),
        )


@dataclass(frozen=True)
class DhanCreds:
    client_id: str
    access_token: str

    @classmethod
    def from_env(cls) -> DhanCreds | None:
        cid = os.getenv("DHAN_CLIENT_ID", "").strip()
        tok = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
        if not cid or not tok:
            return None
        return cls(client_id=cid, access_token=tok)
