"""Integration tests for FileDFReader, common for all FileDF connections.

Test only that options generated by both FileDFReader and FileDFReader.Options are passed to Spark,
and behavior is the same as described in documentation.
Also test internal validation of values passed to .run() method.

Do not test all possible options and combinations, we are not testing Spark here.
"""

import logging
import secrets

import pytest

from onetl._util.spark import get_spark_version
from onetl.file import FileDFReader
from onetl.file.format import CSV

try:
    from pyspark.sql.types import (
        DateType,
        DoubleType,
        IntegerType,
        StructField,
        StructType,
        TimestampType,
    )

    from tests.util.assert_df import assert_equal_df
except ImportError:
    # pandas and spark can be missing if someone runs tests for file connections only
    pass


def test_file_df_reader_run(
    file_df_connection_with_path_and_files,
    file_df_dataframe,
):
    file_df_connection, source_path, _ = file_df_connection_with_path_and_files
    df = file_df_dataframe
    csv_root = source_path / "csv/without_header"

    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=csv_root,
        df_schema=df.schema,
    )
    read_df = reader.run()

    assert read_df.count()
    assert read_df.schema == df.schema
    assert_equal_df(read_df, file_df_dataframe)


@pytest.mark.parametrize(
    "pass_source_path",
    [False, True],
    ids=["Without source_path", "With source_path"],
)
def test_file_df_reader_run_with_files(
    file_df_connection_with_path_and_files,
    file_df_dataframe,
    pass_source_path,
    caplog,
):
    file_df_connection, source_path, uploaded_files = file_df_connection_with_path_and_files
    df = file_df_dataframe

    csv_root = source_path / "csv/without_header"
    csv_files = [file for file in uploaded_files if csv_root in file.parents]

    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=csv_root if pass_source_path else None,
        df_schema=df.schema,
    )

    with caplog.at_level(logging.WARNING):
        read_df = reader.run(csv_files)

        if pass_source_path:
            assert (
                "Passed both `source_path` and files list at the same time. Using explicit files list"
            ) in caplog.text

    assert read_df.count()
    assert read_df.schema == df.schema
    assert_equal_df(read_df, df)


def test_file_df_reader_run_with_files_relative_and_source_path(
    file_df_connection_with_path_and_files,
    file_df_dataframe,
):
    file_df_connection, source_path, uploaded_files = file_df_connection_with_path_and_files
    df = file_df_dataframe
    csv_root = source_path / "csv/without_header"

    csv_files = [file for file in uploaded_files if csv_root in file.parents]
    relative_files_path = [file.relative_to(csv_root) for file in csv_files]

    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=csv_root,
        df_schema=df.schema,
    )

    read_df = reader.run(file for file in relative_files_path)

    assert read_df.count()
    assert read_df.schema == df.schema
    assert_equal_df(read_df, df)


def test_file_df_reader_run_without_files_and_source_path(file_df_connection):
    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
    )
    with pytest.raises(ValueError, match="Neither file list nor `source_path` are passed"):
        reader.run()


@pytest.mark.parametrize(
    "pass_source_path",
    [False, True],
    ids=["Without source_path", "With source_path"],
)
def test_file_df_reader_run_with_empty_files_input(
    file_df_connection_with_path_and_files,
    pass_source_path,
    file_df_schema,
):
    file_df_connection, source_path, _ = file_df_connection_with_path_and_files
    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=source_path if pass_source_path else None,
        df_schema=file_df_schema,
    )

    read_df = reader.run([])  # this argument takes precedence
    assert not read_df.count()
    assert read_df.schema == file_df_schema


def test_file_df_reader_run_relative_path_without_source_path(file_df_connection):
    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
    )

    with pytest.raises(ValueError, match="Cannot pass relative file path with empty `source_path`"):
        reader.run(["some/relative/path/file.txt"])


def test_file_df_reader_run_absolute_path_not_match_source_path(file_df_connection_with_path_and_files):
    file_df_connection, source_path, _ = file_df_connection_with_path_and_files
    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=source_path,
    )

    error_message = f"File path '/some/relative/path/file.txt' does not match source_path '{source_path}'"
    with pytest.raises(ValueError, match=error_message):
        reader.run(["/some/relative/path/file.txt"])


def test_file_df_reader_source_path_does_not_exist(file_df_connection, file_df_schema):
    source_path = f"/tmp/test_read_{secrets.token_hex(5)}"

    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=source_path,
        df_schema=file_df_schema,
    )

    with pytest.raises(Exception, match="does not exist"):
        reader.run()


def test_file_df_reader_source_path_cannot_be_file(file_df_connection_with_path_and_files, file_df_schema):
    file_df_connection, source_path, _ = file_df_connection_with_path_and_files
    csv_file = source_path / "csv/without_header/file.csv"

    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=csv_file,
        df_schema=file_df_schema,
    )

    with pytest.raises(Exception, match="must be a directory"):
        reader.run()


def test_file_df_reader_run_recursive_false(spark, file_df_connection_with_path_and_files, file_df_schema):
    spark_version = get_spark_version(spark)
    if spark_version.major < 3:
        pytest.skip("Option `recursive` is not supported on Spark 2")

    file_df_connection, source_path, _ = file_df_connection_with_path_and_files

    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=source_path / "csv/nested",
        df_schema=file_df_schema,
        options=FileDFReader.Options(recursive=False),
    )

    read_df = reader.run()
    assert not read_df.count()


def test_file_df_reader_run_recursive_true(
    spark,
    file_df_connection_with_path_and_files,
    file_df_dataframe,
):
    spark_version = get_spark_version(spark)
    if spark_version.major < 3:
        pytest.skip("Option `recursive` is not supported on Spark 2")

    file_df_connection, source_path, _ = file_df_connection_with_path_and_files
    df = file_df_dataframe

    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=source_path / "csv/nested",
        df_schema=df.schema,
        options=FileDFReader.Options(recursive=True),
    )
    read_df = reader.run()

    assert read_df.count()
    assert read_df.schema == df.schema
    assert_equal_df(read_df, df, order_by="id")


def test_file_df_reader_run_partitioned(
    file_df_connection_with_path_and_files,
    file_df_schema_str_value_last,
    file_df_dataframe,
):
    file_df_connection, source_path, _ = file_df_connection_with_path_and_files
    df = file_df_dataframe

    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=source_path / "csv/partitioned",
        df_schema=df.schema,
    )

    read_df = reader.run()

    assert read_df.count()
    assert read_df.schema == file_df_schema_str_value_last
    assert_equal_df(read_df, df, order_by="id")


def test_file_df_reader_run_partitioned_recursive(spark, file_df_connection_with_path_and_files, file_df_dataframe):
    spark_version = get_spark_version(spark)
    if spark_version.major < 3:
        pytest.skip("Option `recursive` is not supported on Spark 2")

    file_df_connection, source_path, _ = file_df_connection_with_path_and_files

    # csv does not contain "str_value" column.
    # do not pass it to df_schema, otherwise dataframe will be corrupted - "date_value" column will contain string value
    real_df_schema = StructType(
        [
            StructField("id", IntegerType()),
            StructField("int_value", IntegerType()),
            StructField("date_value", DateType()),
            StructField("datetime_value", TimestampType()),
            StructField("float_value", DoubleType()),
        ],
    )

    reader = FileDFReader(
        connection=file_df_connection,
        format=CSV(),
        source_path=source_path / "csv/partitioned",
        df_schema=real_df_schema,
        options=FileDFReader.Options(recursive=True),
    )

    read_df = reader.run()

    assert read_df.count()
    assert read_df.schema == real_df_schema

    expected_df = file_df_dataframe.drop("str_value")
    assert_equal_df(read_df, expected_df, order_by="id")
