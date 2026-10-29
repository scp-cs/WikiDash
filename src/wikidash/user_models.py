"""Wikidot user profile as stored in `_users/<bucket>.json`."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class UserActivity(IntEnum):
    """Wikidot's 'karma level'."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    VERY_HIGH = 4
    GURU = 5
    UNKNOWN = 6


@dataclass
class User:
    user_id: int
    username: str  # the slug used in profile URLs
    full_name: str  # display name
    wikidot_user_since: float  # unix SECONDS
    fetched_at: int  # unix MILLISECONDS
    activity: UserActivity = UserActivity.UNKNOWN
    real_name: str | None = None
    gender: str | None = None
    birthday: int | None = None  # unix MILLISECONDS
    location: str | None = None  # "From" on the profile
    website: str | None = None
    bio: str | None = None
    account_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON in the original key order; unset fields are left out."""
        fields: dict[str, Any] = {
            "full_name": self.full_name,
            "username": self.username,
            "real_name": self.real_name,
            "gender": self.gender,
            "birthday": self.birthday,
            "from": self.location,
            "website": self.website,
            "wikidot_user_since": self.wikidot_user_since,
            "bio": self.bio,
            "account_type": self.account_type,
            "activity": int(self.activity),
            "fetched_at": self.fetched_at,
            "user_id": self.user_id,
        }
        return {key: value for key, value in fields.items() if value is not None}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "User":
        return cls(
            user_id=raw["user_id"],
            username=raw["username"],
            full_name=raw["full_name"],
            wikidot_user_since=raw["wikidot_user_since"],
            fetched_at=raw["fetched_at"],
            activity=UserActivity(raw.get("activity", UserActivity.UNKNOWN)),
            real_name=raw.get("real_name"),
            gender=raw.get("gender"),
            birthday=raw.get("birthday"),
            location=raw.get("from"),
            website=raw.get("website"),
            bio=raw.get("bio"),
            account_type=raw.get("account_type"),
        )
