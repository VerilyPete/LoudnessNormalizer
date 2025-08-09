#!/usr/bin/env python3
"""
Video Loudness Checker
Analyzes all video files in a folder and reports loudness levels
Usage: python loudness_checker.py [folder_path]
"""

import os
import sys
import subprocess
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import shutil

# Video file extensions to check
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.m4v', '.webm', '.flv', '.wmv', '.mpg', '.mpeg'}

# Define target range (podcast/dialogue standard)
MIN_LUFS = -20
MAX_LUFS = -16

class VideoLoudnessChecker:
    def __init__(self, folder_path: str = "."):
        self.folder_path = Path(folder_path)
        self.report_file = f"loudness_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.results = []
        
    def check_dependencies(self) -> bool:
        """Check if ffmpeg is available"""
        if not shutil.which('ffmpeg'):
            print("Error: ffmpeg is not installed or not in PATH")
            return False
        return True
    
    def find_video_files(self) -> List[Path]:
        """Find all video files in the specified folder"""
        video_files = []
        
        if not self.folder_path.exists():
            print(f"Error: Folder '{self.folder_path}' does not exist")
            return video_files
        
        if not self.folder_path.is_dir():
            print(f"Error: '{self.folder_path}' is not a directory")
            return video_files
        
        # Find all video files (non-recursive, like the bash script)
        for file in self.folder_path.iterdir():
            if file.is_file() and file.suffix.lower() in VIDEO_EXTENSIONS:
                video_files.append(file)
        
        video_files.sort()
        return video_files
    
    def analyze_loudness(self, file_path: Path) -> Optional[Dict]:
        """Analyze loudness of a single video file using ffmpeg"""
        try:
            # Run ffmpeg with loudnorm filter
            cmd = [
                'ffmpeg',
                '-i', str(file_path),
                '-af', 'loudnorm=print_format=summary',
                '-f', 'null',
                '-'
            ]
            
            print(f"  Running ffmpeg analysis...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for large files
            )
            
            # Combine stdout and stderr (ffmpeg outputs to stderr)
            output = result.stderr + result.stdout
            
            # Parse the loudnorm output
            lufs_value = self.extract_lufs(output)
            
            if lufs_value is not None:
                return {
                    'filename': file_path.name,
                    'path': str(file_path),
                    'lufs': lufs_value,
                    'status': self.check_compliance(lufs_value)
                }
            else:
                print(f"  WARNING: Could not extract LUFS value from ffmpeg output")
                # Debug output
                if "lufs" in output.lower():
                    print("  Debug: Found LUFS in output but couldn't parse it")
                    lufs_lines = [line for line in output.split('\n') if 'lufs' in line.lower()]
                    for line in lufs_lines[:3]:
                        print(f"    {line.strip()}")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"  ERROR: Analysis timed out for {file_path.name}")
            return None
        except Exception as e:
            print(f"  ERROR: Failed to analyze {file_path.name}: {e}")
            return None
    
    def extract_lufs(self, ffmpeg_output: str) -> Optional[float]:
        """Extract LUFS value from ffmpeg output"""
        # Look for patterns like "Input Integrated:    -24.2 LUFS"
        patterns = [
            r'Input Integrated:\s+([-\d.]+)\s+LUFS',
            r'I:\s+([-\d.]+)\s+LUFS',  # Sometimes it's shortened
            r'input.*integrated.*?([-\d.]+)\s*LUFS',  # Case insensitive backup
        ]
        
        for pattern in patterns:
            match = re.search(pattern, ffmpeg_output, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        # Last resort: find any line with a negative number followed by LUFS
        last_resort = re.search(r'([-\d.]+)\s*LUFS', ffmpeg_output, re.IGNORECASE)
        if last_resort:
            try:
                return float(last_resort.group(1))
            except ValueError:
                pass
        
        return None
    
    def check_compliance(self, lufs: float) -> Tuple[str, float]:
        """Check if LUFS value is within target range"""
        if lufs < MIN_LUFS:
            deviation = MIN_LUFS - lufs
            return ('TOO_QUIET', deviation)
        elif lufs > MAX_LUFS:
            deviation = lufs - MAX_LUFS
            return ('TOO_LOUD', deviation)
        else:
            return ('OK', 0.0)
    
    def write_report(self, video_files: List[Path]):
        """Generate and write the analysis report"""
        with open(self.report_file, 'w') as f:
            # Header
            f.write("=== Video Loudness Analysis Report ===\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Folder: {self.folder_path.absolute()}\n")
            f.write(f"Target Range: {MIN_LUFS} to {MAX_LUFS} LUFS (podcast/dialogue)\n\n")
            
            # Process each file
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
                
                # Check if file is readable
                if not file_path.exists() or not os.access(file_path, os.R_OK):
                    error_msg = f"ERROR: {file_path.name} - File not readable\n"
                    print(f"  {error_msg}")
                    f.write(error_msg)
                    error_files += 1
                    continue
                
                # Analyze the file
                result = self.analyze_loudness(file_path)
                
                if result:
                    analyzed_files += 1
                    status, deviation = result['status']
                    lufs = result['lufs']
                    
                    if status == 'OK':
                        msg = f"OK: {result['filename']} ({lufs:.1f} LUFS)\n"
                        ok_files += 1
                    elif status == 'TOO_QUIET':
                        msg = f"TOO QUIET: {result['filename']}\n"
                        msg += f"  Current: {lufs:.1f} LUFS | Target: {MIN_LUFS} to {MAX_LUFS} LUFS | "
                        msg += f"Deviation: {deviation:.1f} dB quieter\n\n"
                        too_quiet_files += 1
                    else:  # TOO_LOUD
                        msg = f"TOO LOUD: {result['filename']}\n"
                        msg += f"  Current: {lufs:.1f} LUFS | Target: {MIN_LUFS} to {MAX_LUFS} LUFS | "
                        msg += f"Deviation: {deviation:.1f} dB louder\n\n"
                        too_loud_files += 1
                    
                    print(f"  {msg.strip()}")
                    f.write(msg)
                    self.results.append(result)
                else:
                    error_msg = f"ERROR: {file_path.name} - Could not analyze file\n"
                    print(f"  {error_msg}")
                    f.write(error_msg)
                    error_files += 1
            
            # Summary
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
    
    def run(self):
        """Main execution method"""
        # Check dependencies
        if not self.check_dependencies():
            return 1
        
        # Find video files
        video_files = self.find_video_files()
        
        if not video_files:
            print(f"No video files found in '{self.folder_path}'")
            return 0
        
        # Generate report
        self.write_report(video_files)
        
        print("\nAnalysis complete!")
        return 0


def main():
    """Main entry point"""
    # Get folder path from command line or use current directory
    folder_path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    # Create and run checker
    checker = VideoLoudnessChecker(folder_path)
    return checker.run()


if __name__ == "__main__":
    sys.exit(main())