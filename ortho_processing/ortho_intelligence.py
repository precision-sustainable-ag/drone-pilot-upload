import os
import sys

import numpy as np
import rasterio


def generateVegIndices(ortho_file, flight_dir):
    index_folder = os.path.join(flight_dir, "veg_indices")
    if not os.path.exists(index_folder):
        os.makedirs(index_folder)
    rasterio_dataset = rasterio.open(ortho_file)
    print("RasterIO dataset read")
    band_mapping = {}
    for band, name in zip(rasterio_dataset.indexes, rasterio_dataset.descriptions, strict=False):
        if name:
            band_mapping[name.lower()] = band
    # bandmapping > 4 (and not 3) indicates multispec since there always is
    # an empty band
    if len(band_mapping) > 3:
        print("Running multispec pipeline")
        red_band = rasterio_dataset.read(band_mapping["red"]).astype("float32")
        nir_band = rasterio_dataset.read(band_mapping["nir"]).astype("float32")

        # TODO: Check if default should be np.nan
        ndvi = np.where(
            (nir_band == 0.0) | (red_band == 0.0),
            -255,
            np.where(
                (nir_band + red_band) == 0.0, 0, (nir_band - red_band) / (nir_band + red_band)
            ),
        )
        print("NDVI values generated")

        del red_band
        del nir_band

        profile = rasterio_dataset.profile
        profile.update(dtype=rasterio.float32, count=1)
        with rasterio.open(
            os.path.join(index_folder, "ndvi_image.tif"), "w", **profile, BIGTIFF="YES"
        ) as op:
            op.write(ndvi.astype(rasterio.float32), 1)
        print("NDVI file written")

        lai = 0.75 * np.exp(ndvi)
        print("LAI values generated")
        del ndvi
        with rasterio.open(
            os.path.join(index_folder, "lai_image.tif"), "w", **profile, BIGTIFF="YES"
        ) as op:
            op.write(lai.astype(rasterio.float32), 1)
        print("LAI file written")
    else:
        print("Running RGB pipeline")
        try:
            red_band = rasterio_dataset.read(band_mapping["red"]).astype("float32")
            green_band = rasterio_dataset.read(band_mapping["green"]).astype("float32")
            blue_band = rasterio_dataset.read(band_mapping["blue"]).astype("float32")
            vari = np.where(
                (green_band + red_band - blue_band) == 0,
                np.nan,
                (green_band - red_band) / (green_band + red_band - blue_band),
            )
            print("VARI values generated")
            del red_band
            del green_band
            del blue_band

            vari[np.isnan(vari)] = np.nan
            # Metadata for the new NDVI raster
            profile = rasterio_dataset.profile
            profile.update(dtype=rasterio.float32, count=1)
            # Write the NDVI raster to a new GeoTIFF file
            with rasterio.open(
                os.path.join(index_folder, "vari_image.tif"), "w", **profile, BIGTIFF="YES"
            ) as op:
                op.write(vari.astype(rasterio.float32), 1)
            print("VARI file written")

            # explict delete to claim memory
            del vari
            red_band = rasterio_dataset.read(band_mapping["red"]).astype("float32")
            green_band = rasterio_dataset.read(band_mapping["green"]).astype("float32")
            blue_band = rasterio_dataset.read(band_mapping["blue"]).astype("float32")

            gli = np.where(
                (2 * green_band + red_band + blue_band) == 0,
                np.nan,
                (2 * green_band - red_band - blue_band) / (2 * green_band + red_band + blue_band),
            )
            del red_band
            del green_band
            del blue_band

            # Set any potential division by zero or NaN values to NaN
            gli[np.isnan(gli)] = np.nan
            print("GLI values generated")

            with rasterio.open(
                os.path.join(index_folder, "gli_image.tif"), "w", **profile, BIGTIFF="YES"
            ) as op:
                op.write(gli.astype(rasterio.float32), 1)
            print("GLI file written")

        except Exception as e:
            print(e)


def process_in_chunks(rasterio_dataset, index_folder, chunk_size=512):
    # Get the dimensions of the raster
    band_mapping = {}
    for band, name in zip(rasterio_dataset.indexes, rasterio_dataset.descriptions, strict=False):
        if name:
            band_mapping[name.lower()] = band
    height, width = rasterio_dataset.height, rasterio_dataset.width
    # Profile for writing new raster files
    profile = rasterio_dataset.profile
    profile.update(dtype=rasterio.float32, count=1, BIGTIFF="YES")

    with (
        rasterio.open(os.path.join(index_folder, "vari_image.tif"), "w", **profile) as vari_dest,
        rasterio.open(os.path.join(index_folder, "gli_image.tif"), "w", **profile) as gli_dest,
    ):
        for i in range(0, height, chunk_size):
            for j in range(0, width, chunk_size):
                # Define the window to read the chunk
                window = rasterio.windows.Window(
                    j, i, min(chunk_size, width - j), min(chunk_size, height - i)
                )

                # Read chunks of the red and nir bands
                red_band = rasterio_dataset.read(band_mapping["red"], window=window).astype(
                    "float32"
                )
                green_band = rasterio_dataset.read(band_mapping["green"], window=window).astype(
                    "float32"
                )
                blue_band = rasterio_dataset.read(band_mapping["blue"], window=window).astype(
                    "float32"
                )

                # Calculate NDVI for the chunk
                vari = np.where(
                    (green_band + red_band - blue_band) == 0,
                    np.nan,
                    (green_band - red_band) / (green_band + red_band - blue_band),
                )
                vari[np.isnan(vari)] = np.nan
                # Write NDVI chunk to file
                vari_dest.write(vari.astype(rasterio.float32), 1, window=window)

                # Calculate LAI for the chunk
                gli = np.where(
                    (2 * green_band + red_band + blue_band) == 0,
                    np.nan,
                    (2 * green_band - red_band - blue_band)
                    / (2 * green_band + red_band + blue_band),
                )
                gli[np.isnan(gli)] = np.nan

                gli_dest.write(gli.astype(rasterio.float32), 1, window=window)
                del red_band, blue_band, green_band, vari, gli

    print("NDVI and LAI files written in chunks")


if __name__ == "__main__":
    ortho_file = sys.argv[1]
    flight_dir = sys.argv[2]

    cog_file = os.path.join(os.path.split(ortho_file)[0], "odm_orthophoto_cog.tif")
    # rio_op = subprocess.run(['rio', 'cogeo', 'create', ortho_file, cog_file],
    #                         capture_output=True, text=True)
    # print(f"RIO OUTPUT:: \n\n{rio_op.stdout}")
    # print(f"RIO ERROR:: \n\n{rio_op.stderr}")
    # print("=====")
    # generateVegIndices(ortho_file, flight_dir)
    rasterio_dataset = rasterio.open(ortho_file)
    index_folder = os.path.join(flight_dir, "veg_indices")
    if not os.path.exists(index_folder):
        os.makedirs(index_folder)
    rasterio_dataset = rasterio.open(ortho_file)
    print("RasterIO dataset read")
    process_in_chunks(rasterio_dataset, index_folder)
