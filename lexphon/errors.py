class LexphonError(Exception):
    """Base error for Lexphon."""


class CatalogError(LexphonError):
    """The remote or local data catalog is invalid."""


class DataDownloadError(LexphonError):
    """A catalog-referenced manifest or asset could not be retrieved."""

    def __init__(
        self,
        *,
        identifier: str,
        resource: str,
        url: str,
        release_tag: str,
        data_version: str,
        status_code: int | None = None,
        reason: str | None = None,
    ) -> None:
        self.identifier = identifier
        self.resource = resource
        self.url = url
        self.release_tag = release_tag
        self.data_version = data_version
        self.status_code = status_code
        self.reason = reason
        detail = f"{status_code} {reason}" if status_code is not None else reason
        message = f"unable to download {resource} for {identifier}"
        if detail:
            message += f": {detail}"
        super().__init__(message)


class DataIntegrityError(LexphonError):
    """An installed or downloaded data artifact violates its contract."""


class LexiconNotInstalledError(LexphonError):
    """A requested G2Lex asset is not present in the local data store."""


class LexiconNotUsableError(LexphonError):
    """An installed asset cannot be used as a pronunciation layer."""


class UnsupportedAlphabetError(LexphonError):
    """A pronunciation alphabet cannot be normalized to IPA."""


class UnknownWordError(LexphonError):
    """A token has no pronunciation and the caller requested strict handling."""
