"""Shared network helpers used by the plugin's HTTP download paths."""

from urllib.parse import urlparse


def require_https(url):
    """Reject non-HTTPS URLs before passing them to urllib.

    Bandit (B310) flags ``urlopen``/``urlretrieve`` because the underlying
    ``urllib`` machinery accepts ``file://``, ``ftp://`` and other schemes
    that can be turned into local-file disclosure if the URL is
    attacker-controlled. The plugin only ever fetches from hard-coded
    ``https://`` constants (GitHub for plugin updates, Earth Engine for
    image downloads), but this guard makes that invariant explicit and
    fail-closed at every call site so a future regression cannot silently
    introduce a non-https fetch.

    Args:
        url: The URL about to be opened.

    Raises:
        ValueError: If ``url`` is not an ``https://`` URL.
    """
    if urlparse(url).scheme != "https":
        raise ValueError(f"Refusing non-https URL: {url}")
