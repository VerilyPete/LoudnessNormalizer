#!/usr/bin/env python3
"""
Video Loudness Normalizer
Reads a loudness report and normalizes out-of-spec video files to target LUFS
Usage: python loudness_normalizer.py [report_file] [options]
"""

import os
import sys
import re
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
from datetime import datetime
import json

# Target loudness for normalization (middle of podcast range)
DEFAULT_TARGET_LUFS = -18.0
DEFAULT_TRUE_PEAK = -1.5
DEFAULT_LRA = 11.0

class VideoNormalizer:
    def __init__(self, report_file: str, target_lufs: float = DEFAULT_TARGET_LUFS,
                 true_peak: float = DEFAULT_TRUE_PEAK, lra: float = DEFAULT_LRA,
                 output_dir: Optional[str] = None, dry_run: bool = False,
                 backup: bool = True, in_place: bool = False):
        self.report_file = Path(report_file)
        self.target_lufs = target_lufs
        self.true_peak = true_peak
        self.lra = lra
        self.output_dir = Path(output_dir) if output_dir else None
        self.dry_run = dry_run
        self.backup = backup
        self.in_place = in_place
        self.files_to_process = []
        self.log_file = f"normalization_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
    def parse_report(self) -> List[Dict]:
        """Parse the loudness report to find files that need normalization"""
        if not self.report_file.exists():
            print(f"Error: Report file '{self.report_file}' not found")
            return []
        
        files_to_normalize = []
        
        with open(self.report_file, 'r') as f:
            content = f.read()
        
        # Parse TOO QUIET entries
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
                'adjustment_needed': self.target_lufs - current_lufs
            })
        
        # Parse TOO LOUD entries
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
                'adjustment_needed': self.target_lufs - current_lufs
            })
        
        # Try to find the source folder from the report
        folder_match = re.search(r'Folder: (.+)', content)
        if folder_match:
            self.source_folder = Path(folder_match.group(1).strip())
        else:
            # Assume report is in the same folder as videos
            self.source_folder = self.report_file.parent
        
        return files_to_normalize
    
    def find_video_file(self, filename: str) -> Optional[Path]:
        """Find the actual video file path"""
        # First try in the source folder
        file_path = self.source_folder / filename
        if file_path.exists():
            return file_path
        
        # Try in current directory
        file_path = Path(filename)
        if file_path.exists():
            return file_path
        
        # Try in report file's directory
        file_path = self.report_file.parent / filename
        if file_path.exists():
            return file_path
        
        return None
    
    def get_output_path(self, input_path: Path) -> Path:
        """Determine the output path for normalized file"""
        if self.in_place:
            return input_path
        elif self.output_dir:
            # Create output directory if it doesn't exist
            self.output_dir.mkdir(parents=True, exist_ok=True)
            # Add _normalized suffix before extension
            stem = input_path.stem
            suffix = input_path.suffix
            return self.output_dir / f"{stem}_normalized{suffix}"
        else:
            # Save in same directory with _normalized suffix
            stem = input_path.stem
            suffix = input_path.suffix
            return input_path.parent / f"{stem}_normalized{suffix}"
    
    def backup_file(self, file_path: Path) -> bool:
        """Create a backup of the original file"""
        backup_path = file_path.parent / f"{file_path.stem}_backup{file_path.suffix}"
        try:
            shutil.copy2(file_path, backup_path)
            print(f"    Created backup: {backup_path.name}")
            return True
        except Exception as e:
            print(f"    ERROR: Failed to create backup: {e}")
            return False
    
    def normalize_file(self, file_info: Dict) -> bool:
        """Normalize a single video file using ffmpeg"""
        # Find the actual file
        input_path = self.find_video_file(file_info['filename'])
        if not input_path:
            print(f"  ERROR: Cannot find file '{file_info['filename']}'")
            return False
        
        output_path = self.get_output_path(input_path)
        
        # Build ffmpeg command
        loudnorm_filter = (
            f"loudnorm="
            f"I={self.target_lufs}:"
            f"TP={self.true_peak}:"
            f"LRA={self.lra}:"
            f"print_format=summary"
        )
        
        # Use a temporary file if doing in-place replacement
        if self.in_place:
            temp_path = input_path.parent / f"{input_path.stem}_temp{input_path.suffix}"
        else:
            temp_path = output_path
        
        cmd = [
            'ffmpeg',
            '-i', str(input_path),
            '-af', loudnorm_filter,
            '-c:v', 'copy',  # Copy video stream without re-encoding
            '-y',  # Overwrite output file if it exists
            str(temp_path)
        ]
        
        if self.dry_run:
            print(f"  [DRY RUN] Would execute: ffmpeg -i {input_path.name} -af {loudnorm_filter} -c:v copy {temp_path.name}")
            return True
        
        try:
            print(f"  Normalizing with ffmpeg...")
            print(f"    Target: {self.target_lufs} LUFS (adjustment: {file_info['adjustment_needed']:+.1f} dB)")
            
            # Run ffmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout for large files
            )
            
            if result.returncode != 0:
                print(f"    ERROR: ffmpeg failed with exit code {result.returncode}")
                if "already exists" in result.stderr:
                    print("    Output file already exists. Use -y flag to overwrite.")
                return False
            
            # If in-place, replace original with normalized version
            if self.in_place:
                # Create backup first if requested
                if self.backup and not self.backup_file(input_path):
                    print("    ERROR: Failed to create backup, aborting in-place replacement")
                    temp_path.unlink()  # Clean up temp file
                    return False
                
                # Replace original with normalized version
                try:
                    temp_path.replace(input_path)
                    print(f"    Replaced original file (backup created)" if self.backup else "    Replaced original file")
                except Exception as e:
                    print(f"    ERROR: Failed to replace original file: {e}")
                    temp_path.unlink()  # Clean up temp file
                    return False
            else:
                print(f"    Saved to: {output_path.name}")
            
            # Extract the final loudness from ffmpeg output
            final_lufs = self.extract_output_lufs(result.stderr)
            if final_lufs:
                print(f"    Final loudness: {final_lufs:.1f} LUFS")
            
            return True
            
        except subprocess.TimeoutExpired:
            print(f"    ERROR: Normalization timed out after 30 minutes")
            # Clean up partial file
            if temp_path.exists() and temp_path != output_path:
                temp_path.unlink()
            return False
        except Exception as e:
            print(f"    ERROR: Normalization failed: {e}")
            # Clean up partial file
            if temp_path.exists() and temp_path != output_path:
                temp_path.unlink()
            return False
    
    def extract_output_lufs(self, ffmpeg_output: str) -> Optional[float]:
        """Extract the output LUFS value from ffmpeg normalization output"""
        # Look for "Output Integrated" in the loudnorm summary
        match = re.search(r'Output Integrated:\s+([-\d.]+)\s+LUFS', ffmpeg_output, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None
    
    def write_log(self, files_processed: List[Dict], success_count: int, error_count: int):
        """Write a detailed log of the normalization process"""
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
    
    def run(self):
        """Main execution method"""
        # Check for ffmpeg
        if not shutil.which('ffmpeg'):
            print("Error: ffmpeg is not installed or not in PATH")
            return 1
        
        # Parse the report
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
        
        # Process confirmation
        if not self.dry_run:
            print(f"\nNormalization settings:")
            print(f"  Target: {self.target_lufs} LUFS")
            print(f"  True Peak: {self.true_peak} dB")
            print(f"  LRA: {self.lra} LU")
            
            if self.in_place:
                print(f"  Mode: In-place replacement {'(with backup)' if self.backup else '(NO BACKUP)'}")
            elif self.output_dir:
                print(f"  Output: {self.output_dir}/")
            else:
                print(f"  Output: Same directory with '_normalized' suffix")
            
            response = input("\nProceed with normalization? (y/N): ")
            if response.lower() != 'y':
                print("Normalization cancelled")
                return 0
        
        # Process each file
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
        
        # Write log
        self.write_log(files_to_process, success_count, error_count)
        
        # Summary
        print(f"\n=== SUMMARY ===")
        print(f"Files processed: {len(files_to_process)}")
        print(f"Successful: {success_count}")
        print(f"Errors: {error_count}")
        print(f"\nLog saved to: {self.log_file}")
        
        return 0 if error_count == 0 else 1


def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        description='Normalize video files based on loudness analysis report',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with report file
  python loudness_normalizer.py loudness_report_20240101_120000.txt
  
  # Specify custom target LUFS
  python loudness_normalizer.py report.txt --target -16
  
  # Save normalized files to specific directory
  python loudness_normalizer.py report.txt --output-dir ./normalized
  
  # Replace files in-place (with backup)
  python loudness_normalizer.py report.txt --in-place
  
  # Dry run to see what would be done
  python loudness_normalizer.py report.txt --dry-run
        """
    )
    
    parser.add_argument('report', help='Path to loudness analysis report file')
    parser.add_argument('--target', '-t', type=float, default=DEFAULT_TARGET_LUFS,
                        help=f'Target LUFS for normalization (default: {DEFAULT_TARGET_LUFS})')
    parser.add_argument('--true-peak', '-tp', type=float, default=DEFAULT_TRUE_PEAK,
                        help=f'True peak limit in dB (default: {DEFAULT_TRUE_PEAK})')
    parser.add_argument('--lra', type=float, default=DEFAULT_LRA,
                        help=f'Loudness range in LU (default: {DEFAULT_LRA})')
    parser.add_argument('--output-dir', '-o', type=str,
                        help='Directory to save normalized files (default: same as source)')
    parser.add_argument('--in-place', '-i', action='store_true',
                        help='Replace original files (backup created by default)')
    parser.add_argument('--no-backup', action='store_true',
                        help='Skip backup when using --in-place (use with caution!)')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Show what would be done without actually processing files')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.in_place and args.output_dir:
        print("Error: Cannot use --in-place and --output-dir together")
        return 1
    
    # Create normalizer instance
    normalizer = VideoNormalizer(
        report_file=args.report,
        target_lufs=args.target,
        true_peak=args.true_peak,
        lra=args.lra,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        in_place=args.in_place
    )
    
    return normalizer.run()


if __name__ == "__main__":
    sys.exit(main())