# Disclaimer
This project was made a while back, some code may be a bit unprofessional, but that is how it usually goes with old projects.

# FileFinder

Find large files fast with a friendly CLI.

## Quick start

1. Install deps (Windows PowerShell):

```
pip install -r requirements.txt
```

2. Run in quick mode (prompts only the essentials):

```
python .\FileFinder.py
```

3. Advanced (full control):

```
python .\FileFinder.py --mode advanced
```

## Examples

- Scan current folder, show top 20 files over 200MB in a table:
```
python .\FileFinder.py --size_threshold 200 --limit 20
```

- Save JSON report and delete listed files after confirmation:
```
python .\FileFinder.py --format json --output report.json --delete
```

- Include only videos, exclude logs, use 8 workers:
```
python .\FileFinder.py --include .mp4 .mkv --exclude .log --workers 8
```

## Config

Defaults are in `config.ini`. Leave `workers` empty to auto-select.
To many workers can cause stress on the CPU, so leave as is if you don't know what you are doing.
