#!/usr/bin/env python3
import os
import sys
import re

def parse_runtime(out_file):
    """Return runtime in hours if job completed successfully, else None."""
    runtime = None
    success = False
    with open(out_file, "r") as f:
        for line in f:
            if "Successfully completed" in line:
                success = True
            m = re.search(r"Run time\s*:\s*([0-9]+)", line)
            if m:
                runtime = int(m.group(1)) / 3600.0  # convert sec → hours
    return runtime if success and runtime is not None else None

def parse_max_memory(out_path):
    """
    Parse 'Max Memory :' from an LSF summary line.
    Returns a friendly string (e.g. '186 GB', '1536 MB', or '-') and
    also tries to normalize MB→GB when possible.
    """
    try:
        with open(out_path, 'r', errors='ignore') as f:
            for raw in f:
                line = raw.strip()
                if line.lower().startswith("max memory"):
                    # Split on the first colon and take the right-hand side
                    parts = line.split(":", 1)
                    if len(parts) < 2:
                        return None
                    rhs = parts[1].strip()  # e.g. '186 GB' or '-' or '1536 MB'
                    if rhs == "-" or rhs == "":
                        return "-"

                    # Tokenize value + unit (be lenient)
                    tokens = rhs.split()
                    if not tokens:
                        return None

                    val = tokens[0]
                    unit = tokens[1].upper() if len(tokens) > 1 else ""

                    # If numeric, optionally normalize MB→GB
                    try:
                        num = float(val)
                        if unit in ("MB", "M"):
                            gb = num / 1024.0
                            return f"{gb:.2f} GB"
                        elif unit in ("GB", "G"):
                            return f"{num:.0f} GB" if num.is_integer() else f"{num} GB"
                        else:
                            # Unknown unit; just return the raw RHS
                            return rhs
                    except ValueError:
                        # Not numeric (unexpected) — return raw RHS
                        return rhs
    except Exception:
        pass
    return None

def count_images(flight_dir):
    """Count number of files in images/ dir."""
    img_dir = os.path.join(flight_dir, "images")
    if not os.path.isdir(img_dir):
        return 0
    return sum(1 for _ in os.scandir(img_dir) if _.is_file())

def main():
    if len(sys.argv) < 2:
        print("Usage: python runtimes.py <research_station>")
        sys.exit(1)

    station = sys.argv[1]
    base = f"/rs1/shares/cals-research-station/{station}/flights"

    if not os.path.isdir(base):
        print(f"Station path not found: {base}")
        sys.exit(1)

    for root, dirs, files in os.walk(base):
        if "odm_processing-out.txt" in files:
            out_file = os.path.join(root, "odm_processing-out.txt")
            # If the out file lives under .../flights/<id>/code/, hop up one to the flight dir.
            flight_dir = os.path.dirname(root) if os.path.basename(root) == "code" else root
            flight_id = os.path.basename(flight_dir)

            runtime = parse_runtime(out_file)
            if runtime is not None:
                max_mem = parse_max_memory(out_file)
                images = count_images(flight_dir)

                print(f"{flight_id}\t{runtime:.2f}\t{max_mem or 'NA'}\t{images}")

if __name__ == "__main__":
    main()
