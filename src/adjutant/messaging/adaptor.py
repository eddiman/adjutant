"""Messaging adaptor interface contract.

Replaces: scripts/messaging/adaptor.sh

Any backend (Telegram, Slack, Discord) must implement this ABC.
The default implementations raise NotImplementedError for required methods
and are no-ops for optional methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class MessagingAdaptor(ABC):
    """Abstract base class defining the messaging adaptor interface."""

    # REQUIRED

    @abstractmethod
    async def send_text(self, message: str, reply_to_message_id: int | None = None) -> None:
        """Send a text message.

        Args:
            message: The text to send. Sanitisation is the implementation's responsibility.
            reply_to_message_id: If set, reply to this message ID.
        """
        ...

    @abstractmethod
    async def send_photo(self, file_path: Path, caption: str = "") -> None:
        """Send a photo file.

        Args:
            file_path: Absolute path to the image file.
            caption: Optional caption for the photo.
        """
        ...

    @abstractmethod
    async def start_listener(self) -> None:
        """Start the polling/webhook listener loop."""
        ...

    @abstractmethod
    async def stop_listener(self) -> None:
        """Stop the listener loop cleanly."""
        ...

    # OPTIONAL (default no-ops)

    async def react(self, message_id: int, emoji: str = "👀") -> None:
        """Add a reaction emoji to a message. Default: no-op.

        Args:
            message_id: The message to react to.
            emoji: The emoji reaction to add.
        """
        pass

    async def typing(self, action: str, suffix: str = "default") -> None:
        """Send a typing indicator. Default: no-op.

        Args:
            action: 'start' or 'stop'.
            suffix: Unique key to identify concurrent typing indicators.
        """
        pass

    def authorize(self, from_id: str) -> bool:
        """Check if a sender is authorised. Default: allow all.

        Args:
            from_id: The sender's identifier.

        Returns:
            True if authorised, False otherwise.
        """
        return True

    def get_user_id(self) -> str:
        """Return the authenticated user / chat identifier. Default: 'unknown'."""
        return "unknown"
