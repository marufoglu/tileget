import asyncio
import os
import random
import sqlite3
import time

import httpx
import tiletanic

from tileget.arg import parse_arg

MAX_RETRIES = 3
BASE_DELAY = 1.0


class RateLimiter:
    def __init__(self, rps: int):
        self.rps = rps
        self.interval = 1.0 / rps
        self.last_request_time = 0.0
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
            wait_time = self.last_request_time + self.interval - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_request_time = time.monotonic()


def is_retryable_error(e: Exception) -> bool:
    if isinstance(e, httpx.TimeoutException):
        return True
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code >= 500 or e.response.status_code == 429
    return False


async def fetch_data(
    client: httpx.AsyncClient, url: str, timeout: int = 5000
) -> bytes | None:
    print("downloading: " + url)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.get(url, timeout=timeout / 1000)
            response.raise_for_status()
            return response.content
        except Exception as e:
            if not is_retryable_error(e) or attempt == MAX_RETRIES:
                if isinstance(e, httpx.HTTPStatusError):
                    print(f"{e.response.status_code}: {url}")
                elif isinstance(e, httpx.TimeoutException):
                    print(f"timeout: {url}")
                else:
                    print(f"{e}: {url}")
                return None

            delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
            print(f"retry {attempt + 1}/{MAX_RETRIES} after {delay:.1f}s: {url}")
            await asyncio.sleep(delay)

    return None


async def download_dir(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    tile: tiletanic.Tile,
    tileurl: str,
    output_path: str,
    timeout: int = 5000,
    overwrite: bool = False,
):
    ext = os.path.splitext(tileurl.split("?")[0])[-1]

    write_dir = os.path.join(output_path, str(tile.z), str(tile.x))
    write_filepath = os.path.join(write_dir, str(tile.y) + ext)

    if os.path.exists(write_filepath) and not overwrite:
        return

    await rate_limiter.acquire()
    url = (
        tileurl.replace(r"{x}", str(tile.x))
        .replace(r"{y}", str(tile.y))
        .replace(r"{z}", str(tile.z))
    )

    data = await fetch_data(client, url, timeout)
    if data is None:
        return

    os.makedirs(write_dir, exist_ok=True)
    with open(write_filepath, mode="wb") as f:
        f.write(data)


async def download_mbtiles(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
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
        ty = (1 << tile.z) - 1 - tile.y

    c = conn.cursor()
    c.execute(
        "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
        (tile.z, tile.x, ty),
    )
    if c.fetchone() is not None and not overwrite:
        return

    await rate_limiter.acquire()
    url = (
        tileurl.replace(r"{x}", str(tile.x))
        .replace(r"{y}", str(tile.y))
        .replace(r"{z}", str(tile.z))
    )

    data = await fetch_data(client, url, timeout)
    if data is None:
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


async def run():
    params = parse_arg()

    rate_limiter = RateLimiter(params.rps)

    conn = None
    if params.mode == "mbtiles":
        if not os.path.exists(params.output_path):
            create_mbtiles(params.output_path)

        conn = sqlite3.connect(params.output_path, check_same_thread=False)

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

    tilescheme = (
        tiletanic.tileschemes.WebMercatorBL()
        if params.tms
        else tiletanic.tileschemes.WebMercator()
    )

    async with httpx.AsyncClient() as client:
        for zoom in range(params.minzoom, params.maxzoom + 1):
            tiles = tiletanic.tilecover.cover_geometry(
                tilescheme, params.geometry, zoom
            )

            for tile in tiles:
                if params.mode == "dir":
                    await download_dir(
                        client,
                        rate_limiter,
                        tile,
                        params.tileurl,
                        params.output_path,
                        params.timeout,
                        params.overwrite,
                    )
                else:
                    assert conn is not None
                    await download_mbtiles(
                        client,
                        rate_limiter,
                        conn,
                        tile,
                        params.tileurl,
                        params.timeout,
                        params.overwrite,
                        params.tms,
                    )

    if conn is not None:
        conn.close()

    print("finished")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
