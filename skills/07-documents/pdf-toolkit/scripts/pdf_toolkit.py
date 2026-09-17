#!/usr/bin/env python3
"""pdf-toolkit: extract / merge / split PDF (offline, bundled pypdf)."""

import argparse
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "assets" / "vendor"
if VENDOR.is_dir():
    sys.path.insert(0, str(VENDOR))

_here = Path(__file__).resolve().parent
for _shared in (_here / "_shared", _here.parent.parent / "_shared", _here.parent.parent.parent / "_shared"):
    if (_shared / "manifest.py").is_file():
        sys.path.insert(0, str(_shared))
        break
from manifest import add_manifest_args, artifact, default_manifest_path, write_manifest  # noqa: E402

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None


def op_extract(pdf_path: Path, out_txt: Path) -> None:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    out_txt.write_text("\n\n--- page break ---\n\n".join(parts), encoding="utf-8")


def op_merge(inputs: list[Path], out_pdf: Path) -> None:
    writer = PdfWriter()
    for path in inputs:
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
    with out_pdf.open("wb") as f:
        writer.write(f)


def op_split(pdf_path: Path, out_dir: Path) -> list[Path]:
    reader = PdfReader(str(pdf_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for i, page in enumerate(reader.pages, 1):
        writer = PdfWriter()
        writer.add_page(page)
        part = out_dir / f"{pdf_path.stem}_page_{i}.pdf"
        with part.open("wb") as f:
            writer.write(f)
        created.append(part)
    return created


def main():
    parser = argparse.ArgumentParser(description="PDF toolkit (extract/merge/split).")
    parser.add_argument("--op", choices=["extract", "merge", "split"], required=True)
    parser.add_argument("--input", nargs="+", required=True, help="Входные PDF")
    parser.add_argument("--out", help="Выходной файл (extract/merge)")
    parser.add_argument("--out-dir", default="split_pages", help="Папка для split")
    add_manifest_args(parser)
    args = parser.parse_args()

    if PdfReader is None:
        print("pypdf не найден. Положите pypdf в assets/vendor/ (см. README скилла).")
        sys.exit(1)

    inputs = [Path(p) for p in args.input]
    outputs = []

    if args.op == "extract":
        out = Path(args.out or inputs[0].with_suffix(".txt"))
        op_extract(inputs[0], out)
        outputs.append(artifact(out, "text", "data"))
    elif args.op == "merge":
        out = Path(args.out or "merged.pdf")
        op_merge(inputs, out)
        outputs.append(artifact(out, "pdf", "data"))
    else:
        created = op_split(inputs[0], Path(args.out_dir))
        outputs.extend(artifact(p, "pdf", "data") for p in created)

    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(Path(args.out or "pdf.manifest.json"))
    write_manifest(
        manifest_path,
        skill="pdf-toolkit",
        status="ok",
        inputs=[artifact(p, "pdf", "data") for p in inputs],
        outputs=outputs,
        metrics={"operation": args.op, "files_out": len(outputs)},
        suggested_next=["contract-review", "pii-redactor"],
    )
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
