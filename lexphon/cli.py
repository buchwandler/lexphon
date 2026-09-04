from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from http import HTTPStatus

from . import __version__
from .catalog import CatalogArtifact, load_catalog
from .engine import Phonemizer
from .errors import DataDownloadError, LexphonError
from .profiles import ProfileRegistry
from .store import DataStore

_ROOT_EPILOG = """examples:
  lexphon data available de-DE
  lexphon data install de-de:gold
  lexphon phonemize --language de-DE \"Die Leute kommen.\"
  lexphon languages

compatibility:
  The legacy form `lexphon -v de-DE \"Die Leute kommen.\"` is still accepted.
"""


def _build_root_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lexphon",
        description="Lexicon-driven IPA phonemizer using explicitly installed G2Lex data.",
        epilog=_ROOT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.add_parser("phonemize", help="Phonemize text with installed lexicons and return IPA")
    sub.add_parser(
        "data",
        help="Discover, install, inspect, verify, and remove lexicon data",
    )
    sub.add_parser("languages", help="List supported Lexphon language profiles")
    return parser


def _build_data_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lexphon data",
        description="Manage Lexphon pronunciation data.",
        epilog="""notes:
  `available` reads the catalog only. It does not prove that every referenced
  release manifest or asset is currently downloadable.

examples:
  lexphon data available de-DE
  lexphon data install de-de:gold
  lexphon data list
  lexphon data info de-de:gold
  lexphon data verify de-de:gold
  lexphon data remove de-de:gold
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--catalog",
        metavar="CATALOG",
        help="catalog URL or local path (default: g2lex-data main catalog)",
    )
    parser.add_argument(
        "--data-home",
        metavar="PATH",
        help="Lexphon data-store directory",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    p_available = sub.add_parser(
        "available",
        help="List lexicons declared by the selected catalog",
        description="List lexicons declared by the selected catalog.",
        epilog=(
            "This reads catalog metadata only. It does not download manifests or assets "
            "and does not verify that referenced release files are reachable."
        ),
    )
    p_available.add_argument(
        "language",
        metavar="LANGUAGE",
        nargs="?",
        help="optional locale filter, for example de-DE or en-US",
    )
    p_install = sub.add_parser(
        "install",
        help="Download, verify, and atomically install catalog lexicons",
        description="""Download, verify, and atomically install one or more catalog lexicons.

For each ID Lexphon resolves the catalog entry, downloads and verifies its
manifest and G2Lex asset, checks readability, and atomically activates the
complete version. A failed install does not activate partial data.
""",
    )
    p_install.add_argument(
        "id", metavar="ID", nargs="+", help="catalog lexicon ID, for example de-de:gold"
    )

    sub.add_parser(
        "list",
        help="List lexicons installed in the local data store",
        description="""List lexicons installed in the local Lexphon data store.

This command is offline and does not read the catalog.
""",
    )
    p_info = sub.add_parser(
        "info",
        help="Show metadata for installed lexicons",
        description="""Show local metadata for installed lexicons.

This command does not query the remote catalog.
""",
    )
    p_info.add_argument("id", metavar="ID", nargs="+", help="installed lexicon ID")
    p_verify = sub.add_parser(
        "verify",
        help="Verify hashes and readability of installed lexicons",
        description="""Verify installed lexicon files against local stored metadata and
confirm that each G2Lex asset can be opened. With no IDs, verify all installed
lexicons. This command is offline.
""",
    )
    p_verify.add_argument("id", metavar="ID", nargs="*", help="installed lexicon ID")
    p_remove = sub.add_parser(
        "remove",
        help="Remove installed lexicons from the local data store",
        description="""Remove one or more installed lexicons from the local data store.

This command does not alter the catalog or g2lex-data releases.
""",
    )
    p_remove.add_argument("id", metavar="ID", nargs="+", help="installed lexicon ID")
    return parser


def _format_download_error(error: DataDownloadError) -> None:
    print(f"lexphon: cannot install {error.identifier!r}", file=sys.stderr)
    print(file=sys.stderr)
    print(
        f"The catalog entry was found, but its {error.resource} is not available.",
        file=sys.stderr,
    )
    print(f"  release:      {error.release_tag}", file=sys.stderr)
    print(f"  data version: {error.data_version}", file=sys.stderr)
    if error.status_code is not None:
        try:
            status = f"{error.status_code} {HTTPStatus(error.status_code).phrase}"
        except ValueError:
            status = str(error.status_code)
        print(f"  HTTP status:  {status}", file=sys.stderr)
    else:
        print(f"  download/connectivity error: {error.reason}", file=sys.stderr)
    print(f"  URL:          {error.url}", file=sys.stderr)
    print(file=sys.stderr)
    print(
        "This usually means the referenced release is not published yet, "
        "is incomplete, or the catalog points to a missing file.",
        file=sys.stderr,
    )
    print("Nothing was installed.", file=sys.stderr)
    print(file=sys.stderr)
    print("Try:", file=sys.stderr)
    print(f"  lexphon data available {error.identifier.split(':', 1)[0]}", file=sys.stderr)


def _format_catalog_error(error: LexphonError) -> bool:
    message = str(error)
    prefix = "unknown catalog artifact: "
    if not message.startswith(prefix):
        return False
    identifier = message[len(prefix) :]
    print(f"lexphon: unknown catalog lexicon {identifier!r}", file=sys.stderr)
    print("Run:", file=sys.stderr)
    print(f"  lexphon data available {identifier.split(':', 1)[0]}", file=sys.stderr)
    print("to list catalog entries for the language.", file=sys.stderr)
    return True


def _data_main(argv: list[str]) -> int:
    parser = _build_data_parser()
    args = parser.parse_args(argv)
    store = DataStore(args.data_home)

    if args.command == "install":
        catalog = load_catalog(args.catalog)
        for identifier in args.id:
            path = store.install(catalog.artifact(identifier))
            print(f"installed {identifier}: {path}")
    elif args.command == "list":
        items = store.installed()
        if not items:
            print("No lexicons installed.")
        else:
            for item in items:
                print(f"{item['id']}\t{item['data_version']}\t{item['phoneme_encoding']}")
    elif args.command == "info":
        for identifier in args.id:
            print(json.dumps(store.metadata(identifier), ensure_ascii=False, sort_keys=True))
    elif args.command == "verify":
        ids = args.id or [item["id"] for item in store.installed()]
        if not ids:
            print("No lexicons installed; nothing to verify.")
            return 0
        failed = False
        for identifier in ids:
            ok = store.verify(identifier)
            print(f"{'OK' if ok else 'FAIL'}\t{identifier}")
            failed |= not ok
        return int(failed)
    elif args.command == "remove":
        for identifier in args.id:
            store.remove(identifier)
            print(f"removed {identifier}")
    elif args.command == "available":
        catalog = load_catalog(args.catalog)
        available_artifacts: tuple[CatalogArtifact, ...] = (
            catalog.for_language(args.language) if args.language else catalog.artifacts
        )
        if args.language and not available_artifacts:
            print(f"No catalog entries found for language {args.language!r}.")
            return 0
        for available_artifact in available_artifacts:
            print(
                f"{available_artifact.id}\t{available_artifact.language}\t"
                f"{available_artifact.phoneme_encoding}\t{available_artifact.data_version}\t"
                f"{available_artifact.release_tag}"
            )
    return 0


def _languages_main() -> int:
    for profile in ProfileRegistry().profiles:
        print(profile.language)
    return 0


def _voices_main() -> int:
    """Compatibility alias for the historical voices command."""
    return _languages_main()


def _build_phonemize_parser(*, prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Phonemize text with explicitly installed lexicons and return IPA.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "-l",
        "--language",
        "-v",
        "--voice",
        dest="language",
        required=True,
        metavar="LANGUAGE",
        help="language profile, for example de-DE (-v/--voice are compatibility aliases)",
    )
    parser.add_argument(
        "--lexicon", action="append", dest="lexicons", help="installed lexicon ID; repeatable"
    )
    parser.add_argument("--tag", help="selector tag for tagged G2Lex values")
    parser.add_argument("--fallback", choices=["none", "espeak"], default="none")
    parser.add_argument("--unknown", choices=["error", "keep", "skip"], default="error")
    parser.add_argument("--punctuation", choices=["keep", "drop"], default="keep")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--data-home", metavar="PATH")
    parser.add_argument("text", nargs="*")
    return parser


def _phonemize_main(argv: list[str], *, prog: str = "lexphon") -> int:
    parser = _build_phonemize_parser(prog=prog)
    args = parser.parse_args(argv)
    text = " ".join(args.text) if args.text else sys.stdin.read().strip()
    if not text:
        parser.error("text argument or stdin is required")
    with Phonemizer(
        args.language,
        lexicons=args.lexicons,
        store=DataStore(args.data_home),
        fallback=None if args.fallback == "none" else args.fallback,
    ) as engine:
        result = engine.phonemize_tokens(text, tag=args.tag)
        if args.json:
            print(
                json.dumps(
                    {
                        "text": result.text,
                        "language": result.language,
                        "phonemes": result.render(
                            unknown=args.unknown, punctuation=args.punctuation
                        ),
                        "tokens": [
                            {
                                "text": token.text,
                                "original_token": token.text,
                                "pronunciation": token.pronunciation,
                                "source": token.source,
                                "alphabet": token.alphabet,
                                "known": token.known,
                                "lexicon_id": token.lexicon_id,
                                "matched_key": token.matched_key,
                                "source_encoding": token.source_encoding,
                                "variants": list(token.variants),
                                "selector_tag": token.selector_tag,
                                "punctuation": token.punctuation,
                            }
                            for token in result.tokens
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(result.render(unknown=args.unknown, punctuation=args.punctuation))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if not args or args[0] in {"-h", "--help"}:
            if not args:
                _build_root_parser().print_help()
                return 0
            _build_root_parser().parse_args(args)
        if args[0] == "--version":
            _build_root_parser().parse_args(args)
        if args[0] == "data":
            return _data_main(args[1:])
        if args[0] == "phonemize":
            return _phonemize_main(args[1:], prog="lexphon phonemize")
        if args[0] in {"languages", "voices"}:
            return _languages_main()
        return _phonemize_main(args, prog="lexphon")
    except DataDownloadError as exc:
        _format_download_error(exc)
        return 2
    except LexphonError as exc:
        if not _format_catalog_error(exc):
            print(f"lexphon: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
