"""Storage: monthly Parquet files on disk, queried with DuckDB.

Layout
    data/public/<dataset>/<key>/<YYYY-MM>.parquet    <- committed to git
    data/private/<dataset>/<key>/<YYYY-MM>.parquet   <- git-ignored (restricted licence)

Why this design?
- Parquet files are small and only the current month's file changes each day,
  so the daily job can commit data to git without bloating the repository.
- DuckDB reads all files with one glob, so analysis is plain SQL.
- Writing is an "upsert": re-running the same ingestion never duplicates rows.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from powerhours.config import data_dir

KEY_COLUMNS = {
    "price": ["ts_utc", "series"],
    "power": ["ts_utc", "series"],
    "exog": ["ts_utc", "series"],
    "exog_seen": ["ts_utc", "series"],
    "forecast": ["ts_utc", "model"],
}


def _folder(dataset: str, key: str, public: bool, root: Path | None = None) -> Path:
    visibility = "public" if public else "private"
    return (root or data_dir()) / visibility / dataset / key


def upsert(
    frame: pd.DataFrame, dataset: str, key: str, public: bool, root: Path | None = None
) -> int:
    """Merge `frame` into the store. Returns the number of rows written.

    Rows are identified by KEY_COLUMNS[dataset]; a newer row replaces an older one.
    """
    if frame.empty:
        return 0
    keys = KEY_COLUMNS[dataset]
    folder = _folder(dataset, key, public, root)
    folder.mkdir(parents=True, exist_ok=True)

    months = frame["ts_utc"].dt.tz_convert("UTC").dt.strftime("%Y-%m")
    for month, part in frame.groupby(months):
        path = folder / f"{month}.parquet"
        if path.exists():
            part = pd.concat([pd.read_parquet(path), part], ignore_index=True)
        part = part.drop_duplicates(subset=keys, keep="last").sort_values(keys)
        part.to_parquet(path, index=False)
    return len(frame)


def insert_new(
    frame: pd.DataFrame, dataset: str, key: str, public: bool, root: Path | None = None
) -> int:
    """Like `upsert`, but rows that already exist are left untouched ("first write wins").

    Used for anything that must not be rewritten with hindsight, such as saved forecasts.
    """
    existing = read(dataset, key, root=root)
    if not existing.empty and not frame.empty:
        keys = KEY_COLUMNS[dataset]
        seen = set(existing[keys].itertuples(index=False, name=None))
        is_new = [row not in seen for row in frame[keys].itertuples(index=False, name=None)]
        frame = frame[is_new]
    return upsert(frame, dataset, key, public, root)


def read(dataset: str, key: str, root: Path | None = None) -> pd.DataFrame:
    """Read everything stored for one dataset/key (public and private) as a DataFrame."""
    files = [
        str(path)
        for public in (True, False)
        for path in sorted(_folder(dataset, key, public, root).glob("*.parquet"))
    ]
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).sort_values(
        KEY_COLUMNS[dataset]
    )


def connect(root: Path | None = None) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with one view per dataset (`price`, `power`, `exog`, `forecast`, ...).

    Each view has a `key` column (the zone or country), taken from the folder name.
    Example:
        con = connect()
        con.sql("SELECT key, avg(value) FROM price GROUP BY key").df()
    """
    root = root or data_dir()
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    for dataset in KEY_COLUMNS:
        files = [str(p) for p in root.glob(f"*/{dataset}/*/*.parquet")]
        if not files:
            continue
        # Folder layout is <root>/<visibility>/<dataset>/<key>/<month>.parquet,
        # so the key is the second-to-last part of the file path.
        file_list = ", ".join("'" + f.replace("'", "''") + "'" for f in files)
        con.execute(
            f"""
            CREATE VIEW {dataset} AS
            SELECT * EXCLUDE (filename),
                   string_split(replace(filename, chr(92), '/'), '/')[-2] AS key
            FROM read_parquet([{file_list}], filename = true, union_by_name = true)
            """
        )
    return con
