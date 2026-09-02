class LexphonError(Exception):
    """Base error for Lexphon."""


class CatalogError(LexphonError):
    """The remote or local data catalog is invalid."""


class LexiconNotInstalledError(LexphonError):
    """A requested G2Lex asset is not present in the local data store."""


class UnsupportedAlphabetError(LexphonError):
    """A pronunciation alphabet cannot be normalized to IPA."""


class UnknownWordError(LexphonError):
    """A token has no pronunciation and the caller requested strict handling."""
