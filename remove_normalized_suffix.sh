#!/bin/bash

# Script to remove "_normalized" suffix from filenames while retaining extensions
# Usage: ./remove_normalized.sh [directory]
# If no directory specified, uses current directory

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get directory from argument or use current directory
DIR="${1:-.}"

# Check if directory exists
if [ ! -d "$DIR" ]; then
    echo -e "${RED}Error: Directory '$DIR' does not exist${NC}"
    exit 1
fi

# Change to the specified directory
cd "$DIR" || exit 1

echo -e "${GREEN}=== Remove '_normalized' Suffix from Filenames ===${NC}"
echo "Directory: $(pwd)"
echo ""

# Find all files with _normalized in the name
files_found=0
files_renamed=0
files_skipped=0
errors=0

# Create array to store files to be renamed
declare -a files_to_rename

# Find files with _normalized pattern
while IFS= read -r -d '' file; do
    files_found=$((files_found + 1))
    files_to_rename+=("$file")
done < <(find . -maxdepth 1 -type f -name "*_normalized.*" -print0)

if [ $files_found -eq 0 ]; then
    echo "No files with '_normalized' suffix found in $DIR"
    exit 0
fi

echo "Found $files_found file(s) with '_normalized' suffix:"
echo ""

# Display files that will be renamed
for file in "${files_to_rename[@]}"; do
    # Extract filename without path
    basename_file=$(basename "$file")
    
    # Remove _normalized suffix while keeping extension
    # This handles files like: video_normalized.mp4 -> video.mp4
    new_name=$(echo "$basename_file" | sed 's/_normalized\(\.[^.]*\)$/\1/')
    
    # If the new name is the same as old name, skip (shouldn't happen but just in case)
    if [ "$basename_file" = "$new_name" ]; then
        echo -e "${YELLOW}⚠ Skip: $basename_file (no _normalized suffix found)${NC}"
        files_skipped=$((files_skipped + 1))
        continue
    fi
    
    echo "  • $basename_file → $new_name"
done

echo ""
read -p "Do you want to rename these files? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Operation cancelled${NC}"
    exit 0
fi

echo ""
echo "Renaming files..."
echo ""

# Perform the actual renaming
for file in "${files_to_rename[@]}"; do
    # Extract filename without path
    basename_file=$(basename "$file")
    dir_path=$(dirname "$file")
    
    # Remove _normalized suffix while keeping extension
    new_name=$(echo "$basename_file" | sed 's/_normalized\(\.[^.]*\)$/\1/')
    
    # Full paths
    old_path="$file"
    new_path="$dir_path/$new_name"
    
    # Skip if names are the same
    if [ "$basename_file" = "$new_name" ]; then
        continue
    fi
    
    # Check if target file already exists
    if [ -e "$new_path" ]; then
        echo -e "${YELLOW}⚠ Warning: $new_name already exists${NC}"
        read -p "  Overwrite? (y/N): " -n 1 -r
        echo ""
        
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}  Skipped: $basename_file${NC}"
            files_skipped=$((files_skipped + 1))
            continue
        fi
    fi
    
    # Perform the rename
    if mv "$old_path" "$new_path" 2>/dev/null; then
        echo -e "${GREEN}✓ Renamed: $basename_file → $new_name${NC}"
        files_renamed=$((files_renamed + 1))
    else
        echo -e "${RED}✗ Error: Failed to rename $basename_file${NC}"
        errors=$((errors + 1))
    fi
done

echo ""
echo -e "${GREEN}=== Summary ===${NC}"
echo "Files found: $files_found"
echo "Files renamed: $files_renamed"
echo "Files skipped: $files_skipped"
echo "Errors: $errors"

if [ $files_renamed -gt 0 ]; then
    echo -e "${GREEN}Successfully removed '_normalized' suffix from $files_renamed file(s)${NC}"
fi

if [ $errors -gt 0 ]; then
    echo -e "${RED}Failed to rename $errors file(s)${NC}"
    exit 1
fi