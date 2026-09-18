"""Import a local company PPTX and build the persistent vector index."""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import TEMPLATE, DATA
from backend.catalog import build_index

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument(
        "--lexical",
        action="store_true",
        help="Use local lexical vectors instead of Ollama semantic embeddings",
    )
    args = parser.parse_args()
    if args.template:
        if not args.template.is_file() or args.template.suffix.lower() != ".pptx":
            parser.error("--template must point to an existing PPTX file")
        if args.template.resolve() != TEMPLATE.resolve():
            shutil.copy2(args.template, TEMPLATE)
    if args.pdf and args.pdf.resolve() != (DATA / "kaartech-guide.pdf").resolve():
        shutil.copy2(args.pdf, DATA / "kaartech-guide.pdf")
    print(build_index(semantic=not args.lexical))
