# tileget

![GitHub Release](https://img.shields.io/github/v/release/Kanahiro/tileget)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/Kanahiro/tileget/lint.yml?label=lint)

Tile download utility - easily download xyz-tile data.

## Requirements

- Python >= 3.14

## Installation

```sh
pip install tileget
```

## Usage

```plaintext
usage: tileget [-h] [-e OUTPUT_DIR] [-o OUTPUT_FILE] [--extent EXTENT EXTENT EXTENT EXTENT]
               [--geojson GEOJSON] [--minzoom MINZOOM] [--maxzoom MAXZOOM] [--rps RPS] [--overwrite]
               [--timeout TIMEOUT] [--tms] [--retries RETRIES] [--retry-delay RETRY_DELAY]
               tileurl

xyz-tile download tool

positional arguments:
  tileurl               xyz-tile url in {z}/{x}/{y} template

options:
  -h, --help            show this help message and exit
  -e, --output_dir OUTPUT_DIR
                        output dir
  -o, --output_file OUTPUT_FILE
                        output mbtiles file
  --extent EXTENT EXTENT EXTENT EXTENT
                        min_lon min_lat max_lon max_lat, whitespace delimited
  --geojson GEOJSON     path to geojson file of Feature or FeatureCollection
  --minzoom MINZOOM     default to 0
  --maxzoom MAXZOOM     default to 16
  --rps RPS             requests per second, must be positive, default to 1
  --overwrite           overwrite existing files
  --timeout TIMEOUT     wait response until this value in seconds, default to 5.0
  --tms                 if set, parse z/x/y as TMS
  --retries RETRIES     max retry count on error, default to 3
  --retry-delay RETRY_DELAY
                        base delay in seconds for exponential backoff, default to 1.0
```

### Examples

```sh
# basic usage
tileget http://path/to/tile/{z}/{x}/{y}.jpg -e output_dir --extent 141.23 40.56 142.45 43.78
tileget http://path/to/tile/{z}/{x}/{y}.jpg -o output.mbtiles --geojson input.geojson

# with rate limiting and retry options
tileget http://path/to/tile/{z}/{x}/{y}.jpg -e output_dir --extent 141.23 40.56 142.45 43.78 --minzoom 0 --maxzoom 16 --rps 5 --retries 5 --retry-delay 2.0 --timeout 10 --overwrite
```
