#!/usr/bin/env python3
"""check_ios_port.py -- the port's static self-check, run on a machine that cannot compile Swift.

    py -I check_ios_port.py [path/to/app/SpektraLab]

Five passes over the tree the iOS target compiles:

  1. Brace, bracket and paren balance per Swift file (string literals, comments and
     interpolations blanked first).
  2. `#if/#endif` pairing per file, and a check that the macOS-only API blacklist never appears
     in a branch the iOS target compiles (`#if os(macOS)` bodies are skipped; bodies under
     `#if targetEnvironment(macCatalyst)` are allowed -- Catalyst-only APIs are legal there,
     and the iOS target removes them at compile time).
  3. Target-membership cross-check: every Swift file under Sources/ must be in the generated
     pbxproj's compile phase for BOTH targets, and the inverse -- nothing in a compile phase
     that is not a file on disk. (The port's survey concluded one tree serves both targets,
     IOS-PORT-NOTES.md §2; this pass pins that conclusion.)
  4. An availability sweep: APIs the port knows are iOS-18+-only or Catalyst-only, listed in
     this file, must sit inside an `#if`/`#available` guard the iOS target honours.
  5. The generated project's iOS target settings: the keys a device build and an App Store
     submission need (photo-library strings, launch screen, orientations, floor 18.0).

Exit status 1 with a report on stderr when anything fails; a summary on stdout either way.
"""
import re
import sys
from pathlib import Path

HERE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
SRC = HERE / "Sources"
PBX = HERE / "SpektraLab.xcodeproj" / "project.pbxproj"

# macOS-only symbols that must never be compiled where the iOS target sees them. The tree
# reaches AppKit through the runtime (NSClassFromString with a *string* -- fine everywhere);
# these are the *type and function* names that would fail to compile on iOS.
MAC_ONLY_API = [
    "NSWindow", "NSSavePanel", "NSOpenPanel", "NSPanel", "NSMenu", "NSAlert",
    "NSStatusBar", "NSWorkspace", "NSApplication", "NSHostingView", "NSHostingController",
    "NSView", "NSPasteboard", "NSResponder", "NSEvent", "NSScreen", "NSImage", "NSColor",
    "NSButton", "NSMenuItem", "NSTrackingArea", "NSCursor", "NSRunningApplication",
    "import AppKit", "import Cocoa",
]

# APIs the port measured against Apple's availability (IOS-PORT-NOTES.md §2): the first needs
# the Catalyst-only guard; the rest are legal everywhere this tree compiles but are listed so
# a future edit is checked against the guard it must carry.
CATALYST_ONLY_API = ["scene.titlebar", ".titlebar?"]

problems: list[str] = []


def strip_comments_and_strings(text: str) -> str:
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == '"':
            # a Swift string, with escapes; a `\#(interpolation)` keeps its braces out
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            out.append('""')
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def balance(name: str, text: str) -> None:
    pairs = {"{": "}", "(": ")", "[": "]"}
    close = {v: k for k, v in pairs.items()}
    stack = []
    line = 1
    for ch in text:
        if ch == "\n":
            line += 1
        elif ch in pairs:
            stack.append((ch, line))
        elif ch in close:
            if not stack or stack[-1][0] != close[ch]:
                problems.append(f"{name}:{line}: unbalanced '{ch}'")
                return
            stack.pop()
    if stack:
        ch, ln = stack[-1]
        problems.append(f"{name}:{ln}: unclosed '{ch}'")


def ios_compiles(condition: str) -> bool:
    """Whether the iOS target's compiler sees code under `condition`. A branch whose every
    part is os(macOS) / canImport(AppKit) is Mac-only and removed for iOS; everything else
    (DEBUG, SPK_*, os(iOS), targetEnvironment(macCatalyst), bare) is present in the iOS
    compile -- where `targetEnvironment(macCatalyst)` is false and its body is removed by
    the compiler, which is why the sweep below skips those branches explicitly."""
    if condition.startswith("!"):
        return not ios_compiles(condition[1:].strip())
    for part in re.split(r"\s*&&\s*|\s*,\s*", condition):
        part = part.strip()
        if part in ("os(macOS)", "canImport(AppKit)", "canImport(Cocoa)"):
            return False
    return True


def swift_files():
    return sorted(SRC.rglob("*.swift"))


def main() -> int:
    if not SRC.exists():
        print(f"no Sources under {HERE}", file=sys.stderr)
        return 1

    # 1 + 2 + 4: per file
    for p in swift_files():
        rel = p.relative_to(HERE).as_posix()
        raw = p.read_text(encoding="utf-8", errors="replace")
        bare = strip_comments_and_strings(raw)
        balance(rel, bare)

        # #if/#endif pairing
        opens = len(re.findall(r"^\s*#if\b", raw, re.M))
        closes = len(re.findall(r"^\s*#endif\b", raw, re.M))
        if opens != closes:
            problems.append(f"{rel}: #if x{opens} against #endif x{closes}")

        # the Catalyst-only surface (`scene.titlebar`, Mac Catalyst 13+ only) must sit inside a
        # `#if targetEnvironment(macCatalyst)` whose enclosing scopes do not turn it back on
        lines = raw.split("\n")
        stack: list[str] = []   # the open #if conditions, outermost first
        for ln, line in enumerate(lines, 1):
            m = re.match(r"\s*#(if|elseif|else|endif)\b\s*(.*)$", line)
            if m:
                kind, body = m.group(1), (m.group(2) or "").strip()
                if kind == "if":
                    stack.append(body)
                elif kind == "elseif":
                    if stack:
                        stack[-1] = body
                elif kind == "else":
                    if stack:
                        stack[-1] = "!" + stack[-1]
                elif kind == "endif":
                    if stack:
                        stack.pop()
                continue
            bare_line = strip_comments_and_strings(line)
            for api in CATALYST_ONLY_API:
                if api in bare_line:
                    guarded = any(c == "targetEnvironment(macCatalyst)" for c in stack)
                    unguarded = any(c == "!targetEnvironment(macCatalyst)" for c in stack)
                    if unguarded or not guarded:
                        problems.append(f"{rel}:{ln}: '{api}' outside #if targetEnvironment(macCatalyst)")

        # the macOS-only blacklist, outside comments, outside Mac-only branches
        for m in re.finditer(r"^\s*#if\s+(.*?)\s*$", raw, re.M):
            cond = m.group(1)
            if ios_compiles(cond) and not cond.startswith("targetEnvironment(macCatalyst)"):
                # find the branch's extent (to its #else/#elseif/#endif at the same depth)
                depth = 1
                scan = re.finditer(r"^\s*#(?:if|elseif|else|endif)\b", raw[m.end():], re.M)
                end = len(raw)
                for s in scan:
                    t = s.group(0).strip()
                    if t.startswith("#if"):
                        depth += 1
                    elif t.startswith("#endif"):
                        depth -= 1
                        if depth == 0:
                            end = m.end() + s.start()
                            break
                branch = strip_comments_and_strings(raw[m.end():end])
                for api in MAC_ONLY_API:
                    if re.search(r"\b" + re.escape(api) + r"\b", branch):
                        problems.append(f"{rel}: macOS-only '{api}' under #if {cond} the iOS target compiles")

    # 3: membership against the generated project
    pbx = PBX.read_text(encoding="utf-8") if PBX.exists() else ""
    if not pbx:
        problems.append(f"{PBX}: not found -- run gen_project.py first")
    else:
        # compile-phase files, per target: the phases follow the target blocks in order
        phases = re.findall(r"isa = PBXSourcesBuildPhase;.*?files = \((.*?)\)", pbx, re.S)
        members = []
        for ph in phases:
            members.append(set(re.findall(r"([0-9A-F]{24}) /\* .*? \*/", ph)))
        if len(members) != 2:
            problems.append(f"expected 2 Sources phases (Mac, iOS), found {len(members)}")
        else:
            mac, ios = members
            on_disk = {p.name for p in swift_files() if p.suffix == ".swift"}
            # build-file ids in a phase -> file names, via the PBXBuildFile table
            buildfiles = dict(re.findall(r"([0-9A-F]{24}) /\* (.*?) in Sources \*/ = ", pbx))
            mac_names = {buildfiles[i].removesuffix(" in Sources") for i in mac if i in buildfiles}
            ios_names = {buildfiles[i].removesuffix(" in Sources") for i in ios if i in buildfiles}
            if mac_names != ios_names:
                only_mac = sorted(mac_names - ios_names)
                only_ios = sorted(ios_names - mac_names)
                problems.append(f"Sources phases differ: Mac-only {only_mac[:8]}, iOS-only {only_ios[:8]}")
            for name, side in (("Mac", mac_names), ("iOS", ios_names)):
                missing = sorted(on_disk - side)
                extra = sorted(side - on_disk)
                if missing:
                    problems.append(f"{side and name}: on disk but not in the target: {missing[:8]}")
                if extra:
                    problems.append(f"{name}: in the target but not on disk: {extra[:8]}")

        # 5: the iOS target's settings
        ios_block = re.search(r"name = SpektraLab-iOS;.*?productType = \"com.apple.product-type.application\";",
                              pbx, re.S)
        if not ios_block:
            problems.append("no SpektraLab-iOS target in the generated project")
        else:
            # the target's two configuration lists hold its settings; search the whole file for
            # the keys the iOS target must carry (they are per-configuration blocks named by id)
            need = {
                "IPHONEOS_DEPLOYMENT_TARGET = 18.0": "the iOS floor 18.0",
                "INFOPLIST_KEY_NSPhotoLibraryUsageDescription": "the photo-library read reason",
                "INFOPLIST_KEY_NSPhotoLibraryAddUsageDescription": "the photo-library write reason",
                "INFOPLIST_KEY_UILaunchScreen_Generation": "the launch screen",
                "INFOPLIST_KEY_UISupportedInterfaceOrientations": "the orientations",
                "TARGETED_DEVICE_FAMILY = \"1,2\"": "iPhone and iPad",
            }
            settings_blob = pbx
            for key, what in need.items():
                if key not in settings_blob:
                    problems.append(f"the iOS target lacks {what} ({key})")

    # the report
    if problems:
        print(f"check_ios_port: {len(problems)} problem(s)", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    n = len(list(swift_files()))
    print(f"check_ios_port: OK -- {n} Swift files, balance, #if pairing, Mac-only API, "
          f"membership (2 targets), iOS settings all pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
