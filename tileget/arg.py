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
    minzoom: int = 0
    maxzoom: int = 16
    interval: int = 1000
    overwrite: bool = False
    timeout: int = 5000
    tms: bool = False


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
    parser.add_argument(
        "--interval",
        default=500,
        type=int,
        help="time taken after each-request, set as miliseconds in interger, default to 500",
    )
    parser.add_argument(
        "--overwrite", help="overwrite existing files", action="store_true"
    )
    parser.add_argument(
        "--timeout",
        default=5000,
        type=int,
        help="wait response until this value, set as miliseconds in integer, default to 5000",
    )
    parser.add_argument("--tms", help="if set, parse z/x/y as TMS", action="store_true")
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
        interval=args.interval,
        overwrite=args.overwrite,
        timeout=args.timeout,
        tms=args.tms,
    )

    return params
