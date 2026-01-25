import argparse
import json
from dataclasses import dataclass
from typing import Literal

import shapely
from pyproj import Transformer


@dataclass
class RunParams:
    tileurl: str
    mode: Literal["dir", "mbtiles"]
    output_path: str
    geometry: shapely.geometry.base.BaseGeometry
    minzoom: int
    maxzoom: int
    rps: int
    overwrite: bool
    timeout: float
    tms: bool
    retries: int
    retry_delay: float
    format: str | None


def parse_arg() -> RunParams:
    parser = argparse.ArgumentParser(description="xyz-tile download tool")
    parser.add_argument("tileurl", help=r"xyz-tile url in {z}/{x}/{y} template")
    parser.add_argument("-e", "--output_dir", help="output dir")
    parser.add_argument("-o", "--output_file", help="output mbtiles file")
    parser.add_argument(
        "--extent",
        help="min_lon min_lat max_lon max_lat, whitespace delimited",
        nargs=4,
    )
    parser.add_argument(
        "--geojson",
        help="path to geojson file of Feature or FeatureCollection",
    )
    parser.add_argument("--minzoom", default=0, type=int, help="default to 0")
    parser.add_argument("--maxzoom", default=16, type=int, help="default to 16")

    def positive_int(value: str) -> int:
        ivalue = int(value)
        if ivalue <= 0:
            raise argparse.ArgumentTypeError("must be a positive integer")
        return ivalue

    parser.add_argument(
        "--rps",
        default=1,
        type=positive_int,
        help="requests per second, must be positive, default to 1",
    )
    parser.add_argument(
        "--overwrite", help="overwrite existing files", action="store_true"
    )
    parser.add_argument(
        "--timeout",
        default=5.0,
        type=float,
        help="wait response until this value in seconds, default to 5.0",
    )
    parser.add_argument("--tms", help="if set, parse z/x/y as TMS", action="store_true")
    parser.add_argument(
        "--retries",
        default=3,
        type=int,
        help="max retry count on error, default to 3",
    )
    parser.add_argument(
        "--retry-delay",
        default=1.0,
        type=float,
        help="base delay in seconds for exponential backoff, default to 1.0",
    )
    parser.add_argument(
        "--format",
        type=str,
        help="tile format for mbtiles metadata (e.g. png, jpg, pbf). used when url has no extension",
    )
    args = parser.parse_args()

    if args.output_dir is None and args.output_file is None:
        raise Exception("output_dir or output_file must be input")

    mode = "dir" if args.output_dir is not None else "mbtiles"
    output_path: str = (
        args.output_dir if args.output_dir is not None else args.output_file
    )

    if args.extent is None and args.geojson is None:
        raise Exception("extent or geojson must be input")

    if args.extent is not None:
        coords = tuple(map(float, args.extent))
        geometry = shapely.geometry.shape(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        (coords[0], coords[1]),
                        (coords[2], coords[1]),
                        (coords[2], coords[3]),
                        (coords[0], coords[3]),
                        (coords[0], coords[1]),
                    ],
                ],
            }
        )
    elif args.geojson is not None:
        with open(args.geojson, mode="r") as f:
            geojson = json.load(f)
        if geojson.get("features") is None:
            geometry = shapely.geometry.shape(geojson["geometry"])
        else:
            geometries = [
                shapely.geometry.shape(g)
                for g in list(map(lambda f: f["geometry"], geojson["features"]))
            ]
            geometry = shapely.ops.unary_union(geometries)

    # tiletanic accept only EPSG:3857 shape, convert
    transformer = Transformer.from_crs(4326, 3857, always_xy=True)
    geom_3857 = shapely.ops.transform(transformer.transform, geometry)

    params = RunParams(
        tileurl=args.tileurl,
        mode=mode,
        output_path=output_path,
        geometry=geom_3857,
        minzoom=args.minzoom,
        maxzoom=args.maxzoom,
        rps=args.rps,
        overwrite=args.overwrite,
        timeout=args.timeout,
        tms=args.tms,
        retries=args.retries,
        retry_delay=args.retry_delay,
        format=args.format,
    )

    return params
