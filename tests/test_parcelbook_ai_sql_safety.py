import pytest

from parcelbook_ai.sql_safety import validate_and_limit_sql

SRC = "read_parquet('r2://openskagit/derived/parcel_search.parquet')"


def test_select_allowed_and_limit_added():
    sql = validate_and_limit_sql(f"SELECT parcel_number FROM {SRC}", limit=10)
    assert "LIMIT 10" in sql


def test_with_select_allowed():
    sql = validate_and_limit_sql(f"WITH p AS (SELECT * FROM {SRC}) SELECT parcel_number FROM p", limit=5)
    assert sql.endswith("LIMIT 5;")


@pytest.mark.parametrize("keyword", ["DELETE", "DROP", "INSTALL", "LOAD", "SECRET"])
def test_forbidden_keywords_rejected(keyword):
    with pytest.raises(ValueError):
        validate_and_limit_sql(f"{keyword} whatever; SELECT * FROM {SRC}")


def test_arbitrary_file_path_rejected():
    with pytest.raises(ValueError):
        validate_and_limit_sql("SELECT * FROM read_parquet('/tmp/private.parquet')")


def test_excessive_limit_reduced():
    sql = validate_and_limit_sql(f"SELECT * FROM {SRC} LIMIT 1000", limit=25)
    assert "LIMIT 25" in sql
    assert "LIMIT 1000" not in sql
