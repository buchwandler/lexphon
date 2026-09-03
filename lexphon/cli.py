from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .catalog import CatalogArtifact, load_catalog
from .engine import Phonemizer
from .errors import LexphonError
from .profiles import ProfileRegistry
from .store import DataStore


def _data_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="lexphon data", description="Manage installed G2Lex pronunciation data"
    )
    parser.add_argument("--catalog", help="catalog URL/path (default: g2lex-data main catalog)")
    parser.add_argument("--data-home")
    sub = parser.add_subparsers(dest="command", required=True)
    p_install = sub.add_parser("install")
    p_install.add_argument("id", nargs="+")
    sub.add_parser("list")
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("id", nargs="*")
    p_remove = sub.add_parser("remove")
    p_remove.add_argument("id", nargs="+")
    p_info = sub.add_parser("info")
    p_info.add_argument("id", nargs="+")
    p_available = sub.add_parser("available")
    p_available.add_argument("language", nargs="?")
    args = parser.parse_args(argv)
    store = DataStore(args.data_home)

    if args.command == "install":
        catalog = load_catalog(args.catalog)
        for identifier in args.id:
            path = store.install(catalog.artifact(identifier))
            print(f"installed {identifier}: {path}")
    elif args.command == "list":
        for item in store.installed():
            print(f"{item['id']}\t{item['data_version']}\t{item['phoneme_encoding']}")
    elif args.command == "info":
        for identifier in args.id:
            print(json.dumps(store.metadata(identifier), ensure_ascii=False, sort_keys=True))
    elif args.command == "verify":
        ids = args.id or [item["id"] for item in store.installed()]
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
        for available_artifact in available_artifacts:
            print(
                f"{available_artifact.id}\t{available_artifact.language}\t"
                f"{available_artifact.phoneme_encoding}\t{available_artifact.data_version}"
            )
    return 0


def _voices_main() -> int:
    for profile in ProfileRegistry().profiles:
        print(profile.language)
    return 0


def _phonemize_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lexphon", description="Lexicon-driven IPA phonemizer")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("-v", "--voice", "--language", dest="language", required=True)
    parser.add_argument(
        "--lexicon", action="append", dest="lexicons", help="installed lexicon id; repeatable"
    )
    parser.add_argument("--tag", help="selector tag for tagged G2Lex values")
    parser.add_argument("--fallback", choices=["none", "espeak"], default="none")
    parser.add_argument("--unknown", choices=["error", "keep", "skip"], default="error")
    parser.add_argument("--punctuation", choices=["keep", "drop"], default="keep")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--data-home")
    parser.add_argument("text", nargs="*")
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


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args and args[0] == "data":
            return _data_main(args[1:])
        if args and args[0] == "voices":
            return _voices_main()
        return _phonemize_main(args)
    except LexphonError as exc:
        print(f"lexphon: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
