#!/usr/bin/env python3
"""
Unified Video Loudness CLI

Subcommands:
  - check: Analyze loudness and write a report
  - normalize: Normalize files using a prior report
  - auto: Run check then normalize in one go (DEFAULT if no subcommand)

Usage examples:
  # Default (auto): analyze then normalize
  python loudness.py --yes

  # Check a folder
  python loudness.py check ./videos

  # Normalize from an existing report
  python loudness.py normalize report.txt --yes

  # One-shot: check then normalize out-of-spec files
  python loudness.py auto ./videos --target -18 --yes
"""

import sys
import os
import argparse
import subprocess
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

PRESET_TO_LUFS = {
    "broadcast": -24.0,  # -24 LUFS (aka -23 LKFS elsewhere)
    "gaming": -16.0,
    "podcast": -16.0,
}


# Embedded analyzer/normalizer (from removed scripts)

# Video file extensions to check
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.m4v', '.webm', '.flv', '.wmv', '.mpg', '.mpeg'}

# Define target range for check (podcast/dialogue standard)
MIN_LUFS = -20
MAX_LUFS = -16

# Target loudness defaults for normalization (middle of podcast range)
DEFAULT_TARGET_LUFS = -18.0
DEFAULT_TRUE_PEAK = -1.5
DEFAULT_LRA = 11.0


class VideoLoudnessChecker:
    def __init__(self, folder_path: str = "."):
        self.folder_path = Path(folder_path)
        self.report_file = f"loudness_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.results: List[Dict] = []

    def check_dependencies(self) -> bool:
        if not shutil.which('ffmpeg'):
            print("Error: ffmpeg is not installed or not in PATH")
            return False
        return True

    def find_video_files(self) -> List[Path]:
        video_files: List[Path] = []
        if not self.folder_path.exists():
            print(f"Error: Folder '{self.folder_path}' does not exist")
            return video_files
        if not self.folder_path.is_dir():
            print(f"Error: '{self.folder_path}' is not a directory")
            return video_files
        for file in self.folder_path.iterdir():
            if file.is_file() and file.suffix.lower() in VIDEO_EXTENSIONS:
                video_files.append(file)
        video_files.sort()
        return video_files

    def analyze_loudness(self, file_path: Path) -> Optional[Dict]:
        try:
            cmd = ['ffmpeg', '-i', str(file_path), '-af', 'loudnorm=print_format=summary', '-f', 'null', '-']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            output = result.stderr + result.stdout
            lufs_value = self.extract_lufs(output)
            if lufs_value is not None:
                return {
                    'filename': file_path.name,
                    'path': str(file_path),
                    'lufs': lufs_value,
                    'status': self.check_compliance(lufs_value),
                }
            return None
        except subprocess.TimeoutExpired:
            print(f"  ERROR: Analysis timed out for {file_path.name}")
            return None
        except Exception as e:
            print(f"  ERROR: Failed to analyze {file_path.name}: {e}")
            return None

    def extract_lufs(self, ffmpeg_output: str) -> Optional[float]:
        patterns = [
            r'Input Integrated:\s+([-\d.]+)\s+LUFS',
            r'I:\s+([-\d.]+)\s+LUFS',
            r'input.*integrated.*?([-\d.]+)\s*LUFS',
        ]
        for pattern in patterns:
            match = re.search(pattern, ffmpeg_output, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        last_resort = re.search(r'([-\d.]+)\s*LUFS', ffmpeg_output, re.IGNORECASE)
        if last_resort:
            try:
                return float(last_resort.group(1))
            except ValueError:
                pass
        return None

    def check_compliance(self, lufs: float) -> Tuple[str, float]:
        if lufs < MIN_LUFS:
            deviation = MIN_LUFS - lufs
            return ('TOO_QUIET', deviation)
        elif lufs > MAX_LUFS:
            deviation = lufs - MAX_LUFS
            return ('TOO_LOUD', deviation)
        else:
            return ('OK', 0.0)

    def write_report(self, video_files: List[Path]) -> None:
        with open(self.report_file, 'w') as f:
            f.write("=== Video Loudness Analysis Report ===\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Folder: {self.folder_path.absolute()}\n")
            f.write(f"Target Range: {MIN_LUFS} to {MAX_LUFS} LUFS (podcast/dialogue)\n\n")

            total_files = len(video_files)
            analyzed_files = 0
            ok_files = 0
            too_quiet_files = 0
            too_loud_files = 0
            error_files = 0

            print(f"\nFound {total_files} video files to process\n")
            f.write(f"Found {total_files} video files to process\n\n")

            for i, file_path in enumerate(video_files, 1):
                print(f"Processing file {i}/{total_files}: {file_path.name}")
                print(f"  Full path: {file_path}")
                if not file_path.exists() or not os.access(file_path, os.R_OK):
                    error_msg = f"ERROR: {file_path.name} - File not readable\n"
                    print(f"  {error_msg}")
                    f.write(error_msg)
                    error_files += 1
                    continue
                result = self.analyze_loudness(file_path)
                if result:
                    analyzed_files += 1
                    status, deviation = result['status']
                    lufs = result['lufs']
                    if status == 'OK':
                        msg = f"OK: {result['filename']} ({lufs:.1f} LUFS)\n"
                        ok_files += 1
                    elif status == 'TOO_QUIET':
                        msg = (
                            f"TOO QUIET: {result['filename']}\n"
                            f"  Current: {lufs:.1f} LUFS | Target: {MIN_LUFS} to {MAX_LUFS} LUFS | "
                            f"Deviation: {deviation:.1f} dB quieter\n\n"
                        )
                        too_quiet_files += 1
                    else:
                        msg = (
                            f"TOO LOUD: {result['filename']}\n"
                            f"  Current: {lufs:.1f} LUFS | Target: {MIN_LUFS} to {MAX_LUFS} LUFS | "
                            f"Deviation: {deviation:.1f} dB louder\n\n"
                        )
                        too_loud_files += 1
                    print(f"  {msg.strip()}")
                    f.write(msg)
                    self.results.append(result)
                else:
                    error_msg = f"ERROR: {file_path.name} - Could not analyze file\n"
                    print(f"  {error_msg}")
                    f.write(error_msg)
                    error_files += 1

            out_of_spec = too_quiet_files + too_loud_files
            summary = "\n=== SUMMARY ===\n"
            summary += f"Total files found: {total_files}\n"
            summary += f"Files successfully analyzed: {analyzed_files}\n"
            summary += f"Files with errors: {error_files}\n"
            summary += f"Files within spec ({MAX_LUFS} to {MIN_LUFS} LUFS): {ok_files}\n"
            summary += f"Files out of spec: {out_of_spec}\n"
            summary += f"  - Too quiet (< {MIN_LUFS} LUFS): {too_quiet_files}\n"
            summary += f"  - Too loud (> {MAX_LUFS} LUFS): {too_loud_files}\n"
            if out_of_spec > 0:
                summary += "\nConsider normalizing out-of-spec files using:\n"
                summary += "ffmpeg -i input.mp4 -af loudnorm=I=-18:TP=-1.5:LRA=11 output.mp4\n"
            print(summary)
            f.write(summary)
        print(f"\nReport saved to: {self.report_file}")

    def run(self) -> int:
        if not self.check_dependencies():
            return 1
        video_files = self.find_video_files()
        if not video_files:
            print(f"No video files found in '{self.folder_path}'")
            return 0
        self.write_report(video_files)
        print("\nAnalysis complete!")
        return 0


class VideoNormalizer:
    def __init__(self, report_file: str, target_lufs: float = DEFAULT_TARGET_LUFS,
                 true_peak: float = DEFAULT_TRUE_PEAK, lra: float = DEFAULT_LRA,
                 output_dir: Optional[str] = None, dry_run: bool = False,
                 backup: bool = True, in_place: bool = False, assume_yes: bool = False):
        self.report_file = Path(report_file)
        self.target_lufs = target_lufs
        self.true_peak = true_peak
        self.lra = lra
        self.output_dir = Path(output_dir) if output_dir else None
        self.dry_run = dry_run
        self.backup = backup
        self.in_place = in_place
        self.assume_yes = assume_yes
        self.files_to_process: List[Dict] = []
        self.log_file = f"normalization_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    def parse_report(self) -> List[Dict]:
        if not self.report_file.exists():
            print(f"Error: Report file '{self.report_file}' not found")
            return []
        files_to_normalize: List[Dict] = []
        content = self.report_file.read_text()
        # TOO QUIET
        too_quiet_pattern = r'TOO QUIET: (.+?)\n\s+Current: ([-\d.]+) LUFS.*?Deviation: ([\d.]+) dB quieter'
        for match in re.finditer(too_quiet_pattern, content, re.MULTILINE):
            filename = match.group(1)
            current_lufs = float(match.group(2))
            deviation = float(match.group(3))
            files_to_normalize.append({
                'filename': filename,
                'current_lufs': current_lufs,
                'status': 'TOO_QUIET',
                'deviation': deviation,
                'adjustment_needed': self.target_lufs - current_lufs,
            })
        # TOO LOUD
        too_loud_pattern = r'TOO LOUD: (.+?)\n\s+Current: ([-\d.]+) LUFS.*?Deviation: ([\d.]+) dB louder'
        for match in re.finditer(too_loud_pattern, content, re.MULTILINE):
            filename = match.group(1)
            current_lufs = float(match.group(2))
            deviation = float(match.group(3))
            files_to_normalize.append({
                'filename': filename,
                'current_lufs': current_lufs,
                'status': 'TOO_LOUD',
                'deviation': deviation,
                'adjustment_needed': self.target_lufs - current_lufs,
            })
        # Source folder hint
        folder_match = re.search(r'Folder: (.+)', content)
        if folder_match:
            self.source_folder = Path(folder_match.group(1).strip())
        else:
            self.source_folder = self.report_file.parent
        return files_to_normalize

    def find_video_file(self, filename: str) -> Optional[Path]:
        # Try in the source folder
        candidate = getattr(self, 'source_folder', self.report_file.parent) / filename
        if candidate.exists():
            return candidate
        # Try current working directory
        alt = Path(filename)
        if alt.exists():
            return alt
        # Try next to the report
        third = self.report_file.parent / filename
        if third.exists():
            return third
        return None

    def get_output_path(self, input_path: Path) -> Path:
        if self.in_place:
            return input_path
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            # When using an explicit output directory, keep original filenames (no suffix)
            return self.output_dir / input_path.name
        return input_path.parent / f"{input_path.stem}_normalized{input_path.suffix}"

    def backup_file(self, file_path: Path) -> bool:
        backup_path = file_path.parent / f"{file_path.stem}_backup{file_path.suffix}"
        try:
            shutil.copy2(file_path, backup_path)
            print(f"    Created backup: {backup_path.name}")
            return True
        except Exception as exc:
            print(f"    ERROR: Failed to create backup: {exc}")
            return False

    def normalize_file(self, file_info: Dict) -> bool:
        input_path = self.find_video_file(file_info['filename'])
        if not input_path:
            print(f"  ERROR: Cannot find file '{file_info['filename']}'")
            return False
        output_path = self.get_output_path(input_path)
        loudnorm_filter = (
            f"loudnorm="
            f"I={self.target_lufs}:"
            f"TP={self.true_peak}:"
            f"LRA={self.lra}:"
            f"print_format=summary"
        )
        temp_path = input_path.parent / f"{input_path.stem}_temp{input_path.suffix}" if self.in_place else output_path
        cmd = ['ffmpeg', '-i', str(input_path), '-af', loudnorm_filter, '-c:v', 'copy', '-y', str(temp_path)]
        if self.dry_run:
            print(f"  [DRY RUN] Would execute: ffmpeg -i {input_path.name} -af {loudnorm_filter} -c:v copy {temp_path.name}")
            return True
        try:
            print("  Normalizing with ffmpeg...")
            print(f"    Target: {self.target_lufs} LUFS (adjustment: {file_info['adjustment_needed']:+.1f} dB)")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0:
                print(f"    ERROR: ffmpeg failed with exit code {result.returncode}")
                return False
            if self.in_place:
                if self.backup and not self.backup_file(input_path):
                    print("    ERROR: Failed to create backup, aborting in-place replacement")
                    if temp_path.exists() and temp_path != output_path:
                        temp_path.unlink()
                    return False
                try:
                    temp_path.replace(input_path)
                    print("    Replaced original file (backup created)" if self.backup else "    Replaced original file")
                except Exception as exc:
                    print(f"    ERROR: Failed to replace original file: {exc}")
                    if temp_path.exists() and temp_path != output_path:
                        temp_path.unlink()
                    return False
            else:
                print(f"    Saved to: {output_path.name}")
            final_lufs = self.extract_output_lufs(result.stderr)
            if final_lufs is not None:
                print(f"    Final loudness: {final_lufs:.1f} LUFS")
            return True
        except subprocess.TimeoutExpired:
            print("    ERROR: Normalization timed out after 30 minutes")
            if temp_path.exists() and temp_path != output_path:
                temp_path.unlink()
            return False
        except Exception as exc:
            print(f"    ERROR: Normalization failed: {exc}")
            if temp_path.exists() and temp_path != output_path:
                temp_path.unlink()
            return False

    def extract_output_lufs(self, ffmpeg_output: str) -> Optional[float]:
        match = re.search(r'Output Integrated:\s+([-\d.]+)\s+LUFS', ffmpeg_output, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    def write_log(self, files_processed: List[Dict], success_count: int, error_count: int) -> None:
        with open(self.log_file, 'w') as f:
            f.write("=== Video Loudness Normalization Log ===\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Source report: {self.report_file}\n")
            f.write(f"Target LUFS: {self.target_lufs}\n")
            f.write(f"True Peak: {self.true_peak} dB\n")
            f.write(f"LRA: {self.lra} LU\n")
            if self.output_dir:
                f.write(f"Output directory: {self.output_dir}\n")
            elif self.in_place:
                f.write("Mode: In-place replacement\n")
            else:
                f.write("Mode: Create normalized copies\n")
            f.write(f"\nFiles processed: {len(files_processed)}\n")
            f.write(f"Successful: {success_count}\n")
            f.write(f"Errors: {error_count}\n\n")
            f.write("=== Detailed Results ===\n")
            for file_info in files_processed:
                f.write(f"\nFile: {file_info['filename']}\n")
                f.write(f"  Original: {file_info['current_lufs']:.1f} LUFS\n")
                f.write(f"  Status: {file_info['status']}\n")
                f.write(f"  Adjustment: {file_info['adjustment_needed']:+.1f} dB\n")
                f.write(f"  Processed: {'Yes' if file_info.get('processed') else 'No'}\n")
                if file_info.get('error'):
                    f.write(f"  Error: {file_info['error']}\n")

    def run(self) -> int:
        if not shutil.which('ffmpeg'):
            print("Error: ffmpeg is not installed or not in PATH")
            return 1
        print(f"Reading report: {self.report_file}")
        files_to_process = self.parse_report()
        if not files_to_process:
            print("No files found that need normalization")
            return 0
        print(f"\nFound {len(files_to_process)} files to normalize:")
        for file_info in files_to_process:
            status_emoji = "🔻" if file_info['status'] == 'TOO_QUIET' else "🔺"
            print(f"  {status_emoji} {file_info['filename']} ({file_info['current_lufs']:.1f} LUFS, {file_info['adjustment_needed']:+.1f} dB adjustment needed)")
        if self.dry_run:
            print("\n[DRY RUN MODE - No files will be modified]")
        if not self.dry_run:
            print("\nNormalization settings:")
            print(f"  Target: {self.target_lufs} LUFS")
            print(f"  True Peak: {self.true_peak} dB")
            print(f"  LRA: {self.lra} LU")
            if self.in_place:
                print(f"  Mode: In-place replacement {'(with backup)' if self.backup else '(NO BACKUP)'}")
            elif self.output_dir:
                print(f"  Output: {self.output_dir}/")
            else:
                print("  Output: Same directory with '_normalized' suffix")
            if not self.assume_yes:
                response = input("\nProceed with normalization? (y/N): ")
                if response.lower() != 'y':
                    print("Normalization cancelled")
                    return 0
        print("\nProcessing files...")
        success_count = 0
        error_count = 0
        for i, file_info in enumerate(files_to_process, 1):
            print(f"\n[{i}/{len(files_to_process)}] Processing: {file_info['filename']}")
            if self.normalize_file(file_info):
                success_count += 1
                file_info['processed'] = True
            else:
                error_count += 1
                file_info['processed'] = False
                file_info['error'] = "Failed to normalize"
        self.write_log(files_to_process, success_count, error_count)
        print("\n=== SUMMARY ===")
        print(f"Files processed: {len(files_to_process)}")
        print(f"Successful: {success_count}")
        print(f"Errors: {error_count}")
        print(f"\nLog saved to: {self.log_file}")
        return 0 if error_count == 0 else 1

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
    """Run in-memory check and normalize out-of-spec files without writing a report.

    Prints a concise stdout report before normalizing. No prompt by default;
    use --confirm to require a confirmation prompt.
    """
    checker = VideoLoudnessChecker(args.folder)

    # Discover files without writing a report
    video_files = checker.find_video_files()
    if not video_files:
        print(f"No video files found in '{args.folder}'.")
        return 0

    print(f"Found {len(video_files)} video files to analyze.\n")

    # Analyze and collect out-of-spec entries
    analysis_results = []
    for idx, file_path in enumerate(video_files, 1):
        print(f"Analyzing [{idx}/{len(video_files)}]: {file_path.name}")
        result = checker.analyze_loudness(file_path)
        if result:
            analysis_results.append(result)

    # Print concise report
    print("\n=== ANALYSIS REPORT ===")
    ok_count = 0
    too_quiet_count = 0
    too_loud_count = 0
    error_count = 0 if len(analysis_results) == len(video_files) else (len(video_files) - len(analysis_results))
    for res in analysis_results:
        status, deviation = res['status']
        lufs = res['lufs']
        if status == 'OK':
            ok_count += 1
            print(f"OK        {res['filename']}  ({lufs:.1f} LUFS)")
        elif status == 'TOO_QUIET':
            too_quiet_count += 1
            print(f"TOO QUIET {res['filename']}  ({lufs:.1f} LUFS, {deviation:.1f} dB quieter)")
        else:
            too_loud_count += 1
            print(f"TOO LOUD  {res['filename']}  ({lufs:.1f} LUFS, {deviation:.1f} dB louder)")

    out_of_spec_results = [r for r in analysis_results if r.get('status', ('OK', 0.0))[0] != 'OK']
    if not out_of_spec_results:
        print("\n=== SUMMARY ===")
        print(f"Files analyzed: {len(analysis_results)}")
        print(f"Within spec: {ok_count}")
        print(f"Too quiet: {too_quiet_count}")
        print(f"Too loud: {too_loud_count}")
        print(f"Errors: {error_count}")
        print("\nAll files are within spec. Nothing to normalize.")
        return 0

    # Prepare normalizer and perform normalization per file without a report file
    target_lufs = _resolve_target_lufs(args)
    normalizer = VideoNormalizer(
        report_file="AUTO_MODE",  # placeholder; we won't parse it
        target_lufs=target_lufs,
        true_peak=args.true_peak,
        lra=args.lra,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        in_place=args.in_place,
        assume_yes=args.yes,
    )
    # Ensure file lookup works
    try:
        from pathlib import Path as _P
        normalizer.source_folder = _P(args.folder)
    except Exception:
        pass

    # Optional confirmation; off by default unless --confirm
    if getattr(args, 'confirm', False) and not args.dry_run and not args.yes:
        print("\nNormalization settings:")
        print(f"  Target: {target_lufs} LUFS")
        print(f"  True Peak: {args.true_peak} dB")
        print(f"  LRA: {args.lra} LU")
        if args.in_place:
            print(f"  Mode: In-place replacement {'(with backup)' if not args.no_backup else '(NO BACKUP)'}")
        elif args.output_dir:
            print(f"  Output: {args.output_dir}/ (original filenames)")
        else:
            print("  Output: Same directory with '_normalized' suffix")
        resp = input("\nProceed with normalization? (y/N): ")
        if resp.lower() != 'y':
            print("Normalization cancelled")
            return 0

    print("\nProcessing out-of-spec files...")
    success_count = 0
    error_count = 0

    for i, res in enumerate(out_of_spec_results, 1):
        filename = res['filename']
        current_lufs = res['lufs']
        status, deviation = res['status']
        file_info = {
            'filename': filename,
            'current_lufs': current_lufs,
            'status': 'TOO_QUIET' if status == 'TOO_QUIET' else 'TOO_LOUD',
            'deviation': deviation,
            'adjustment_needed': target_lufs - current_lufs,
        }
        print(f"\n[{i}/{len(out_of_spec_results)}] Processing: {filename}")
        if normalizer.normalize_file(file_info):
            success_count += 1
        else:
            error_count += 1

    print("\n=== SUMMARY ===")
    print(f"Files analyzed: {len(analysis_results)}")
    print(f"Within spec: {ok_count}")
    print(f"Too quiet: {too_quiet_count}")
    print(f"Too loud: {too_loud_count}")
    print(f"Out-of-spec processed: {success_count}")
    print(f"Errors: {error_count}")
    return 0 if error_count == 0 else 1


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
    p_auto = subparsers.add_parser("auto", help="Run check then normalize out-of-spec files (default if no subcommand)")
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
    p_auto.add_argument("--confirm", action="store_true", help="Ask for confirmation before normalizing")
    p_auto.set_defaults(func=cmd_auto)

    return parser


def main() -> int:
    parser = build_parser()
    argv = sys.argv[1:]
    # Default to 'auto' if no subcommand is provided
    if len(argv) == 0 or argv[0] not in {"check", "normalize", "auto"}:
        argv = ["auto"] + argv
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())


