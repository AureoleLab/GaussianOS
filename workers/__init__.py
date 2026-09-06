"""Out-of-process worker entry points."""

# The released training interpreter also hosts lightweight reconstruction
# workers. Keep Python 3.10 contract compatibility inside worker processes.
import enum
import typing

if not hasattr(enum, "StrEnum"):
    class _StrEnum(str, enum.Enum):
        def __str__(self):
            return str(self.value)

    enum.StrEnum = _StrEnum
if not hasattr(typing, "Self"):
    from typing_extensions import Self
    typing.Self = Self
