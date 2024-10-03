import os
import sys
import subprocess
import numpy as np
import rasterio


def generateVegIndices(ortho_file, flight_dir):
    index_folder = os.path.join(flight_dir, 'veg_indices')
    if not os.path.exists(index_folder):
        os.makedirs(index_folder)
    rasterio_dataset = rasterio.open(ortho_file)
    band_mapping = {}
    for band, name in zip(rasterio_dataset.indexes,
                          rasterio_dataset.descriptions):
        if name:
            band_mapping[name.lower()] = band
    # bandmapping > 4 (and not 3) indicates multispec since there always is
    # an empty band
    if len(band_mapping) > 3:
        red_band = rasterio_dataset.read(band_mapping['red']).astype('float64')
        nir_band = rasterio_dataset.read(band_mapping['nir']).astype('float64')

        # TODO: Check if default should be np.nan
        ndvi = np.where((nir_band == 0.) | (red_band == 0.), -255,
                        np.where((nir_band + red_band) == 0., 0,
                                 (nir_band - red_band) / (nir_band + red_band)))

        del red_band
        del nir_band

        profile = rasterio_dataset.profile
        profile.update(
            dtype=rasterio.float64,
            count=1
        )
        with rasterio.open(os.path.join(index_folder, 'ndvi_image.tif'), 'w',
                           **profile, BIGTIFF='YES') as op:
            op.write(ndvi.astype(rasterio.float64), 1)

        lai = 0.75 * np.exp(ndvi)
        del ndvi
        with rasterio.open(os.path.join(index_folder, 'lai_image.tif'), 'w',
                           **profile, BIGTIFF='YES') as op:
            op.write(lai.astype(rasterio.float64), 1)
    else:
        try:
            red_band = rasterio_dataset.read(band_mapping['red']).astype(
                'float64')
            green_band = rasterio_dataset.read(band_mapping['green']).astype(
                'float64')
            blue_band = rasterio_dataset.read(band_mapping['blue']).astype(
                'float64')
            vari = np.where((green_band + red_band - blue_band) == 0, np.nan,
                            (green_band - red_band) / (
                                    green_band + red_band - blue_band))

            del red_band
            del green_band
            del blue_band

            vari[np.isnan(vari)] = np.nan
            # Metadata for the new NDVI raster
            profile = rasterio_dataset.profile
            profile.update(
                dtype=rasterio.float64,
                count=1
            )
            # Write the NDVI raster to a new GeoTIFF file
            with rasterio.open(os.path.join(index_folder, 'vari_image.tif'),
                               'w',
                               **profile, BIGTIFF='YES') as op:
                op.write(vari.astype(rasterio.float64), 1)
            # explict delete to claim memory
            del vari

            red_band = rasterio_dataset.read(band_mapping['red']).astype(
                'float64')
            green_band = rasterio_dataset.read(band_mapping['green']).astype(
                'float64')
            blue_band = rasterio_dataset.read(band_mapping['blue']).astype(
                'float64')

            gli = np.where((2 * green_band + red_band + blue_band) == 0, np.nan,
                           (2 * green_band - red_band - blue_band) / (
                                   2 * green_band + red_band + blue_band))

            del red_band
            del green_band
            del blue_band

            # Set any potential division by zero or NaN values to NaN
            gli[np.isnan(gli)] = np.nan
            with rasterio.open(os.path.join(index_folder, 'gli_image.tif'), 'w',
                               **profile, BIGTIFF='YES') as op:
                op.write(gli.astype(rasterio.float64), 1)
        except Exception as e:
            print(e)


if __name__ == '__main__':
    ortho_file = sys.argv[1]
    flight_dir = sys.argv[2]

    cog_file = os.path.join(os.path.split(ortho_file)[0],
                            'odm_orthophoto_cog.tif')
    subprocess.run(['rio', 'cogeo', 'create', ortho_file, cog_file])
    generateVegIndices(cog_file, flight_dir)
