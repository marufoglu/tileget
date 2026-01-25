import asyncio
import gzip
import os
import random
import signal
import sqlite3
import time

import httpx
import tiletanic

from tileget.arg import parse_arg

# ダウンロード速度を計測するためのグローバル変数
downloaded_count = 0
start_time = 0.0

# グレースフルシャットダウン用フラグ
shutdown_requested = False


class RateLimiter:
    def __init__(self, rps: int):
        self.rps = rps
        self.interval = 1.0 / rps
        self.last_request_time = 0.0
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """レートリミットを取得。シャットダウン時はFalseを返す"""
        if shutdown_requested:
            return False

        async with self.lock:
            if shutdown_requested:
                return False

            now = time.monotonic()
            wait_time = self.last_request_time + self.interval - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                if shutdown_requested:
                    return False

            self.last_request_time = time.monotonic()
            return True


def normalize_format(ext: str, default: str | None = None) -> str:
    """拡張子をMBTiles仕様のformat値に正規化"""
    ext = ext.lower().lstrip(".")
    if not ext:
        if default is None:
            raise ValueError("format must be specified when url has no extension")
        return normalize_format(default)
    if ext in ("jpeg", "jpg"):
        return "jpg"
    if ext in ("mvt", "pbf"):
        return "pbf"
    return ext


def is_retryable_error(e: Exception) -> bool:
    if isinstance(e, httpx.TimeoutException):
        return True
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code >= 500 or e.response.status_code == 429
    return False


async def fetch_data(
    client: httpx.AsyncClient,
    url: str,
    timeout: float,
    retries: int,
    retry_delay: float,
) -> bytes | None:
    global downloaded_count

    for attempt in range(retries + 1):
        try:
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()
            downloaded_count += 1
            elapsed = time.monotonic() - start_time
            speed = downloaded_count / elapsed if elapsed > 0 else 0
            print(f"{downloaded_count} tiles ({speed:.1f} tiles/s): {url}")
            return response.content
        except Exception as e:
            if not is_retryable_error(e) or attempt == retries:
                if isinstance(e, httpx.HTTPStatusError):
                    print(f"{e.response.status_code}: {url}")
                elif isinstance(e, httpx.TimeoutException):
                    print(f"timeout: {url}")
                else:
                    print(f"{e}: {url}")
                return None

            delay = retry_delay * (2**attempt) + random.uniform(0, 1)
            print(f"retry {attempt + 1}/{retries} after {delay:.1f}s: {url}")
            await asyncio.sleep(delay)
            if shutdown_requested:
                return None

    return None


async def download_dir(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    tile: tiletanic.Tile,
    tileurl: str,
    output_path: str,
    timeout: float,
    overwrite: bool,
    retries: int,
    retry_delay: float,
):
    ext = os.path.splitext(tileurl.split("?")[0])[-1]

    write_dir = os.path.join(output_path, str(tile.z), str(tile.x))
    write_filepath = os.path.join(write_dir, str(tile.y) + ext)

    if os.path.exists(write_filepath) and not overwrite:
        return

    if not await rate_limiter.acquire():
        return

    url = (
        tileurl.replace(r"{x}", str(tile.x))
        .replace(r"{y}", str(tile.y))
        .replace(r"{z}", str(tile.z))
    )

    data = await fetch_data(client, url, timeout, retries, retry_delay)
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
    timeout: float,
    overwrite: bool,
    tms: bool,
    retries: int,
    retry_delay: float,
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

    if not await rate_limiter.acquire():
        return

    url = (
        tileurl.replace(r"{x}", str(tile.x))
        .replace(r"{y}", str(tile.y))
        .replace(r"{z}", str(tile.z))
    )

    data = await fetch_data(client, url, timeout, retries, retry_delay)
    if data is None:
        return

    # MVT(pbf)はgzip圧縮して保存する必要がある
    ext = os.path.splitext(tileurl.split("?")[0])[-1].lower().lstrip(".")
    if ext in ("mvt", "pbf") and data[:2] != b"\x1f\x8b":
        data = gzip.compress(data)

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
            name TEXT PRIMARY KEY,
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
    global start_time, shutdown_requested
    params = parse_arg()
    start_time = time.monotonic()

    # SIGINTハンドラを設定
    loop = asyncio.get_running_loop()

    def handle_sigint():
        global shutdown_requested
        if not shutdown_requested:
            shutdown_requested = True
            print("\nShutdown requested. Waiting for running tasks to complete...")

    loop.add_signal_handler(signal.SIGINT, handle_sigint)
    loop.add_signal_handler(signal.SIGTERM, handle_sigint)

    rate_limiter = RateLimiter(params.rps)

    conn = None
    if params.mode == "mbtiles":
        is_new = not os.path.exists(params.output_path)
        if is_new:
            create_mbtiles(params.output_path)

        conn = sqlite3.connect(params.output_path, check_same_thread=False)

        if is_new:
            ext = os.path.splitext(params.tileurl.split("?")[0])[-1]
            c = conn.cursor()
            c.execute(
                "INSERT INTO metadata (name, value) VALUES (?, ?)",
                ("name", os.path.basename(params.output_path)),
            )
            c.execute(
                "INSERT INTO metadata (name, value) VALUES (?, ?)",
                ("format", normalize_format(ext, params.format)),
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
            if shutdown_requested:
                break

            tiles = tiletanic.tilecover.cover_geometry(
                tilescheme, params.geometry, zoom
            )

            # TaskGroupの代わりに手動でタスクを管理
            pending_tasks: set[asyncio.Task] = set()

            for tile in tiles:
                if shutdown_requested:
                    break

                if params.mode == "dir":
                    task = asyncio.create_task(
                        download_dir(
                            client,
                            rate_limiter,
                            tile,
                            params.tileurl,
                            params.output_path,
                            params.timeout,
                            params.overwrite,
                            params.retries,
                            params.retry_delay,
                        )
                    )
                else:
                    assert conn is not None
                    task = asyncio.create_task(
                        download_mbtiles(
                            client,
                            rate_limiter,
                            conn,
                            tile,
                            params.tileurl,
                            params.timeout,
                            params.overwrite,
                            params.tms,
                            params.retries,
                            params.retry_delay,
                        )
                    )
                pending_tasks.add(task)
                task.add_done_callback(pending_tasks.discard)

            # 残っているタスクの完了を待つ
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)

    if conn is not None:
        conn.close()

    if shutdown_requested:
        print("Shutdown complete.")
    else:
        print("finished")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
