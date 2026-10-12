"""Download the official archives with TLS and published archive checksums."""
import argparse
import hashlib
import json
import shutil
import stat
import urllib.request
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RECORD = "https://zenodo.org/records/3371780"
ARCHIVES = {"annotation.zip": "b39b78e63d3446f2e54ddb7a54df9b10",
            "audio_mono-mic.zip": "275966d6610ac34999b58426beb119c3"}


def checksum(path):
    md5 = hashlib.md5(usedforsecurity=False)
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            md5.update(chunk)
    return md5.hexdigest()


def verify(path, expected):
    observed = checksum(path)
    if observed != expected:
        raise ValueError(f"归档校验失败：{Path(path).name}，expected={expected}, observed={observed}；停止使用该归档")


def extract_verified(archive, destination, expected):
    verify(archive, expected)
    destination = Path(destination).resolve()
    with ZipFile(archive) as z:
        members = []
        if sum(i.file_size for i in z.infolist()) > 6 * 1024**3:
            raise ValueError("解压体积异常")
        for info in z.infolist():
            parts = PurePosixPath(info.filename)
            if parts.is_absolute() or ".." in parts.parts or "\\" in info.filename or ":" in info.filename:
                raise ValueError("归档包含非法路径")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("归档包含符号链接")
            target = destination.joinpath(*parts.parts)
            if not target.resolve().is_relative_to(destination):
                raise ValueError("目标路径越界")
            members.append((info,target))
        # Check existing files before extraction; never blindly overwrite user work.
        for info,target in members:
            if target.exists() and not info.is_dir():
                with z.open(info) as src, target.open("rb") as existing:
                    while True:
                        first, second = src.read(1024*1024), existing.read(1024*1024)
                        if first != second:
                            raise ValueError(f"目标已存在不同内容，保留原文件：{target}")
                        if not first:
                            break
        for info,target in members:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)


def download(url, destination, max_bytes):
    request = urllib.request.Request(url, headers={"User-Agent":"AIC-PuYigai/0.1 (research)"})
    with urllib.request.urlopen(request, timeout=60) as response, Path(destination).open("xb") as output:
        count = 0
        for chunk in iter(lambda: response.read(1024*1024), b""):
            count += len(chunk)
            if count > max_bytes:
                raise ValueError("下载超过预期体积上限")
            output.write(chunk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "var" / "datasets" / "guitarset"))
    parser.add_argument("--archives-only", action="store_true", help="only download verified archives")
    args = parser.parse_args()
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    metadata_file = folder / "record-metadata.json"
    temporary = folder / "record-metadata.part"
    if temporary.exists():
        raise SystemExit(f"存在上次未完成文件，请先检查再移除：{temporary}")
    try:
        download("https://zenodo.org/api/records/3371780", temporary, 10*1024**2)
        metadata = json.loads(temporary.read_text(encoding="utf-8"))
        published_files = {f["key"]: f for f in metadata["files"]}
        for name,expected in ARCHIVES.items():
            if published_files[name]["checksum"] != "md5:" + expected:
                raise ValueError("发布页与已知归档校验不一致，请先核查版本")
        license_info = metadata.get("metadata", {}).get("license")
        if not license_info:
            raise ValueError("官方元数据缺少许可信息，请人工核查后再使用数据")
        temporary.replace(metadata_file)
        print("官方许可元数据：", json.dumps(license_info, ensure_ascii=False), flush=True)
        for name,expected in ARCHIVES.items():
            archive = folder / name
            if archive.exists():
                verify(archive, expected)
            else:
                part = folder / (name + ".part")
                if part.exists():
                    raise ValueError(f"存在未完成下载，请先检查：{part}")
                print("下载", name, flush=True)
                try:
                    download(RECORD + "/files/" + name + "?download=1", part, 3*1024**3)
                    verify(part, expected)
                    part.replace(archive)
                except Exception:
                    if part.exists():
                        part.unlink()
                    raise
            if not args.archives_only:
                extract_verified(archive, folder / name.removesuffix(".zip"), expected)
        print("完成：", folder)
    finally:
        if temporary.exists():
            temporary.unlink()


if __name__ == "__main__":
    main()
