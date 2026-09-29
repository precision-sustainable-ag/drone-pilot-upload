#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import numpy as np
import rasterio

from PIL import Image
from pyproj import Transformer

FLIGHT_COLOR = "#ff00cc"
OVERLAY_COLOR = "white"
OVERLAY_OUTLINE = "black"


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Overlay a verified drone flight path on a georeferenced "
            "orthophoto and optionally rotate it for presentation."
        )
    )

    parser.add_argument(
        "orthophoto",
        type=Path,
        help="Georeferenced ODM orthophoto TIFF",
    )

    parser.add_argument(
        "mapping_csv",
        type=Path,
        help="flight-image-map.csv produced by map-flight-images.py",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("flight-over-orthophoto.png"),
    )

    parser.add_argument(
        "--max-dimension",
        type=int,
        default=2000,
        help="Maximum output raster dimension before rotation",
    )

    parser.add_argument(
        "--label-every",
        type=int,
        default=20,
        help="Label every Nth camera position; 0 disables labels",
    )

    parser.add_argument(
        "--no-rotate",
        action="store_true",
        help="Do not automatically rotate to the dominant flight axis",
    )

    parser.add_argument(
        "--no-axes",
        action="store_true",
        help="Do not draw local axes through the flight center",
    )

    parser.add_argument(
        "--platform",
        help="Processing platform, e.g. 'Atlas L40S'",
    )

    parser.add_argument(
        "--processing-time",
        help="Processing wall time, e.g. '01:26:41'",
    )

    parser.add_argument(
        "--peak-memory",
        type=float,
        help="Peak processing memory in GB",
    )

    parser.add_argument(
        "--camera-model",
        help="Camera model, e.g. 'DJI Zenmuse P1'",
    )

    parser.add_argument(
        "--show-summary",
        action="store_true",
        help="Display a flight and processing summary panel",
    )

    return parser.parse_args()


def load_mapping(path):
    rows = []

    with path.open(
        newline="",
        encoding="utf-8",
    ) as stream:
        for row in csv.DictReader(stream):
            rows.append(
                {
                    "index": int(row["mongo_index"]),
                    "longitude": float(row["mongo_longitude"]),
                    "latitude": float(row["mongo_latitude"]),
                }
            )

    rows.sort(
        key=lambda row: row["index"]
    )

    if not rows:
        raise RuntimeError(
            f"No flight positions found in {path}"
        )

    return rows


def compute_rotation_angle(x, y):
    """
    Use PCA to find the dominant direction of the flight.

    Return the angle needed to rotate that dominant direction
    to horizontal.
    """

    points = np.column_stack(
        (
            x - np.mean(x),
            y - np.mean(y),
        )
    )

    covariance = np.cov(
        points,
        rowvar=False,
    )

    eigenvalues, eigenvectors = np.linalg.eigh(
        covariance
    )

    dominant = eigenvectors[
        :,
        np.argmax(eigenvalues)
    ]

    angle = math.degrees(
        math.atan2(
            dominant[1],
            dominant[0],
        )
    )

    return -angle


def rotate_points(
    x,
    y,
    center_x,
    center_y,
    angle_degrees,
):
    theta = math.radians(
        angle_degrees
    )

    cos_theta = math.cos(theta)
    sin_theta = math.sin(theta)

    dx = x - center_x
    dy = y - center_y

    rx = (
        dx * cos_theta
        - dy * sin_theta
    )

    ry = (
        dx * sin_theta
        + dy * cos_theta
    )

    return rx, ry


def nice_scale_length(width_m):
    """
    Choose a simple human-friendly scale-bar length.
    """

    target = width_m / 5.0

    candidates = [
        1,
        2,
        5,
        10,
        20,
        25,
        50,
        100,
        200,
        500,
    ]

    return min(
        candidates,
        key=lambda value: abs(value - target),
    )


def main():
    args = parse_args()

    mapping = load_mapping(
        args.mapping_csv
    )

    with rasterio.open(
        args.orthophoto
    ) as dataset:
        if dataset.crs is None:
            raise RuntimeError(
                "Orthophoto has no CRS"
            )

        source_crs = dataset.crs

        original_width = dataset.width
        original_height = dataset.height

        pixel_size_x_m = abs(dataset.transform.a)
        pixel_size_y_m = abs(dataset.transform.e)

        scale = min(
            1.0,
            args.max_dimension
            / max(
                dataset.width,
                dataset.height,
            ),
        )

        out_width = max(
            1,
            round(dataset.width * scale),
        )

        out_height = max(
            1,
            round(dataset.height * scale),
        )

        #
        # Read RGB bands only.
        #
        image = dataset.read(
            [1, 2, 3],
            out_shape=(
                3,
                out_height,
                out_width,
            ),
            resampling=rasterio.enums.Resampling.bilinear,
        )

        image = np.moveaxis(
            image,
            0,
            2,
        )

        bounds = dataset.bounds

    #
    # Convert camera GPS positions into the orthophoto CRS.
    #
    transformer = Transformer.from_crs(
        "EPSG:4326",
        source_crs,
        always_xy=True,
    )

    longitude = np.array(
        [
            row["longitude"]
            for row in mapping
        ]
    )

    latitude = np.array(
        [
            row["latitude"]
            for row in mapping
        ]
    )

    x, y = transformer.transform(
        longitude,
        latitude,
    )

    center_x = np.mean(x)
    center_y = np.mean(y)

    #
    # Rotation angle based on the dominant flight direction.
    #
    if args.no_rotate:
        angle = 0.0
    else:
        angle = compute_rotation_angle(
            x,
            y,
        )

        #
        # PCA determines an axis but not its direction, so the
        # result is ambiguous by 180 degrees. Prefer the equivalent
        # orientation in which geographic north points upward.
        #
        theta = math.radians(angle)
        north_dy = math.cos(theta)

        if north_dy < 0:
            angle += 180.0

        #
        # Normalize to the conventional -180..180 degree range.
        #
        angle = (
            (angle + 180.0) % 360.0
        ) - 180.0

    #
    # Build the display raster.
    #
    #
    # Convert projected raster bounds into pixel coordinates.
    #
    pixel_size_x = (
        bounds.right - bounds.left
    ) / out_width

    pixel_size_y = (
        bounds.top - bounds.bottom
    ) / out_height

    center_pixel_x = (
        center_x - bounds.left
    ) / pixel_size_x

    center_pixel_y = (
        bounds.top - center_y
    ) / pixel_size_y

    pil_image = Image.fromarray(
        image
    )

    #
    # Rotate about the flight center.
    #
    rotated_image = pil_image.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        center=(
            center_pixel_x,
            center_pixel_y,
        ),
    )

    #
    # Camera coordinates expressed locally in meters around
    # the flight center, then rotated by the same angle.
    #
    local_x, local_y = rotate_points(
        x,
        y,
        center_x,
        center_y,
        angle,
    )

    #
    # Determine corresponding rotated raster corners in the
    # same local coordinate system.
    #
    corners_x = np.array(
        [
            bounds.left,
            bounds.right,
            bounds.right,
            bounds.left,
        ]
    )

    corners_y = np.array(
        [
            bounds.bottom,
            bounds.bottom,
            bounds.top,
            bounds.top,
        ]
    )

    rcx, rcy = rotate_points(
        corners_x,
        corners_y,
        center_x,
        center_y,
        angle,
    )

    extent = (
        min(rcx),
        max(rcx),
        min(rcy),
        max(rcy),
    )

    figure, axis = plt.subplots(
        figsize=(14, 10)
    )

    axis.imshow(
        rotated_image,
        extent=extent,
        origin="upper",
    )

    #
    # Flight path and camera positions.
    #
    flight_line, = axis.plot(
        local_x,
        local_y,
        color=FLIGHT_COLOR,
        linewidth=1.1,
        label="Flight path",
        zorder=5,
    )

    flight_line.set_path_effects(
        [
            path_effects.Stroke(
                linewidth=2.2,
                foreground="white",
            ),
            path_effects.Normal(),
        ]
    )

    axis.scatter(
        local_x,
        local_y,
        color=FLIGHT_COLOR,
        edgecolor="white",
        linewidth=0.6,
        s=22,
        label="Camera positions",
        zorder=6,
    )

    #
    # Start and finish.
    #
    axis.scatter(
        local_x[0],
        local_y[0],
        color=FLIGHT_COLOR,
        edgecolor="white",
        linewidth=1.2,
        s=105,
        marker="o",
        label="Start",
        zorder=8,
    )

    axis.scatter(
        local_x[-1],
        local_y[-1],
        color=FLIGHT_COLOR,
        edgecolor="white",
        linewidth=1.2,
        s=105,
        marker="s",
        label="Finish",
        zorder=8,
    )

    #
    # Sparse camera sequence labels.
    #
    if args.label_every > 0:
        for row, px, py in zip(
            mapping,
            local_x,
            local_y,
        ):
            index = row["index"]

            if (
                index == 1
                or index == len(mapping)
                or index % args.label_every == 0
            ):
                annotation = axis.annotate(
                    str(index),
                    (px, py),
                    xytext=(4, 4),
                    textcoords="offset points",
                    color="black",
                    fontsize=8,
                    fontweight="bold",
                    zorder=9,
                )

                annotation.set_path_effects(
                    [
                        path_effects.Stroke(
                            linewidth=2.5,
                            foreground="white",
                        ),
                        path_effects.Normal(),
                    ]
                )

    #
    # Local coordinate axes centered on the flight.
    #
    if not args.no_axes:
        axis.axhline(
            0,
            color="white",
            linewidth=0.7,
            alpha=0.35,
            zorder=4,
        )

        axis.axvline(
            0,
            color="white",
            linewidth=0.7,
            alpha=0.35,
            zorder=4,
        )

    #
    # North arrow.
    #
    # Before rotation, geographic north points along +Y.
    # Rotate that vector using the same display rotation.
    #
    theta = math.radians(angle)

    north_dx = -math.sin(theta)
    north_dy = math.cos(theta)

    origin_x = 0.92
    origin_y = 0.13
    arrow_length = 0.09

    tip_x = origin_x + north_dx * arrow_length
    tip_y = origin_y + north_dy * arrow_length

    axis.annotate(
        "",
        xy=(tip_x, tip_y),
        xytext=(origin_x, origin_y),
        xycoords=axis.transAxes,
        arrowprops={
            "arrowstyle": "-|>",
            "color": OVERLAY_COLOR,
            "linewidth": 2.5,
            "mutation_scale": 18,
            "path_effects": [
                path_effects.Stroke(
                    linewidth=4.0,
                    foreground=OVERLAY_OUTLINE,
                ),
                path_effects.Normal(),
            ],
        },
        zorder=20,
    )

    north_label = axis.text(
        tip_x,
        tip_y + 0.025,
        "N",
        transform=axis.transAxes,
        horizontalalignment="center",
        verticalalignment="center",
        color=OVERLAY_COLOR,
        fontsize=13,
        fontweight="bold",
        zorder=21,
    )

    north_label.set_path_effects(
        [
            path_effects.Stroke(
                linewidth=3,
                foreground=OVERLAY_OUTLINE,
            ),
            path_effects.Normal(),
        ]
    )

    #
    # Scale bar.
    #
    xmin, xmax = axis.get_xlim()
    ymin, ymax = axis.get_ylim()

    width_m = xmax - xmin

    scale_length = nice_scale_length(
        width_m
    )

    #
    # Place the scale bar in data coordinates, but use explicit
    # high-contrast styling.
    #
    bar_x = xmin + 0.07 * (xmax - xmin)
    bar_y = ymin + 0.08 * (ymax - ymin)

    scale_line, = axis.plot(
        [
            bar_x,
            bar_x + scale_length,
        ],
        [
            bar_y,
            bar_y,
        ],
        color=OVERLAY_COLOR,
        linewidth=4,
        solid_capstyle="butt",
        zorder=20,
    )

    scale_line.set_path_effects(
        [
            path_effects.Stroke(
                linewidth=6,
                foreground=OVERLAY_OUTLINE,
            ),
            path_effects.Normal(),
        ]
    )

    #
    # End ticks make it visually obvious that this is a scale.
    #
    tick_height = 3.0

    for x_position in (
        bar_x,
        bar_x + scale_length,
    ):
        tick, = axis.plot(
            [
                x_position,
                x_position,
            ],
            [
                bar_y - tick_height / 2,
                bar_y + tick_height / 2,
            ],
            color=OVERLAY_COLOR,
            linewidth=2.5,
            zorder=20,
        )

        tick.set_path_effects(
            [
                path_effects.Stroke(
                    linewidth=4,
                    foreground=OVERLAY_OUTLINE,
                ),
                path_effects.Normal(),
            ]
        )

    scale_text = axis.text(
        bar_x + scale_length / 2,
        bar_y + 4.0,
        f"{scale_length:g} m",
        horizontalalignment="center",
        verticalalignment="bottom",
        color=OVERLAY_COLOR,
        fontsize=10,
        fontweight="bold",
        zorder=21,
    )

    scale_text.set_path_effects(
        [
            path_effects.Stroke(
                linewidth=3,
                foreground=OVERLAY_OUTLINE,
            ),
            path_effects.Normal(),
        ]
    )

    #
    # Flight and processing summary.
    #
    if args.show_summary:
        flight_width_m = max(local_x) - min(local_x)
        flight_height_m = max(local_y) - min(local_y)

        mean_pixel_size_cm = (
            (pixel_size_x_m + pixel_size_y_m)
            / 2.0
            * 100.0
        )

        summary_lines = [
            "Flight summary",
            "",
            f"Images:          {len(mapping):,}",
            (
                f"Flight extent:   "
                f"{flight_width_m:.0f} x "
                f"{flight_height_m:.0f} m"
            ),
            f"Orthophoto:      {mean_pixel_size_cm:.1f} cm/pixel",
            f"CRS:             {source_crs}",
        ]

        if args.camera_model:
            summary_lines.append(
                f"Camera:          {args.camera_model}"
            )

        if args.platform:
            summary_lines.extend(
                [
                    "",
                    f"Processing:      {args.platform}",
                ]
            )

        if args.processing_time:
            summary_lines.append(
                f"Wall time:       {args.processing_time}"
            )

        if args.peak_memory is not None:
            summary_lines.append(
                f"Peak memory:     {args.peak_memory:.2f} GB"
            )

        summary_text = axis.text(
            0.72,
            0.94,
            "\n".join(summary_lines),
            transform=axis.transAxes,
            horizontalalignment="left",
            verticalalignment="top",
            color="white",
            fontsize=9,
            family="monospace",
            bbox={
                "boxstyle": "round,pad=0.6",
                "facecolor": "black",
                "edgecolor": "white",
                "linewidth": 1.0,
                "alpha": 0.72,
            },
            zorder=30,
        )

    #
    # Final plot formatting and output.
    #
    axis.set_xlabel(
        "Local X relative to flight center (m)"
    )

    axis.set_ylabel(
        "Local Y relative to flight center (m)"
    )

    axis.set_title(
        "Sandhills flight over ODM orthophoto\n"
        f"Display rotation: {angle:.1f} degrees"
    )

    axis.set_aspect(
        "equal",
        adjustable="box",
    )

    axis.legend(
        loc="upper left",
        framealpha=0.9,
    )

    figure.tight_layout()

    figure.savefig(
        args.output,
        dpi=180,
        bbox_inches="tight",
    )

    print(
        f"Orthophoto CRS:           {source_crs}"
    )

    print(
        f"Original dimensions:      "
        f"{original_width} x {original_height}"
    )

    print(
        f"Working dimensions:       "
        f"{out_width} x {out_height}"
    )

    print(
        f"Display rotation:         {angle:.2f} degrees"
    )

    print(
        f"Flight center:            "
        f"{center_x:.3f}, {center_y:.3f}"
    )

    print(
        f"Plot written:             {args.output.resolve()}"
    )

#
# Program entry point.
#
if __name__ == "__main__":
    main()
