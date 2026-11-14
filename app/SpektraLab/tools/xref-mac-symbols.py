#!/usr/bin/env python3
"""Find which files outside Sources/Mac/ reference top-level symbols defined in Sources/Mac/.
Top-level = declaration starts at column 0 (Swift requires top-level decls at col 0)."""
import re, sys
from pathlib import Path

HERE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
SRC = HERE / "Sources"

type_re = re.compile(
    r"^(?:@MainActor\s+|@objc\s+|@Observable\s+|@retroactive\s+\S+\s+|final\s+|open\s+|public\s+|private\s+|internal\s+|indirect\s+)*"
    r"(class|struct|enum|protocol|typealias)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
func_re = re.compile(
    r"^(?:@MainActor\s+|@objc\s+|@discardableResult\s+|public\s+|private\s+|internal\s+|final\s+|static\s+)*"
    r"(func|var|let)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)

mac_defs = {}
for p in sorted((SRC / "Mac").rglob("*.swift")):
    text = p.read_text(encoding="utf-8", errors="replace")
    rel = p.relative_to(SRC).as_posix()
    for m in type_re.finditer(text):
        mac_defs.setdefault(m.group(2), set()).add(rel)
    for m in func_re.finditer(text):
        mac_defs.setdefault(m.group(2), set()).add(rel)

hits = []
for p in sorted(SRC.rglob("*.swift")):
    rel = p.relative_to(SRC).as_posix()
    if rel.startswith("Mac/"):
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    text_nc = re.sub(r"//[^\n]*", "", text)
    text_nc = re.sub(r"/\*.*?\*/", "", text_nc, flags=re.S)
    found = sorted({n for n in mac_defs if re.search(r"\b" + re.escape(n) + r"\b", text_nc)})
    if found:
        hits.append((rel, found))

for rel, found in sorted(hits):
    print(f"{rel}:")
    for n in found:
        files = sorted(mac_defs[n])
        print(f"    {n}  <- {', '.join(files[:3])}")
print(f"\n({len(hits)} files outside Sources/Mac reference Mac symbols)")
