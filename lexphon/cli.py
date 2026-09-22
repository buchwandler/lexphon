from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from http import HTTPStatus

from . import __version__
from .catalog import CatalogArtifact, load_catalog
from .engine import Phonemizer
from .errors import DataDownloadError, LexphonError, UnsupportedAlphabetError
from .inspection import (
    LexiconEntryInspection,
    OpaqueDisplayResolver,
    RawPhonemizationResult,
    RawPronunciationToken,
    inspect_entry,
)
from .layers import ensure_normalizable_encoding, open_installed_pronunciation_layer
from .profiles import ProfileRegistry
from .store import DataStore

_ROOT_EPILOG = """examples:
  lexphon data available de-DE
  lexphon data install de-de:gold
  lexphon phonemize --language de-DE \"Die Leute kommen.\"
  lexphon languages
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
    sub.add_parser(
        "phonemize",
        help="Phonemize text with installed lexicons; normalize generic encodings to IPA",
    )
    sub.add_parser(
        "lookup",
        help="Inspect one stored G2Lex pronunciation entry",
    )
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
    print("The failed lexicon was not installed.", file=sys.stderr)
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
                f"{available_artifact.id}\t{available_artifact.display_name}\t"
                f"{available_artifact.language}\t{available_artifact.phoneme_encoding}\t"
                f"{available_artifact.data_version}\t{available_artifact.release_tag}"
            )
    return 0


def _languages_main() -> int:
    for profile in ProfileRegistry().profiles:
        print(profile.language)
    return 0


def _build_lookup_parser(*, prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Inspect the exact stored G2Lex value for one word without requiring "
            "an IPA-normalizable pronunciation encoding."
        ),
    )
    parser.add_argument(
        "-l",
        "--language",
        required=True,
        metavar="LANGUAGE",
        help="language profile, for example en-US",
    )
    parser.add_argument(
        "--lexicon",
        required=True,
        metavar="ID",
        help="installed pronunciation lexicon ID",
    )
    parser.add_argument(
        "--tag",
        help="selector tag to resolve while displaying every stored tag",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--data-home", metavar="PATH")
    parser.add_argument("word")
    return parser


def _lookup_payload(entry: LexiconEntryInspection) -> dict[str, object]:
    return {
        "schema_version": 1,
        "query": entry.query,
        "language": entry.language,
        "lexicon_id": entry.lexicon_id,
        "matched_key": entry.matched_key,
        "source_encoding": entry.source_encoding,
        "kind": entry.kind,
        "available_tags": list(entry.available_tags),
        "requested_tag": entry.requested_tag,
        "selected_tag": entry.selected_tag,
        "selected_via": entry.selected_via,
        "stored": [
            {
                "tag": item.tag,
                "value": None if item.values is None else list(item.values),
            }
            for item in entry.stored
        ],
        "selected": list(entry.selected_values),
    }


def _print_lookup_entry(entry: LexiconEntryInspection) -> None:
    print(f"word:            {entry.query}")
    print(f"matched_key:     {entry.matched_key}")
    print(f"language:        {entry.language}")
    print(f"lexicon:         {entry.lexicon_id}")
    print(f"encoding:        {entry.source_encoding}")
    print(f"kind:            {entry.kind}")
    print(f"available_tags:  {', '.join(entry.available_tags) or '-'}")
    print(f"requested_tag:   {entry.requested_tag or '-'}")
    print(f"selected_tag:    {entry.selected_tag or '-'}")
    print(f"selected_via:    {entry.selected_via}")
    print()
    print("stored:")
    for item in entry.stored:
        if item.tag is None:
            if item.values is None:
                print("  - null")
            elif not item.values:
                print("  - []")
            else:
                for value in item.values:
                    print(f"  - {value}")
            continue
        if item.values is None:
            print(f"  {item.tag}: null")
        elif not item.values:
            print(f"  {item.tag}: []")
        else:
            print(f"  {item.tag}:")
            for value in item.values:
                print(f"    - {value}")
    print()
    print("selected:")
    selected_item = next(
        (item for item in entry.stored if item.tag == entry.selected_tag),
        None,
    )
    if selected_item is not None and selected_item.values is None:
        print("  null")
    elif selected_item is not None and not selected_item.values:
        print("  []")
    elif entry.selected_values:
        for value in entry.selected_values:
            print(f"  - {value}")
    else:
        print("  -")


def _lookup_main(argv: list[str]) -> int:
    parser = _build_lookup_parser(prog="lexphon lookup")
    args = parser.parse_args(argv)
    entry = inspect_entry(
        args.word,
        language=args.language,
        lexicon_id=args.lexicon,
        tag=args.tag,
        store=DataStore(args.data_home),
    )
    if entry is None:
        print(f"lexphon: {args.word!r} was not found in {args.lexicon}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(_lookup_payload(entry), ensure_ascii=False))
    else:
        _print_lookup_entry(entry)
    return 0


def _selected_lexicon_ids(language: str, lexicons: list[str] | None) -> tuple[str, ...]:
    if lexicons is not None:
        return tuple(lexicons)
    return ProfileRegistry().resolve(language).default_lexicons


def _preflight_opaque_display(
    language: str,
    lexicon_ids: tuple[str, ...],
    store: DataStore,
    fallback: str,
) -> str | None:
    layers = []
    try:
        profile = ProfileRegistry().resolve(language)
        for identifier in lexicon_ids:
            layers.append(open_installed_pronunciation_layer(store, profile.language, identifier))
        opaque_layers = []
        for layer in layers:
            try:
                ensure_normalizable_encoding(layer.encoding, layer.identifier)
            except UnsupportedAlphabetError:
                opaque_layers.append(layer)
        if not opaque_layers:
            return None
        if fallback != "none":
            raise LexphonError(
                f"fallback {fallback!r} returns IPA and cannot be mixed with "
                f"{opaque_layers[0].encoding} display output"
            )
        encodings = {layer.encoding.casefold() for layer in layers}
        if len(encodings) != 1:
            details = "\n".join(f"  {layer.identifier}: {layer.encoding}" for layer in layers)
            raise LexphonError(
                "cannot render mixed source encodings in display mode:\n"
                f"{details}\n"
                "Use one source encoding at a time, or select an IPA-compatible lexicon."
            )
        return opaque_layers[0].encoding
    finally:
        for layer in layers:
            layer.lexicon.close()


def _raw_token_payload(
    token: RawPronunciationToken,
    language: str,
) -> dict[str, object]:
    return {
        "text": token.text,
        "source": token.source,
        "provider": None,
        "requested_language": language,
        "lexicon_id": token.lexicon_id,
        "matched_key": token.matched_key,
        "source_encoding": token.source_encoding,
        "selector_tag": token.selector_tag,
        "known": token.known,
        "punctuation": token.punctuation,
        "pronunciation": token.pronunciation,
        "source_pronunciation": token.source_pronunciation,
        "language_markers": [],
        "variants": [
            {
                "pronunciation": variant.pronunciation,
                "source_pronunciation": variant.source_pronunciation,
                "language_markers": [],
            }
            for variant in token.variants
        ],
    }


def _print_opaque_result(
    result: RawPhonemizationResult,
    *,
    encoding: str,
    unknown: str,
    punctuation: str,
    as_json: bool,
) -> None:
    if as_json:
        payload = {
            "schema_version": 2,
            "text": result.text,
            "language": result.language,
            "output_encoding": encoding,
            "normalized_to_ipa": False,
            "phonemes": result.render(unknown=unknown, punctuation=punctuation),
            "tokens": [_raw_token_payload(token, result.language) for token in result.tokens],
        }
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(result.render(unknown=unknown, punctuation=punctuation))


def _phonemize_opaque(
    args: argparse.Namespace,
    text: str,
    *,
    store: DataStore,
    lexicon_ids: tuple[str, ...],
    encoding: str,
) -> int:
    print(
        f"lexphon: displaying stored {encoding} pronunciations unchanged",
        file=sys.stderr,
    )
    with OpaqueDisplayResolver(
        args.language,
        lexicons=lexicon_ids,
        store=store,
    ) as resolver:
        result = resolver.phonemize_tokens(text, tag=args.tag)
        _print_opaque_result(
            result,
            encoding=encoding,
            unknown=args.unknown,
            punctuation=args.punctuation,
            as_json=args.json,
        )
    return 0


def _build_phonemize_parser(*, prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Phonemize text with installed lexicons; normalize generic encodings to IPA. "
            "An explicitly selected opaque encoding is displayed unchanged for diagnostics."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "-l",
        "--language",
        dest="language",
        required=True,
        metavar="LANGUAGE",
        help="language profile, for example de-DE",
    )
    parser.add_argument(
        "--lexicon", action="append", dest="lexicons", help="installed lexicon ID; repeatable"
    )
    parser.add_argument("--tag", help="selector tag for tagged G2Lex values")
    parser.add_argument("--fallback", choices=["none", "espeak", "goruut"], default="none")
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
    store = DataStore(args.data_home)
    lexicon_ids = _selected_lexicon_ids(args.language, args.lexicons)
    opaque_encoding = _preflight_opaque_display(
        args.language,
        lexicon_ids,
        store,
        args.fallback,
    )
    if opaque_encoding is not None:
        return _phonemize_opaque(
            args,
            text,
            store=store,
            lexicon_ids=lexicon_ids,
            encoding=opaque_encoding,
        )
    with Phonemizer(
        args.language,
        lexicons=args.lexicons,
        store=store,
        fallback=None if args.fallback == "none" else args.fallback,
    ) as engine:
        result = engine.phonemize_tokens(text, tag=args.tag)
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 2,
                        "text": result.text,
                        "language": result.language,
                        "output_encoding": "ipa",
                        "normalized_to_ipa": True,
                        "phonemes": result.render(
                            unknown=args.unknown, punctuation=args.punctuation
                        ),
                        "tokens": [
                            {
                                "text": token.text,
                                "source": token.source,
                                "provider": token.provider,
                                "requested_language": token.requested_language,
                                "lexicon_id": token.lexicon_id,
                                "matched_key": token.matched_key,
                                "source_encoding": token.source_encoding,
                                "selector_tag": token.selector_tag,
                                "known": token.known,
                                "punctuation": token.punctuation,
                                "pronunciation": token.pronunciation,
                                "source_pronunciation": token.source_pronunciation,
                                "language_markers": [
                                    {
                                        "language": marker.language,
                                        "ipa_offset": marker.ipa_offset,
                                    }
                                    for marker in token.language_markers
                                ],
                                "variants": [
                                    {
                                        "pronunciation": variant.pronunciation,
                                        "source_pronunciation": variant.source_pronunciation,
                                        "language_markers": [
                                            {
                                                "language": marker.language,
                                                "ipa_offset": marker.ipa_offset,
                                            }
                                            for marker in variant.language_markers
                                        ],
                                    }
                                    for variant in token.variants
                                ],
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
        if args[0] == "lookup":
            return _lookup_main(args[1:])
        if args[0] == "phonemize":
            return _phonemize_main(args[1:], prog="lexphon phonemize")
        if args[0] == "languages":
            return _languages_main()
        _build_root_parser().parse_args(args)
        return 0
    except DataDownloadError as exc:
        _format_download_error(exc)
        return 2
    except LexphonError as exc:
        if not _format_catalog_error(exc):
            print(f"lexphon: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
