"""Provider parity benchmark: compare two Lexphon provider configurations.

Usage:
    python benchmarks/provider_parity.py \
        --provider espeak \
        --language en-US \
        --left-mode native \
        --right-mode cli \
        --input benchmarks/data/en_provider_parity.txt \
        --json provider-parity.json \
        --markdown provider-parity.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lexphon.providers import EspeakProvider


def _create_provider(provider: str, mode: str | None = None) -> Any:
    """Create a provider instance."""
    if provider == "espeak":
        return EspeakProvider(mode=mode)
    raise ValueError(f"Unknown provider: {provider}")


def _load_inputs(input_path: Path) -> list[str]:
    """Load input texts from file, one per line."""
    return [
        line.strip() for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def compare_providers(
    provider_name: str,
    language: str,
    left_mode: str,
    right_mode: str,
    inputs: list[str],
) -> dict[str, Any]:
    """Compare two provider configurations and return results."""
    left = _create_provider(provider_name, left_mode)
    right = _create_provider(provider_name, right_mode)

    try:
        results = []
        exact_matches = 0
        total = len(inputs)

        for text in inputs:
            left_result = left.phonemize(text, language)
            right_result = right.phonemize(text, language)
            is_exact = left_result == right_result
            if is_exact:
                exact_matches += 1

            results.append(
                {
                    "text": text,
                    "left": left_result,
                    "right": right_result,
                    "exact_match": is_exact,
                }
            )

        # Collect runtime diagnostics
        left_diag = left.diagnostic_info() if hasattr(left, "diagnostic_info") else {}
        right_diag = right.diagnostic_info() if hasattr(right, "diagnostic_info") else {}

        return {
            "provider": provider_name,
            "language": language,
            "left_mode": left_mode,
            "right_mode": right_mode,
            "total_inputs": total,
            "exact_matches": exact_matches,
            "exact_match_rate": round(exact_matches / total, 6) if total > 0 else 0.0,
            "results": results,
            "left_diagnostics": left_diag,
            "right_diagnostics": right_diag,
        }
    finally:
        left.close()
        right.close()


def write_json_report(data: dict[str, Any], output_path: Path) -> None:
    """Write results as JSON."""
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown_report(data: dict[str, Any], output_path: Path) -> None:
    """Write results as Markdown."""
    lines = [
        "# Provider Parity Report",
        "",
        f"**Provider:** {data['provider']}",
        f"**Language:** {data['language']}",
        f"**Left mode:** {data['left_mode']}",
        f"**Right mode:** {data['right_mode']}",
        "",
        "## Summary",
        "",
        f"- Total inputs: {data['total_inputs']}",
        f"- Exact matches: {data['exact_matches']}",
        f"- Match rate: {data['exact_match_rate']:.2%}",
        "",
        "## Runtime Diagnostics",
        "",
        f"### Left ({data['left_mode']})",
        "",
    ]

    for key, value in data["left_diagnostics"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            f"### Right ({data['right_mode']})",
            "",
        ]
    )

    for key, value in data["right_diagnostics"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Results",
            "",
            "| Text | Left | Right | Match |",
            "|------|------|-------|-------|",
        ]
    )

    for result in data["results"]:
        match_icon = "✓" if result["exact_match"] else "✗"
        left = result["left"] or "None"
        right = result["right"] or "None"
        lines.append(f"| {result['text']} | {left} | {right} | {match_icon} |")

    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two Lexphon provider configurations.")
    parser.add_argument("--provider", required=True, help="Provider name (e.g., espeak)")
    parser.add_argument("--language", required=True, help="Language code (e.g., en-US)")
    parser.add_argument("--left-mode", required=True, help="Left provider mode (e.g., native)")
    parser.add_argument("--right-mode", required=True, help="Right provider mode (e.g., cli)")
    parser.add_argument(
        "--input", required=True, type=Path, help="Input file with one text per line"
    )
    parser.add_argument("--json", type=Path, help="JSON output path")
    parser.add_argument("--markdown", type=Path, help="Markdown output path")

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    inputs = _load_inputs(args.input)
    if not inputs:
        print("Error: No inputs found in file", file=sys.stderr)
        sys.exit(1)

    results = compare_providers(
        provider_name=args.provider,
        language=args.language,
        left_mode=args.left_mode,
        right_mode=args.right_mode,
        inputs=inputs,
    )

    # Print summary to stdout
    print(f"Provider: {results['provider']}")
    print(f"Language: {results['language']}")
    print(f"Left: {results['left_mode']}, Right: {results['right_mode']}")
    print(
        f"Exact matches: {results['exact_matches']}/{results['total_inputs']} ({results['exact_match_rate']:.2%})"
    )

    # Write reports
    if args.json:
        write_json_report(results, args.json)
        print(f"\nJSON report written to: {args.json}")

    if args.markdown:
        write_markdown_report(results, args.markdown)
        print(f"Markdown report written to: {args.markdown}")


if __name__ == "__main__":
    main()
