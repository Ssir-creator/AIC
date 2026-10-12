from zipfile import ZipFile
import pytest
from scripts.download_guitarset import checksum, extract_verified


def test_verified_extraction_is_repeatable_and_preserves_changed_files(tmp_path):
    archive = tmp_path / "source.zip"
    with ZipFile(archive,"w") as z:
        z.writestr("annotation/file.jams", "original")
    expected = checksum(archive)
    output = tmp_path / "output"
    extract_verified(archive, output, expected)
    extract_verified(archive, output, expected)
    file = output / "annotation/file.jams"
    assert file.read_text() == "original"
    file.write_text("user work")
    with pytest.raises(ValueError,match="不同内容"):
        extract_verified(archive, output, expected)
    assert file.read_text() == "user work"


def test_checksum_failure_stops_extraction(tmp_path):
    archive = tmp_path / "source.zip"
    with ZipFile(archive,"w") as z:
        z.writestr("file", "test")
    with pytest.raises(ValueError,match="校验失败"):
        extract_verified(archive, tmp_path / "output", "0"*32)
    assert not (tmp_path / "output").exists()


def test_archive_path_escape_is_rejected(tmp_path):
    archive = tmp_path / "source.zip"
    with ZipFile(archive,"w") as z:
        z.writestr("../outside", "test")
    with pytest.raises(ValueError,match="非法路径"):
        extract_verified(archive, tmp_path / "output", checksum(archive))
    assert not (tmp_path / "outside").exists()
