from typing import Tuple

import pytest

import ebook


@pytest.mark.parametrize(
    ("urlId", "expected"),
    [
        (
            "abc",
            (
                f"{ebook.PRIMARY_CACHE_DIR}/epub/abc/abc",
                f"{ebook.SECONDARY_CACHE_DIR}/epub/abc/abc",
            ),
        ),
        (
            "abcd",
            (
                f"{ebook.PRIMARY_CACHE_DIR}/epub/abc/d/abcd",
                f"{ebook.SECONDARY_CACHE_DIR}/epub/abc/d/abcd",
            ),
        ),
        (
            "abcdef",
            (
                f"{ebook.PRIMARY_CACHE_DIR}/epub/abc/def/abcdef",
                f"{ebook.SECONDARY_CACHE_DIR}/epub/abc/def/abcdef",
            ),
        ),
        (
            "abcdefhi",
            (
                f"{ebook.PRIMARY_CACHE_DIR}/epub/abc/def/hi/abcdefhi",
                f"{ebook.SECONDARY_CACHE_DIR}/epub/abc/def/hi/abcdefhi",
            ),
        ),
    ],
)
def test_buildExportPath(urlId: str, expected: Tuple[str, str]) -> None:
    assert ebook.buildExportPath("epub", urlId, create=False) == expected
