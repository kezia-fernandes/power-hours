from powerhours import store


def test_upsert_is_idempotent(prices, tmp_path):
    store.upsert(prices, "price", "DE-LU", public=True, root=tmp_path)
    store.upsert(prices.tail(500), "price", "DE-LU", public=True, root=tmp_path)
    assert len(store.read("price", "DE-LU", root=tmp_path)) == len(prices)


def test_newer_value_replaces_older(prices, tmp_path):
    store.upsert(prices, "price", "DE-LU", public=True, root=tmp_path)
    changed = prices.head(1).assign(value=-999.0)
    store.upsert(changed, "price", "DE-LU", public=True, root=tmp_path)
    stored = store.read("price", "DE-LU", root=tmp_path)
    assert stored["value"].iloc[0] == -999.0


def test_restricted_data_goes_to_private_folder(prices, tmp_path):
    store.upsert(prices, "price", "NO2", public=False, root=tmp_path)
    assert list((tmp_path / "private" / "price" / "NO2").glob("*.parquet"))
    assert not (tmp_path / "public").exists()
    assert len(store.read("price", "NO2", root=tmp_path)) == len(prices)


def test_duckdb_view_exposes_zone_as_key(prices, tmp_path):
    store.upsert(prices, "price", "DE-LU", public=True, root=tmp_path)
    store.upsert(prices, "price", "NO2", public=False, root=tmp_path)
    con = store.connect(root=tmp_path)
    counts = dict(con.sql("SELECT key, count(*) FROM price GROUP BY key").fetchall())
    assert counts == {"DE-LU": len(prices), "NO2": len(prices)}
