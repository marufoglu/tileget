import os
import sqlite3
import time
import urllib.request

import tiletanic

from tileget.arg import parse_arg


def fetch_data(url: str, timeout: int = 5000) -> bytes:
    print("downloading: " + url)
    data = None
    while True:
        try:
            data = urllib.request.urlopen(url, timeout=timeout / 1000)
            break
        except urllib.error.HTTPError as e:
            raise Exception(str(e) + ":" + url)
        except Exception as e:
            if (
                str(e.args)
                == "(timeout('_ssl.c:1091: The handshake operation timed out'),)"
            ):
                print("timeout, retrying... :" + url)
            else:
                raise Exception(str(e) + ":" + url)

    return data.read()


def create_mbtiles(output_file: str):
    conn = sqlite3.connect(output_file)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE metadata (
            name TEXT,
            value TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE tiles (
            zoom_level INTEGER,
            tile_column INTEGER,
            tile_row INTEGER,
            tile_data BLOB
        )
        """
    )
    c.execute(
        """
        CREATE UNIQUE INDEX tile_index
        ON tiles (zoom_level, tile_column, tile_row)
        """
    )
    conn.commit()
    conn.close()

    return output_file


def download_dir(
    tile: tiletanic.Tile,
    tileurl: str,
    output_path: str,
    timeout: int = 5000,
    overwrite: bool = False,
):
    # detect file extension from tileurl
    # tileurl = https://path/to/{z}/{x}/{y}.ext?foo=bar...&hoge=fuga.json
    ext = os.path.splitext(tileurl.split("?")[0])[-1]

    write_dir = os.path.join(output_path, str(tile.z), str(tile.x))
    write_filepath = os.path.join(write_dir, str(tile.y) + ext)

    if os.path.exists(write_filepath) and not overwrite:
        # skip if already exists when not-overwrite mode
        return

    url = (
        tileurl.replace(r"{x}", str(tile.x))
        .replace(r"{y}", str(tile.y))
        .replace(r"{z}", str(tile.z))
    )

    try:
        data = fetch_data(url, timeout)
    except Exception as e:
        print(e)
        return

    os.makedirs(write_dir, exist_ok=True)
    with open(write_filepath, mode="wb") as f:
        f.write(data)


def download_mbtiles(
    conn: sqlite3.Connection,
    tile: tiletanic.Tile,
    tileurl: str,
    timeout: int = 5000,
    overwrite: bool = False,
    tms: bool = False,
):
    if tms:
        ty = tile.y
    else:
        # flip y: xyz -> tms
        ty = (1 << tile.z) - 1 - tile.y

    c = conn.cursor()
    c.execute(
        "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
        (tile.z, tile.x, ty),
    )
    if c.fetchone() is not None and not overwrite:
        return

    url = (
        tileurl.replace(r"{x}", str(tile.x))
        .replace(r"{y}", str(tile.y))
        .replace(r"{z}", str(tile.z))
    )
    try:
        data = fetch_data(url, timeout)
    except Exception as e:
        print(e)
        return

    if overwrite:
        c.execute(
            "DELETE FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
            (tile.z, tile.x, ty),
        )

    c.execute(
        "INSERT INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
        (tile.z, tile.x, ty, data),
    )
    conn.commit()


def main():
    params = parse_arg()

    if params.mode == "dir":

        def _download(tile):
            download_dir(
                tile,
                params.tileurl,
                params.output_path,
                params.timeout,
                params.overwrite,
            )
            time.sleep(params.interval / 1000)
    elif params.mode == "mbtiles":
        if not os.path.exists(params.output_path):
            create_mbtiles(params.output_path)

        conn = sqlite3.connect(params.output_path)

        # write metadata
        c = conn.cursor()
        c.execute(
            "INSERT INTO metadata (name, value) VALUES (?, ?)",
            ("name", os.path.basename(params.output_path)),
        )
        c.execute(
            "INSERT INTO metadata (name, value) VALUES (?, ?)",
            (
                "format",
                os.path.splitext(params.tileurl.split("?")[0])[-1].replace(".", ""),
            ),
        )
        c.execute(
            "INSERT INTO metadata (name, value) VALUES (?, ?)",
            ("minzoom", params.minzoom),
        )
        c.execute(
            "INSERT INTO metadata (name, value) VALUES (?, ?)",
            ("maxzoom", params.maxzoom),
        )

        conn.commit()

        def _download(tile):
            download_mbtiles(
                conn, tile, params.tileurl, params.timeout, params.overwrite, params.tms
            )
            time.sleep(params.interval / 1000)

    tilescheme = (
        tiletanic.tileschemes.WebMercatorBL()
        if params.tms
        else tiletanic.tileschemes.WebMercator()
    )

    for zoom in range(params.minzoom, params.maxzoom + 1):
        generator = tiletanic.tilecover.cover_geometry(
            tilescheme, params.geometry, zoom
        )
        for tile in generator:
            _download(tile)

    print("finished")


if __name__ == "__main__":
    main()
