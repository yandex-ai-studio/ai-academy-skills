#!/usr/bin/env python3
"""Render PPTX slides to PNG with LibreOffice and Poppler."""
from __future__ import annotations
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Conversion failed: {result.stdout}\n{result.stderr}")


def render(deck: Path, output_dir: Path, dpi: int = 120) -> list[Path]:
    office = shutil.which("soffice") or shutil.which("libreoffice")
    poppler = shutil.which("pdftoppm") or shutil.which("pdftocairo")
    if not office or not poppler:
        raise RuntimeError("Rendering requires LibreOffice and Poppler; PPTX generation works without them.")
    if not 72 <= dpi <= 300:
        raise ValueError("dpi must be between 72 and 300")
    deck = deck.resolve(strict=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="presentation-render-") as tmp:
        directory = Path(tmp)
        profile = (directory / "office-profile").as_uri()
        _run([office, f"-env:UserInstallation={profile}", "--headless", "--convert-to",
              "pdf", "--outdir", str(directory), str(deck)])
        pdf = directory / f"{deck.stem}.pdf"
        if not pdf.is_file():
            raise RuntimeError("Conversion produced no PDF")
        _run([poppler, "-png", "-r", str(dpi), str(pdf), str(directory / "slide")])
        images = sorted(directory.glob("slide-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        if not images:
            raise RuntimeError("Conversion produced no slide images")
        # Only files from this conversion are returned, including for reused directories.
        paths = []
        for index, image in enumerate(images, 1):
            destination = output_dir / f"slide-{index:03d}.png"
            shutil.copyfile(image, destination)
            paths.append(destination.resolve())
        return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--contact-sheet", action="store_true")
    args = parser.parse_args()
    try:
        paths = render(args.deck, args.output_dir, args.dpi)
        if args.contact_sheet:
            from helpers import create_contact_sheet
            print(create_contact_sheet(paths, args.output_dir / "contact-sheet.png", columns=2, thumb_width=720))
        print(f"Rendered {len(paths)} slides")
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
