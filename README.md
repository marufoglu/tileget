# tileget

Tile download utility - easily download xyz-tile data.

## installation

```sh
pip install tileget
```

## usage

```planetext
usage: __main__.py [-h] [-e OUTPUT_DIR] [-o OUTPUT_FILE] [--extent EXTENT EXTENT EXTENT EXTENT] [--geojson GEOJSON] [--minzoom MINZOOM] [--maxzoom MAXZOOM] [--interval INTERVAL] [--overwrite] [--timeout TIMEOUT] [--tms]
                   tileurl

xyz-tile download tool

positional arguments:
  tileurl               xyz-tile url in {z}/{x}/{y} template

options:
  -h, --help            show this help message and exit
  -e OUTPUT_DIR, --output_dir OUTPUT_DIR
                        output dir
  -o OUTPUT_FILE, --output_file OUTPUT_FILE
                        output mbtiles file
  --extent EXTENT EXTENT EXTENT EXTENT
                        min_lon min_lat max_lon max_lat, whitespace delimited
  --geojson GEOJSON     path to geojson file of Feature or FeatureCollection
  --minzoom MINZOOM     default to 0
  --maxzoom MAXZOOM     default to 16
  --interval INTERVAL   time taken after each-request, set as miliseconds in interger, default to 500
  --overwrite           overwrite existing files
  --timeout TIMEOUT     wait response until this value, set as miliseconds in integer, default to 5000
  --tms                 if set, parse z/x/y as TMS
```

### examples

```sh
# basic usage
tileget http://path/to/tile/{z}/{x}/{y}.jpg -e output_dir --extent 141.23 40.56 142.45 43.78
tileget http://path/to/tile/{z}/{x}/{y}.jpg -o output.mbtiles --geojson input.geojson

# optional arguments
tileget http://path/to/tile/{z}/{x}/{y}.jpg -e output_dir --extent 141.23 40.56 142.45 43.78 --minzoom 0 --maxzoom 16 --interval 500 --timeout 5000 --overwrite
```
