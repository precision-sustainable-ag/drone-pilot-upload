#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


MATCH_RE = re.compile(
    r"Matching\s+"
    r"(\S+\.jpg)\s+and\s+(\S+\.jpg)"
    r".*?"
    r"Success:\s+(True|False)"
)

INDEX_RE = re.compile(
    r"-(\d{12})\.jpg$",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot OpenSfM image-match relationships over the "
            "mapped drone flight path."
        )
    )

    parser.add_argument(
        "mapping_csv",
        type=Path,
        help="CSV produced by map-flight-images.py",
    )

    parser.add_argument(
        "odm_log",
        type=Path,
        help="ODM stdout log containing OpenSfM Matching records",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("opensfm-match-graph.png"),
        help="Output PNG filename",
    )

    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("opensfm-match-pairs.csv"),
        help="Output CSV containing parsed match pairs",
    )

    parser.add_argument(
        "--label-every",
        type=int,
        default=20,
        help="Label every Nth flight image",
    )

    parser.add_argument(
        "--show-failed",
        action="store_true",
        help="Also draw attempted pairs that failed matching",
    )

    parser.add_argument(
        "--match-alpha",
        type=float,
        default=0.28,
        help="Opacity of successful match lines",
    )

    parser.add_argument(
        "--match-linewidth",
        type=float,
        default=0.65,
        help="Width of successful match lines",
    )

    parser.add_argument(
        "--title",
        default="OpenSfM match graph",
        help="Plot title",
    )

    #
    # Optional performance-comparison values.
    #
    parser.add_argument(
        "--atlas-wall",
        help="Atlas wall time in HH:MM:SS",
    )

    parser.add_argument(
        "--ceres-wall",
        help="Ceres wall time in HH:MM:SS",
    )

    parser.add_argument(
        "--atlas-cpu",
        help="Atlas accumulated CPU time in HH:MM:SS",
    )

    parser.add_argument(
        "--ceres-cpu",
        help="Ceres accumulated CPU time in HH:MM:SS",
    )

    parser.add_argument(
        "--atlas-memory",
        type=float,
        help="Atlas peak memory in GB",
    )

    parser.add_argument(
        "--ceres-memory",
        type=float,
        help="Ceres peak memory in GB",
    )

    return parser.parse_args()


def duration_seconds(value: str) -> int:
    fields = value.split(":")

    if len(fields) != 3:
        raise ValueError(
            f"Expected HH:MM:SS duration, got: {value}"
        )

    hours, minutes, seconds = map(int, fields)

    return (
        hours * 3600
        + minutes * 60
        + seconds
    )


def duration_minutes(value: str) -> float:
    return duration_seconds(value) / 60.0


def load_mapping(path: Path) -> dict[int, dict]:
    mapping = {}

    with path.open(
        newline="",
        encoding="utf-8",
    ) as stream:
        for row in csv.DictReader(stream):
            index = int(row["mongo_index"])

            mapping[index] = {
                "filename": row["filename"],
                "longitude": float(row["mongo_longitude"]),
                "latitude": float(row["mongo_latitude"]),
                "capture_time": row["capture_time"],
            }

    if not mapping:
        raise RuntimeError(
            f"No mapping records found in {path}"
        )

    return mapping


def image_index(filename: str) -> int:
    match = INDEX_RE.search(filename)

    if match is None:
        raise ValueError(
            f"Cannot extract flight index from filename: {filename}"
        )

    return int(match.group(1))


def parse_matches(path: Path) -> list[dict]:
    matches = []

    with path.open(
        encoding="utf-8",
        errors="replace",
    ) as stream:
        for line_number, line in enumerate(
            stream,
            start=1,
        ):
            match = MATCH_RE.search(line)

            if match is None:
                continue

            filename_a = match.group(1)
            filename_b = match.group(2)
            success = match.group(3) == "True"

            try:
                index_a = image_index(filename_a)
                index_b = image_index(filename_b)
            except ValueError:
                continue

            matches.append(
                {
                    "line_number": line_number,
                    "index_a": index_a,
                    "index_b": index_b,
                    "filename_a": filename_a,
                    "filename_b": filename_b,
                    "success": success,
                }
            )

    return matches


def local_xy(
    longitude: float,
    latitude: float,
    center_lon: float,
    center_lat: float,
) -> tuple[float, float]:
    """
    Convert longitude/latitude to local meters using an
    equirectangular projection.

    This is more than adequate for a flight footprint only a
    few hundred meters across.
    """

    earth_radius = 6371008.8

    x = (
        math.radians(longitude - center_lon)
        * earth_radius
        * math.cos(math.radians(center_lat))
    )

    y = (
        math.radians(latitude - center_lat)
        * earth_radius
    )

    return x, y


def planar_distance_m(
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]

    return math.hypot(dx, dy)


def add_panel_background(
    axis,
    facecolor,
    edgecolor,
) -> None:
    """
    Draw a rounded rectangle behind an information panel.
    """

    panel = FancyBboxPatch(
        (0.01, 0.01),
        0.98,
        0.98,
        transform=axis.transAxes,
        boxstyle="round,pad=0.015,rounding_size=0.025",
        linewidth=1.2,
        facecolor=facecolor,
        edgecolor=edgecolor,
        clip_on=False,
        zorder=-10,
    )

    axis.add_patch(panel)


def main() -> None:
    args = parse_args()

    mapping = load_mapping(
        args.mapping_csv
    )

    matches = parse_matches(
        args.odm_log
    )

    if not matches:
        raise RuntimeError(
            f"No OpenSfM matching records found in {args.odm_log}"
        )

    longitudes = [
        item["longitude"]
        for item in mapping.values()
    ]

    latitudes = [
        item["latitude"]
        for item in mapping.values()
    ]

    center_lon = sum(longitudes) / len(longitudes)
    center_lat = sum(latitudes) / len(latitudes)

    xy = {}

    for index, item in mapping.items():
        xy[index] = local_xy(
            item["longitude"],
            item["latitude"],
            center_lon,
            center_lat,
        )

    valid_matches = []
    missing_indices = set()

    for item in matches:
        a = item["index_a"]
        b = item["index_b"]

        if a not in xy:
            missing_indices.add(a)
            continue

        if b not in xy:
            missing_indices.add(b)
            continue

        item["sequence_gap"] = abs(a - b)

        item["camera_distance_m"] = planar_distance_m(
            xy[a],
            xy[b],
        )

        valid_matches.append(item)

    matches = valid_matches

    success_count = sum(
        1
        for item in matches
        if item["success"]
    )

    failure_count = (
        len(matches) - success_count
    )

    unique_pairs = {
        tuple(
            sorted(
                (
                    item["index_a"],
                    item["index_b"],
                )
            )
        )
        for item in matches
    }

    total_possible_pairs = (
        len(mapping)
        * (len(mapping) - 1)
        // 2
    )

    evaluated_percent = (
        100.0
        * len(unique_pairs)
        / total_possible_pairs
    )

    success_percent = (
        100.0
        * success_count
        / len(matches)
    )

    failure_percent = (
        100.0
        * failure_count
        / len(matches)
    )

    #
    # Write pair-analysis CSV.
    #
    with args.csv.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:
        fieldnames = [
            "index_a",
            "index_b",
            "success",
            "sequence_gap",
            "camera_distance_m",
            "filename_a",
            "filename_b",
            "line_number",
        ]

        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for item in matches:
            writer.writerow(
                {
                    key: item[key]
                    for key in fieldnames
                }
            )

    import matplotlib.pyplot as plt

    #
    # Presentation-oriented layout:
    #
    #   large flight/match plot | performance
    #                           | match stats
    #
    figure = plt.figure(
        figsize=(18, 10)
    )

    grid = figure.add_gridspec(
        nrows=2,
        ncols=2,
        width_ratios=(4.7, 1.3),
        height_ratios=(1, 1),
        wspace=0.08,
        hspace=0.28,
    )

    axis = figure.add_subplot(
        grid[:, 0]
    )

    performance_axis = figure.add_subplot(
        grid[0, 1]
    )

    stats_axis = figure.add_subplot(
        grid[1, 1]
    )

    ordered_indices = sorted(mapping)

    flight_x = [
        xy[index][0]
        for index in ordered_indices
    ]

    flight_y = [
        xy[index][1]
        for index in ordered_indices
    ]

    #
    # Draw failed matches first, if requested.
    #
    if args.show_failed:
        first_failed = True

        for item in matches:
            if item["success"]:
                continue

            a = item["index_a"]
            b = item["index_b"]

            axis.plot(
                [xy[a][0], xy[b][0]],
                [xy[a][1], xy[b][1]],
                color="#c95c5c",
                linewidth=0.55,
                alpha=0.20,
                linestyle="--",
                zorder=0,
                label=(
                    "Failed match"
                    if first_failed
                    else None
                ),
            )

            first_failed = False

    #
    # Successful OpenSfM matching graph.
    #
    first_success = True

    for item in matches:
        if not item["success"]:
            continue

        a = item["index_a"]
        b = item["index_b"]

        axis.plot(
            [xy[a][0], xy[b][0]],
            [xy[a][1], xy[b][1]],
            color="#3a9d5d",
            linewidth=args.match_linewidth,
            alpha=args.match_alpha,
            zorder=1,
            label=(
                "Successful match"
                if first_success
                else None
            ),
        )

        first_success = False

    #
    # Flight trajectory.
    #
    axis.plot(
        flight_x,
        flight_y,
        color="#1565c0",
        linewidth=2.0,
        zorder=4,
        label="Flight path",
    )

    axis.scatter(
        flight_x,
        flight_y,
        color="#1565c0",
        s=19,
        zorder=5,
        label="Camera positions",
    )

    #
    # Start and finish markers.
    #
    start_index = ordered_indices[0]
    end_index = ordered_indices[-1]

    axis.scatter(
        [xy[start_index][0]],
        [xy[start_index][1]],
        s=85,
        marker="o",
        edgecolor="black",
        linewidth=0.8,
        zorder=7,
        label="Start",
    )

    axis.scatter(
        [xy[end_index][0]],
        [xy[end_index][1]],
        s=85,
        marker="s",
        edgecolor="black",
        linewidth=0.8,
        zorder=7,
        label="Finish",
    )

    #
    # Sparse sequence labels.
    #
    if args.label_every > 0:
        for index in ordered_indices:
            if (
                index == 1
                or index == len(ordered_indices)
                or index % args.label_every == 0
            ):
                x, y = xy[index]

                axis.annotate(
                    str(index),
                    (x, y),
                    xytext=(4, 4),
                    textcoords="offset points",
                    fontsize=9,
                    fontweight="bold",
                    zorder=8,
                )

    axis.set_xlabel(
        "East-west position relative to flight center (m)",
        fontsize=11,
    )

    axis.set_ylabel(
        "North-south position relative to flight center (m)",
        fontsize=11,
    )

    axis.set_aspect(
        "equal",
        adjustable="box",
    )

    axis.grid(
        True,
        linewidth=0.35,
        alpha=0.30,
    )

    axis.legend(
        loc="upper left",
        framealpha=0.96,
        fontsize=9,
    )


    #
    # Performance panel.
    #
    performance_axis.axis("off")

    add_panel_background(
        performance_axis,
        facecolor="#eef6ff",
        edgecolor="#6aa8ff",
    )

    performance_axis.text(
        0.50,
        0.94,
        "Atlas vs. Ceres performance",
        transform=performance_axis.transAxes,
        horizontalalignment="center",
        verticalalignment="top",
        fontsize=12,
        fontweight="bold",
    )

    performance_axis.text(
        0.50,
        0.865,
        "313-image full-flight ODM 3.6.2",
        transform=performance_axis.transAxes,
        horizontalalignment="center",
        verticalalignment="top",
        fontsize=9.5,
    )

    if (
        args.atlas_wall
        and args.ceres_wall
    ):
        atlas_minutes = duration_minutes(
            args.atlas_wall
        )

        ceres_minutes = duration_minutes(
            args.ceres_wall
        )

        speedup = (
            ceres_minutes
            / atlas_minutes
        )

        inset = performance_axis.inset_axes(
            [0.13, 0.60, 0.78, 0.22]
        )

        names = [
            "Atlas L40S",
            "Ceres CPU",
        ]

        values = [
            atlas_minutes,
            ceres_minutes,
        ]

        y_positions = list(range(len(names)))

        bars = inset.barh(
            y_positions,
            values,
            color="#2c7fb8",
        )

        inset.set_yticks(y_positions)
        inset.set_yticklabels(names)
        inset.invert_yaxis()

        inset.set_xlabel(
            "Wall-clock minutes",
            fontsize=8.5,
        )

        inset.tick_params(
            axis="both",
            labelsize=8.5,
        )

        inset.grid(
            axis="x",
            linewidth=0.3,
            alpha=0.3,
        )

        maximum = max(values)

        inset.set_xlim(
            0,
            maximum * 1.20,
        )

        for bar, value in zip(
            bars,
            values,
        ):
            inset.text(
                value + maximum * 0.025,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.1f}",
                verticalalignment="center",
                fontsize=8.5,
                fontweight="bold",
            )

        performance_lines = [
            f"Atlas wall:    {args.atlas_wall}",
            f"Ceres wall:    {args.ceres_wall}",
            f"Atlas speedup: {speedup:.2f}x",
        ]

        if (
            args.atlas_cpu
            and args.ceres_cpu
        ):
            performance_lines.extend(
                [
                    "",
                    f"Atlas CPU:     {args.atlas_cpu}",
                    f"Ceres CPU:     {args.ceres_cpu}",
                ]
            )

        if (
            args.atlas_memory is not None
            and args.ceres_memory is not None
        ):
            performance_lines.extend(
                [
                    "",
                    f"Atlas memory:  {args.atlas_memory:.2f} GB",
                    f"Ceres memory:  {args.ceres_memory:.2f} GB",
                ]
            )

        performance_lines.extend(
            [
                "",
                "Both jobs:",
                "COMPLETED, exit code 0",
            ]
        )

        performance_axis.text(
            0.10,
            0.47,
            "\n".join(performance_lines),
            transform=performance_axis.transAxes,
            horizontalalignment="left",
            verticalalignment="top",
            fontsize=9.2,
            family="monospace",
        )

    else:
        performance_axis.text(
            0.50,
            0.50,
            "Performance values\nnot supplied",
            transform=performance_axis.transAxes,
            horizontalalignment="center",
            verticalalignment="center",
            fontsize=11,
        )


    #
    # Matching-statistics panel.
    #
    stats_axis.axis("off")

    add_panel_background(
        stats_axis,
        facecolor="#f0faee",
        edgecolor="#69b96b",
    )

    #
    # Keep the heading well inside the panel rather than using
    # set_title(), which can collide with the panel above.
    #
    stats_axis.text(
        0.50,
        0.91,
        "OpenSfM matching",
        transform=stats_axis.transAxes,
        horizontalalignment="center",
        verticalalignment="top",
        fontsize=12,
        fontweight="bold",
    )

    #
    # Horizontal rule beneath the heading.
    #
    stats_axis.plot(
        [0.08, 0.92],
        [0.84, 0.84],
        transform=stats_axis.transAxes,
        color="0.55",
        linewidth=0.7,
    )

    stats_text = (
        f"Images:              {len(mapping):,}\n"
        f"Possible pairs:      {total_possible_pairs:,}\n"
        f"Candidate pairs:     {len(unique_pairs):,}\n"
        f"Pairs evaluated:     {evaluated_percent:.1f}%\n"
        "\n"
        f"Successful:          {success_count:,}\n"
        f"Success rate:        {success_percent:.1f}%\n"
        f"Failed:              {failure_count:,}\n"
        f"Failure rate:        {failure_percent:.1f}%\n"
        "\n"
        "Blue:\n"
        "  acquisition path\n"
        "  and camera positions\n"
        "\n"
        "Green:\n"
        "  successful image-pair\n"
        "  feature matches"
    )

    stats_axis.text(
        0.10,
        0.79,
        stats_text,
        transform=stats_axis.transAxes,
        horizontalalignment="left",
        verticalalignment="top",
        fontsize=9.2,
        family="monospace",
    )


    #
    # Figure titles.
    #
    figure.suptitle(
        args.title,
        fontsize=17,
        fontweight="bold",
        y=0.985,
    )

    figure.text(
        0.42,
        0.942,
        (
            f"{len(mapping):,} images - "
            f"{len(unique_pairs):,} candidate pairs - "
            f"{success_count:,} successful matches"
        ),
        horizontalalignment="center",
        fontsize=11,
    )

    #
    # Final layout and output.
    #
    figure.subplots_adjust(
        left=0.055,
        right=0.975,
        bottom=0.075,
        top=0.91,
    )

    figure.savefig(
        args.output,
        dpi=220,
        bbox_inches="tight",
    )

    #
    # Console summary.
    #
    print(
        f"Parsed matching records:  {len(matches)}"
    )

    print(
        f"Unique image pairs:       {len(unique_pairs)}"
    )

    print(
        f"Successful matches:       {success_count}"
    )

    print(
        f"Failed matches:           {failure_count}"
    )

    print(
        f"Possible image pairs:     {total_possible_pairs}"
    )

    print(
        f"Pairs evaluated:          "
        f"{evaluated_percent:.1f}%"
    )

    print(
        f"Missing flight indices:   "
        f"{len(missing_indices)}"
    )

    if (
        args.atlas_wall
        and args.ceres_wall
    ):
        speedup = (
            duration_seconds(args.ceres_wall)
            / duration_seconds(args.atlas_wall)
        )

        print()

        print(
            f"Atlas wall time:          {args.atlas_wall}"
        )

        print(
            f"Ceres wall time:          {args.ceres_wall}"
        )

        print(
            f"Atlas wall-time speedup:  {speedup:.2f}x"
        )

    print()

    print(
        f"Match CSV written:        {args.csv.resolve()}"
    )

    print(
        f"Plot written:             {args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
