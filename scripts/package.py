"""Create a source-only development bundle, excluding recordings and secrets."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
output = root / "artifacts" / "谱易改-开发包.zip"
output.parent.mkdir(exist_ok=True)
files = [root / name for name in ("README.md", "Start-Windows.cmd", "Dockerfile", "render.yaml", "site_security.py", "jianpu.py", "project_backup.py", ".dockerignore", ".gitignore", "app.py", "notation.py", "practice.py", "alignment.py", "evaluation.py", "independent_review.py", "requirements.lock")]
for directory in ("web", "review_tool", "scripts", "tests", "docs", "third_party", "deploy"):
    files.extend(p for p in (root / directory).rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and p.name != ".env")
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, "AIC/" + str(path.relative_to(root)))
with ZipFile(output) as archive:
    assert archive.testzip() is None
print(output, output.stat().st_size, "bytes")
