#!/usr/bin/env python3
"""Generate PNG previews of an Atlas ODM orthophoto and RGB vegetation indices."""

import argparse
import warnings
from pathlib import Path
from uuid import UUID

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import NotGeoreferencedWarning

DEFAULT_DATA_ROOT = Path('/project/dash_drone/user/stephen.amerige/dpu-data')
PREVIEW_WIDTH = 2000
COLOR_STOPS = (0.0, 0.5, 1.0)
COLORS = ((115, 72, 42), (245, 224, 128), (30, 130, 65))


def flight_directory(data_root, flight_id):
    try:
        if str(UUID(flight_id)) != flight_id:
            raise ValueError('Flight ID must be a canonical lowercase UUID')
    except ValueError as exc:
        raise ValueError(f'Invalid flight ID: {flight_id}') from exc

    site_id = data_root / 'site-id'
    if not site_id.is_dir():
        raise FileNotFoundError(f'Atlas flight storage not found: {site_id}')
    matches = [
        path for path in site_id.glob(f'*/flights/{flight_id}')
        if path.is_dir() and not path.is_symlink()
        and not path.parent.is_symlink() and not path.parent.parent.is_symlink()
    ]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one flight directory, found {len(matches)}')
    return matches[0]


def write_png(path, rgba):
    # PNG previews are intentionally not georeferenced; source GeoTIFFs remain intact.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', NotGeoreferencedWarning)
        with rasterio.open(
            path, 'w', driver='PNG', width=rgba.shape[2],
            height=rgba.shape[1], count=4, dtype='uint8',
        ) as dst:
            dst.write(rgba)
    print(f'Created: {path}', flush=True)


def generate(flight_dir):
    odm = flight_dir / 'odm'
    orthophoto = odm / 'code/odm_orthophoto/odm_orthophoto.tif'
    indices = {name: odm / f'veg_indices/{name}_image.tif' for name in ('vari', 'gli')}
    for path in (orthophoto, *indices.values()):
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f'Missing or empty required artifact: {path}')

    previews = flight_dir / 'previews'
    if previews.is_symlink():
        raise ValueError(f'Refusing symlinked preview directory: {previews}')

    with rasterio.open(orthophoto) as src:
        if src.count != 4:
            raise ValueError(f'Expected RGBA orthophoto, found {src.count} bands')
        source_size = (src.width, src.height)
        width = min(PREVIEW_WIDTH, src.width)
        height = max(1, round(src.height * width / src.width))
        rgba = src.read(
            (1, 2, 3, 4), out_shape=(4, height, width),
            resampling=Resampling.nearest,
        )

    previews.mkdir(exist_ok=True)
    alpha = rgba[3].copy()
    write_png(previews / 'orthophoto.png', rgba)

    for name, path in indices.items():
        with rasterio.open(path) as src:
            if src.count != 1 or (src.width, src.height) != source_size:
                raise ValueError(f'Unexpected dimensions or bands in {path}')
            values = src.read(
                1, out_shape=(height, width), resampling=Resampling.nearest,
            )

        valid = np.isfinite(values) & (alpha > 0)
        if not valid.any():
            raise ValueError(f'No valid pixels in {name.upper()}')
        low, high = np.percentile(values[valid], [2, 98])
        if high <= low:
            raise ValueError(f'No usable contrast range in {name.upper()}')

        finite = np.nan_to_num(values, nan=low, posinf=high, neginf=low)
        scaled = np.clip((finite - low) / (high - low), 0.0, 1.0)
        preview = np.zeros((4, height, width), dtype=np.uint8)
        for channel in range(3):
            preview[channel] = np.interp(
                scaled, COLOR_STOPS, [rgb[channel] for rgb in COLORS],
            ).astype(np.uint8)
        preview[3] = np.where(valid, alpha, 0)
        write_png(previews / f'{name}.png', preview)
        print(f'{name.upper()} display range: {low:.4f} to {high:.4f}')

    print(f'Previews completed: {previews}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flight_id', help='Canonical flight UUID')
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT)
    args = parser.parse_args()
    generate(flight_directory(args.data_root.expanduser().resolve(strict=True), args.flight_id))


if __name__ == '__main__':
    main()
