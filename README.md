# Loudness Normalizer

A small toolkit to analyze and normalize video loudness using ffmpeg.

It provides:
- `loudness.py` unified CLI with subcommands:
  - `check`: Analyze a folder of videos and write a loudness report
  - `normalize`: Normalize files using a prior report
  - `auto`: Run `check` then normalize out-of-spec files in one go
- Backward-compatible scripts:
  - `loudness_checker.py`
  - `loudness_normalizer.py`
- Utility script:
  - `remove_normalized_suffix.sh` to strip `_normalized` from filenames

## Requirements
- ffmpeg installed and available on PATH
- Python 3.8+
- macOS, Linux, or Windows (WSL recommended on Windows)

Verify ffmpeg:
```
ffmpeg -version
```

## Quick Start
- Analyze a folder and produce a report:
```
python loudness.py check ./videos
```
- Normalize from an existing report (non-interactive):
```
python loudness.py normalize loudness_report_20240101_120000.txt --yes
```
- One-shot: check then normalize out-of-spec files:
```
python loudness.py auto ./videos --target -18 --yes
```

## Unified CLI
The unified entrypoint is `loudness.py`.

### Check
Analyze loudness for all videos in a folder (non-recursive) and write a timestamped report.
```
python loudness.py check /path/to/folder
```

### Normalize
Normalize files based on a previously generated report.
```
# Basic usage - normalize files from a report
python loudness.py normalize loudness_report_20240101_120000.txt

# Dry run - see what would be done without processing
python loudness.py normalize report.txt --dry-run

# Custom target for louder output (e.g., for music videos)
python loudness.py normalize report.txt --target -14

# Presets for known standards
# Broadcast (-24 LUFS)
python loudness.py normalize report.txt --preset broadcast
# Gaming (-16 LUFS)
python loudness.py normalize report.txt --preset gaming
# Podcast (-16 LUFS)
python loudness.py normalize report.txt --preset podcast

# Save all normalized files to a specific directory
python loudness.py normalize report.txt --output-dir ./normalized_videos

# Replace files in-place (creates backups first)
python loudness.py normalize report.txt --in-place

# In-place without backup (dangerous but saves space)
python loudness.py normalize report.txt --in-place --no-backup

# Custom settings for broadcast standard
python loudness.py normalize report.txt --target -23 --true-peak -2

# Non-interactive (skip confirmation)
python loudness.py normalize report.txt --yes
```

### Auto
Runs `check` then normalizes only out-of-spec files using the generated report.
```
python loudness.py auto ./videos --target -18 --yes
```
All `normalize` options (e.g., `--output-dir`, `--in-place`, `--no-backup`, `--dry-run`) also work with `auto`.

Preset examples with `auto`:
```
# Broadcast (-24 LUFS)
python loudness.py auto ./videos --preset broadcast --yes
# Gaming (-16 LUFS)
python loudness.py auto ./videos --preset gaming --yes
# Podcast (-16 LUFS)
python loudness.py auto ./videos --preset podcast --yes
```

## Backward-Compatible Scripts
You can still use the original scripts directly if you prefer.

### Analyzer
```
python loudness_checker.py /path/to/folder
```
Generates a report like `loudness_report_YYYYMMDD_HHMMSS.txt`. Default target range: -20 to -16 LUFS (dialog/podcast).

### Normalizer
```
# Basic usage - normalize files from a report
python loudness_normalizer.py loudness_report_20240101_120000.txt

# Dry run - see what would be done without processing
python loudness_normalizer.py report.txt --dry-run

# Custom target for louder output (e.g., for music videos)
python loudness_normalizer.py report.txt --target -14

# Presets for known standards
# Broadcast (-24 LUFS)
python loudness_normalizer.py report.txt --preset broadcast
# Gaming (-16 LUFS)
python loudness_normalizer.py report.txt --preset gaming
# Podcast (-16 LUFS)
python loudness_normalizer.py report.txt --preset podcast

# Save all normalized files to a specific directory
python loudness_normalizer.py report.txt --output-dir ./normalized_videos

# Replace files in-place (creates backups first)
python loudness_normalizer.py report.txt --in-place

# In-place without backup (dangerous but saves space)
python loudness_normalizer.py report.txt --in-place --no-backup

# Custom settings for broadcast standard
python loudness_normalizer.py report.txt --target -23 --true-peak -2

# Non-interactive (skip confirmation)
python loudness_normalizer.py report.txt --yes
```

## Notes and Tips
- `--in-place` will replace originals; by default a backup copy is created (e.g., `video_backup.mp4`). Use `--no-backup` with caution.
- `--dry-run` prints intended ffmpeg commands and skips processing.
- The analyzer is non-recursive by design; place all target videos in one folder or run per folder.
- ffmpeg timeouts are applied to protect against hanging on very large/corrupt files.

## Utility: Remove `_normalized` Suffix
After creating normalized copies (e.g., `clip_normalized.mp4`), you can strip the suffix:
```
./remove_normalized_suffix.sh /path/to/folder
```
- Shows a preview and asks for confirmation.
- Handles name collisions with a prompt.

## Troubleshooting
- ffmpeg not found: install via your package manager (brew, apt) or from ffmpeg.org and ensure it’s on PATH.
- No videos found: supported extensions include `.mp4, .mkv, .avi, .mov, .m4v, .webm, .flv, .wmv, .mpg, .mpeg`.
- Parsing errors: the normalizer expects a report generated by this toolchain; re-run `check` if needed.

## License
MIT
