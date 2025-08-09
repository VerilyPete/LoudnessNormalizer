#!/usr/bin/env python3
"""
Unified Video Loudness CLI

Subcommands:
  - check: Analyze loudness and write a report
  - normalize: Normalize files using a prior report
  - auto: Run check then normalize in one go

Usage examples:
  # Check a folder
  python loudness.py check ./videos

  # Normalize from an existing report
  python loudness.py normalize report.txt --yes

  # One-shot: check then normalize out-of-spec files
  python loudness.py auto ./videos --target -18 --yes
"""

import sys
import argparse
from pathlib import Path

from loudness_checker import VideoLoudnessChecker
from loudness_normalizer import VideoNormalizer, DEFAULT_TARGET_LUFS, DEFAULT_TRUE_PEAK, DEFAULT_LRA

PRESET_TO_LUFS = {
    "broadcast": -24.0,  # -24 LUFS (aka -23 LKFS elsewhere)
    "gaming": -16.0,
    "podcast": -16.0,
}


def cmd_check(args: argparse.Namespace) -> int:
    checker = VideoLoudnessChecker(args.folder)
    return checker.run()


def _resolve_target_lufs(args: argparse.Namespace) -> float:
    # Explicit --target wins
    if args.target is not None:
        return args.target
    # Then preset if provided
    if getattr(args, "preset", None):
        return PRESET_TO_LUFS[args.preset]
    # Fallback to default
    return DEFAULT_TARGET_LUFS


def cmd_normalize(args: argparse.Namespace) -> int:
    target_lufs = _resolve_target_lufs(args)
    normalizer = VideoNormalizer(
        report_file=args.report,
        target_lufs=target_lufs,
        true_peak=args.true_peak,
        lra=args.lra,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        in_place=args.in_place,
        assume_yes=args.yes,
    )
    return normalizer.run()


def cmd_auto(args: argparse.Namespace) -> int:
    # 1) Check
    checker = VideoLoudnessChecker(args.folder)
    check_rc = checker.run()
    if check_rc != 0:
        return check_rc

    # Compute out-of-spec count from results if available
    out_of_spec = 0
    for result in getattr(checker, 'results', []):
        status, _ = result.get('status', ('OK', 0.0))
        if status != 'OK':
            out_of_spec += 1

    if out_of_spec == 0:
        print("All files are within spec. Nothing to normalize.")
        return 0

    report_path = Path(getattr(checker, 'report_file', ''))
    if not report_path:
        print("Error: Could not determine report file path from check step.")
        return 1

    # 2) Normalize with the generated report
    target_lufs = _resolve_target_lufs(args)
    normalizer = VideoNormalizer(
        report_file=str(report_path),
        target_lufs=target_lufs,
        true_peak=args.true_peak,
        lra=args.lra,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        in_place=args.in_place,
        assume_yes=args.yes,
    )
    return normalizer.run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified CLI for checking and normalizing video loudness",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # check
    p_check = subparsers.add_parser("check", help="Analyze a folder and write a loudness report")
    p_check.add_argument("folder", nargs="?", default=".", help="Folder containing video files (default: current directory)")
    p_check.set_defaults(func=cmd_check)

    # normalize
    p_norm = subparsers.add_parser("normalize", help="Normalize files based on a loudness report")
    p_norm.add_argument("report", help="Path to loudness report file")
    p_norm.add_argument("--target", "-t", type=float, default=None, help=f"Explicit target LUFS (overrides --preset). Default if unset: {DEFAULT_TARGET_LUFS}")
    p_norm.add_argument("--preset", choices=sorted(PRESET_TO_LUFS.keys()), help="Target preset: broadcast (-24), gaming (-16), podcast (-16)")
    p_norm.add_argument("--true-peak", "-tp", type=float, default=DEFAULT_TRUE_PEAK, help=f"True peak limit in dB (default: {DEFAULT_TRUE_PEAK})")
    p_norm.add_argument("--lra", type=float, default=DEFAULT_LRA, help=f"Loudness range in LU (default: {DEFAULT_LRA})")
    p_norm.add_argument("--output-dir", "-o", type=str, help="Directory to save normalized files")
    p_norm.add_argument("--in-place", "-i", action="store_true", help="Replace original files (backup by default)")
    p_norm.add_argument("--no-backup", action="store_true", help="Skip backup when using --in-place")
    p_norm.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done without processing files")
    p_norm.add_argument("--yes", "-y", action="store_true", help="Proceed without confirmation prompt")
    p_norm.set_defaults(func=cmd_normalize)

    # auto
    p_auto = subparsers.add_parser("auto", help="Run check then normalize out-of-spec files")
    p_auto.add_argument("folder", nargs="?", default=".", help="Folder containing video files (default: current directory)")
    p_auto.add_argument("--target", "-t", type=float, default=None, help=f"Explicit target LUFS (overrides --preset). Default if unset: {DEFAULT_TARGET_LUFS}")
    p_auto.add_argument("--preset", choices=sorted(PRESET_TO_LUFS.keys()), help="Target preset: broadcast (-24), gaming (-16), podcast (-16)")
    p_auto.add_argument("--true-peak", "-tp", type=float, default=DEFAULT_TRUE_PEAK, help=f"True peak limit in dB (default: {DEFAULT_TRUE_PEAK})")
    p_auto.add_argument("--lra", type=float, default=DEFAULT_LRA, help=f"Loudness range in LU (default: {DEFAULT_LRA})")
    p_auto.add_argument("--output-dir", "-o", type=str, help="Directory to save normalized files")
    p_auto.add_argument("--in-place", "-i", action="store_true", help="Replace original files (backup by default)")
    p_auto.add_argument("--no-backup", action="store_true", help="Skip backup when using --in-place")
    p_auto.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done without processing files")
    p_auto.add_argument("--yes", "-y", action="store_true", help="Proceed without confirmation prompt")
    p_auto.set_defaults(func=cmd_auto)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())


