import os
import sys
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from tabulate import tabulate  # Install with 'pip install tabulate'
import json
import csv
import configparser

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def normalize_ext_list(exts):
    """Normalize list of extensions: lowercase and ensure leading dot."""
    if not exts:
        return None
    norm = []
    for ext in exts:
        if not ext:
            continue
        e = ext.strip().lower()
        if not e:
            continue
        if not e.startswith('.'):
            e = '.' + e
        norm.append(e)
    return norm or None


def format_size(num_bytes):
    """Return human-readable size string."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024


def ensure_parent_dir(path):
    """Ensure parent directory exists for a file path."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def process_file(file_path, size_threshold):
    """Check if a file exceeds the specified size threshold.

    Args:
        file_path (str): Path to the file.
        size_threshold (int): Size threshold in bytes.

    Returns:
        tuple: (file_path, file_size) if the file exceeds the threshold, else None.
    """
    try:
        file_size = os.path.getsize(file_path)
        if file_size > size_threshold:
            return (file_path, file_size)
    except OSError as e:
        logging.error(f"Error accessing file '{file_path}': {e}")
    return None


def find_large_files(directories, size_threshold, include_types=None, exclude_types=None, workers=None):
    """Find files larger than the given size threshold in specified directories."""
    large_files = []
    file_paths = []

    include_types = normalize_ext_list(include_types)
    exclude_types = normalize_ext_list(exclude_types)

    for directory in directories:
        if not os.path.isdir(directory):
            logging.warning(f"Skipping non-existent path: {directory}")
            continue
        for root, _, files in os.walk(directory):
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if include_types and ext not in include_types:
                    continue
                if exclude_types and ext in exclude_types:
                    continue
                file_paths.append(os.path.join(root, name))

    total_files = len(file_paths)
    logging.info(f"Total candidate files to scan: {total_files}")
    if total_files == 0:
        return []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for result in tqdm(
            executor.map(lambda fp: process_file(fp, size_threshold), file_paths),
            total=total_files,
            desc="Scanning files",
            unit="file",
            leave=False,
        ):
            if result:
                large_files.append(result)

    large_files.sort(key=lambda x: x[1], reverse=True)
    return large_files


def display_large_files(large_files, output_file=None, limit=None, output_format="table"):
    """Display the large files found with their sizes in a formatted table or other formats.

    Returns the list used for output (after applying limit).
    """
    if not large_files:
        logging.info("No files larger than the specified threshold were found.")
        return []

    used_files = large_files[:limit] if limit else list(large_files)

    if output_format == "json":
        output_data = [
            {"file_path": fp, "size_bytes": fs, "size_human": format_size(fs)}
            for fp, fs in used_files
        ]
        print(json.dumps(output_data, indent=2))
    elif output_format == "csv":
        # simple CSV display
        print("file_path,size_bytes,size_human")
        for fp, fs in used_files:
            print(f"{fp},{fs},{format_size(fs)}")
    else:
        table_data = [(fp, format_size(fs)) for fp, fs in used_files]
        print("\nLarge files found:")
        print(tabulate(table_data, headers=["File Path", "Size"], tablefmt="grid"))

    if output_file:
        ensure_parent_dir(output_file)
        fmt = (output_format or "table").lower()
        try:
            if fmt == "json":
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(
                        [
                            {
                                "file_path": fp,
                                "size_bytes": fs,
                                "size_human": format_size(fs),
                            }
                            for fp, fs in used_files
                        ],
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )
            elif fmt == "csv":
                import csv as _csv

                with open(output_file, "w", newline="", encoding="utf-8") as f:
                    writer = _csv.writer(f)
                    writer.writerow(["file_path", "size_bytes", "size_human"])
                    for fp, fs in used_files:
                        writer.writerow([fp, fs, format_size(fs)])
            else:
                table_data = [(fp, format_size(fs)) for fp, fs in used_files]
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(tabulate(table_data, headers=["File Path", "Size"], tablefmt="grid"))
            logging.info(f"Results saved to {output_file}")
        except OSError as e:
            logging.error(f"Failed to save results to '{output_file}': {e}")

    total_size_mb = sum(sz for _, sz in used_files) / (1024 * 1024)
    logging.info(f"Summary: {len(used_files)} files listed, Total size: {total_size_mb:.2f} MB")
    return used_files


def main():
    config = configparser.ConfigParser()
    config.read("config.ini")

    parser = argparse.ArgumentParser(description="Find large files in a directory.")
    parser.add_argument(
        "--directory",
        help="Directories to scan (comma-separated)",
        default=config.get("DEFAULT", "directory", fallback=os.getcwd()),
    )
    parser.add_argument(
        "--size_threshold",
        type=int,
        help="Minimum file size to find (in MB)",
        default=config.getint("DEFAULT", "size_threshold", fallback=100),
    )
    parser.add_argument(
        "--output",
        help="Output file path to save results",
        default=config.get("DEFAULT", "output", fallback=None),
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        help="File types to exclude (e.g., .txt .log)",
        default=config.get("DEFAULT", "exclude", fallback=None),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of results displayed",
        default=config.getint("DEFAULT", "limit", fallback=None),
    )
    parser.add_argument(
        "--include",
        nargs="+",
        help="File types to include (e.g., .mp4 .pdf)",
        default=config.get("DEFAULT", "include", fallback=None),
    )
    parser.add_argument("--delete", action="store_true", help="Delete the displayed files")
    parser.add_argument("-y", "--yes", action="store_true", help="Confirm deletion without prompting")
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default=config.get("DEFAULT", "format", fallback="table"),
        help="Output format",
    )
    # Robustly read workers default from config (allow empty)
    _workers_cfg = config.get("DEFAULT", "workers", fallback="").strip()
    try:
        _workers_default = int(_workers_cfg) if _workers_cfg else None
    except ValueError:
        _workers_default = None
    parser.add_argument(
        "--workers",
        type=int,
        default=_workers_default,
        help="Number of worker threads (default: auto)",
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "advanced", "config"],
        default=None,
        help="Interactive mode selection when no args are provided",
    )
    parser.add_argument(
        "--all-types",
        action="store_true",
        help="Ignore include filters and scan all file types",
    )
    parser.add_argument(
        "--no-exclude",
        action="store_true",
        help="Ignore exclude filters",
    )
    args = parser.parse_args()

    # Convert exclude and include from comma-separated strings to lists if needed
    if isinstance(args.exclude, str):
        args.exclude = [ext.strip() for ext in args.exclude.split(",")]
    if isinstance(args.include, str):
        args.include = [ext.strip() for ext in args.include.split(",")]

    # Set delete flag based on command-line argument or config file
    if not args.delete:
        args.delete = config.getboolean("DEFAULT", "delete", fallback=False)

    # Interactive selection if no args
    if len(sys.argv) == 1:
        mode = args.mode
        if not mode:
            choice = (
                input("Choose mode: [Q]uick, [A]dvanced, or [C]onfig? [Q]: ")
                .strip()
                .lower()
            )
            if choice in ("a", "advanced"):
                mode = "advanced"
            elif choice in ("c", "config"):
                mode = "config"
            else:
                mode = "quick"

        if mode == "config":
            print("Using configuration file settings.")
        elif mode == "quick":
            print("Quick mode: minimal prompts.")
            args.directory = (
                input("Directories (comma-separated) [default: current directory]: ")
                or os.getcwd()
            )
            args.size_threshold = int(
                input("Minimum size in MB [default: 100]: ") or 100
            )
            lim = input("Limit results (optional): ").strip()
            args.limit = int(lim) if lim else None
            # others default from config
        else:  # advanced
            print("Advanced mode: customize all options.")
            args.directory = (
                input("Directories (comma-separated) [default: current directory]: ")
                or os.getcwd()
            )
            args.size_threshold = int(
                input("Minimum size in MB [default: 100]: ") or 100
            )
            args.output = input("Output file (optional): ") or None
            exclude_input = input("Exclude types (e.g., .txt .log) (optional): ")
            args.exclude = exclude_input.split() if exclude_input else None
            include_input = input("Include types (e.g., .mp4 .pdf) (optional): ")
            args.include = include_input.split() if include_input else None
            lim = input("Limit results (optional): ").strip()
            args.limit = int(lim) if lim else None
            delete_input = input("Delete listed files? (y/N): ").strip().lower()
            args.delete = delete_input in ("y", "yes")
            fmt = input("Format: table/json/csv [table]: ").strip().lower()
            args.format = fmt if fmt in ("table", "json", "csv") else "table"

    directories_to_scan = [os.path.abspath(d.strip()) for d in args.directory.split(",")]
    size_threshold = args.size_threshold * 1024 * 1024  # Convert MB to bytes

    # Apply override flags for filters
    if getattr(args, "all_types", False):
        args.include = None
    if getattr(args, "no_exclude", False):
        args.exclude = None

    # Log chosen filters and start message
    logging.info(
        f"Scanning directories: {directories_to_scan} for files larger than {args.size_threshold} MB..."
    )
    logging.info(
        "Filters -> include: %s | exclude: %s",
        (", ".join(args.include) if args.include else "ALL"),
        (", ".join(args.exclude) if args.exclude else "NONE"),
    )

    try:
        large_files = find_large_files(
            directories_to_scan,
            size_threshold,
            include_types=args.include,
            exclude_types=args.exclude,
            workers=args.workers,
        )
        used_files = display_large_files(
            large_files, output_file=args.output, limit=args.limit, output_format=args.format
        )
        if args.delete and used_files:
            if not getattr(args, "yes", False):
                total_bytes = sum(sz for _, sz in used_files)
                print(
                    f"\nAbout to delete {len(used_files)} files totaling {format_size(total_bytes)}."
                )
                confirm = input("Proceed? (y/N): ").strip().lower()
                if confirm not in ("y", "yes"):
                    logging.info("Deletion cancelled.")
                    return
            deleted, failed = 0, 0
            for file_path, _ in used_files:
                try:
                    os.remove(file_path)
                    deleted += 1
                except OSError as e:
                    failed += 1
                    logging.error(f"Failed to delete '{file_path}': {e}")
            logging.info(f"Deletion complete. Deleted: {deleted}, Failed: {failed}")
    except Exception as e:
        logging.exception("An unexpected error occurred.")


if __name__ == "__main__":
    main()
