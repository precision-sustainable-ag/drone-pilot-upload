#!/usr/bin/env python3

import argparse
import math
import re
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Plot the ordered camera/GPS points stored in a MongoDB flight-information "
            "document exported as mongosh-style text."
        )
    )
    p.add_argument("input", type=Path, help="mongosh text export containing flight_polygon.geometries")
    p.add_argument("--output", type=Path, default=Path("flight-path.png"), help="output plot (default: flight-path.png)")
    p.add_argument("--csv", type=Path, help="optional CSV containing point,index,longitude,latitude,east_m,north_m")
    p.add_argument("--label-every", type=int, default=20, help="label every Nth point; 0 disables periodic labels")
    p.add_argument(
        "--highlight",
        type=str,
        default="",
        help="comma-separated 1-based Mongo geometry point numbers to highlight, e.g. 84,294",
    )
    p.add_argument("--title", default="Flight path", help="plot title")
    return p.parse_args()


def parse_points(text: str):
    # Restrict parsing to flight_polygon.geometries so that bounding-box coordinates
    # later in the document are not mistaken for camera positions.
    section = re.search(
        r"flight_polygon:\s*\{.*?geometries:\s*\[(.*?)\]\s*\}\s*,\s*flight_bounding_box:",
        text,
        re.S,
    )
    if not section:
        raise ValueError("Could not locate flight_polygon.geometries in the input document")

    pairs = re.findall(
        r"coordinates:\s*\[\s*Double\('([^']+)'\),\s*Double\('([^']+)'\)\s*\]",
        section.group(1),
        re.S,
    )
    if not pairs:
        raise ValueError("No Point coordinates found in flight_polygon.geometries")

    return [(float(lon), float(lat)) for lon, lat in pairs]


def to_local_meters(points):
    # Equirectangular approximation is more than adequate over a field-sized extent.
    lon0 = sum(lon for lon, _ in points) / len(points)
    lat0 = sum(lat for _, lat in points) / len(points)
    earth_radius_m = 6_371_008.8
    lat0_rad = math.radians(lat0)

    local = []
    for lon, lat in points:
        east = earth_radius_m * math.radians(lon - lon0) * math.cos(lat0_rad)
        north = earth_radius_m * math.radians(lat - lat0)
        local.append((east, north))
    return local


def parse_highlights(value, count):
    if not value.strip():
        return []
    result = []
    for item in value.split(","):
        n = int(item.strip())
        if not 1 <= n <= count:
            raise ValueError(f"highlight {n} is outside the valid range 1..{count}")
        result.append(n)
    return result


def write_csv(path, points, local):
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "longitude", "latitude", "east_m", "north_m"])
        for i, ((lon, lat), (east, north)) in enumerate(zip(points, local), start=1):
            w.writerow([i, f"{lon:.12f}", f"{lat:.12f}", f"{east:.3f}", f"{north:.3f}"])


def main():
    args = parse_args()
    text = args.input.read_text(encoding="utf-8")
    points = parse_points(text)
    local = to_local_meters(points)
    highlights = parse_highlights(args.highlight, len(points))

    if args.csv:
        write_csv(args.csv, points, local)

    # Import only when plotting, so parsing errors remain easy to diagnose.
    import matplotlib.pyplot as plt

    east = [p[0] for p in local]
    north = [p[1] for p in local]

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.plot(east, north, marker=".", markersize=3, linewidth=0.8)

    # Start/end markers and labels.
    ax.scatter([east[0]], [north[0]], marker="o", s=70, label="Start (1)")
    ax.scatter([east[-1]], [north[-1]], marker="s", s=70, label=f"End ({len(points)})")
    ax.annotate("1", (east[0], north[0]), xytext=(5, 5), textcoords="offset points")
    ax.annotate(str(len(points)), (east[-1], north[-1]), xytext=(5, 5), textcoords="offset points")

    if args.label_every > 0:
        for i in range(args.label_every, len(points) + 1, args.label_every):
            x, y = local[i - 1]
            ax.annotate(str(i), (x, y), xytext=(4, 4), textcoords="offset points", fontsize=8)

    for n in highlights:
        x, y = local[n - 1]
        ax.scatter([x], [y], marker="*", s=170, label=f"Highlight {n}")
        ax.annotate(str(n), (x, y), xytext=(7, 7), textcoords="offset points", fontsize=10, fontweight="bold")

    ax.set_title(f"{args.title}\n{len(points)} ordered MongoDB geometry points")
    ax.set_xlabel("East / West relative to flight centroid (m)")
    ax.set_ylabel("North / South relative to flight centroid (m)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.4)
    ax.legend(loc="best")
    fig.tight_layout()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)

    width = max(east) - min(east)
    height = max(north) - min(north)
    print(f"Parsed {len(points)} ordered geometry points")
    print(f"Approximate footprint: {width:.1f} m east-west x {height:.1f} m north-south")
    print(f"Plot written to: {args.output}")
    if args.csv:
        print(f"CSV written to: {args.csv}")
    if highlights:
        print("Highlighted Mongo geometry point numbers: " + ", ".join(map(str, highlights)))
        print("NOTE: these are Mongo geometry-order indices, not yet proven to match your renamed JPEG indices.")


if __name__ == "__main__":
    main()
