from enum import StrEnum


class AccountStatus(StrEnum):
    """Whether an account may log in.

    PAUSED -- the default for new accounts; logging in is refused.
    ACTIVE -- set when the user completes the activation link, or manually by a SUPER_ADMIN.
    """

    PAUSED = "PAUSED"
    ACTIVE = "ACTIVE"
