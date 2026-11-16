#!/usr/bin/env python3
"""Refuse a repository layout that has drifted from the one written in tools/structure.json.

Reusable: the rules live in the JSON file, this script only applies them. Generic copy for the RealSpap public repositories: incident rules are skipped when incident_parent is null; README ceiling and dash check added.
Run from anywhere:   python3 tools/check_structure.py [--root DIR] [--config FILE]
Exit code 0 = layout accepted; 1 = at least one violation (each one is printed).

The files checked are the ones git lists (tracked, plus untracked and not ignored); outside a git checkout
the whole tree is read. Rules, all read from the config:
  1. root_files / root_dirs: nothing else may sit at the root.
  2. max_root_entries: the count of visible root entries (no leading dot) stays under a ceiling,
     so the allowlist cannot grow quietly.
  3. incident_parent + incident_markers: a file named like an incident marker anywhere outside
     <incident_parent>/<slug>/ is refused (an incident folder at the root, or one level too deep).
  4. incident_parent may hold only folders, each with a README.md.
  5. forbidden_names: no file or folder with one of these names at any depth (fnmatch, case-insensitive).
  6. allowed_paths: every file below the root must match one of these patterns, whatever its name.
     In a pattern "*" stands for characters inside ONE path segment, "**" for one or more whole segments,
     and neither matches a name that starts with a dot (a hidden file or folder is refused unless a
     pattern spells it out).
  7. A symbolic link is refused anywhere.
  8. legacy_redirects: old paths kept at the root so a published link still lands somewhere. A folder must
     hold only a short README.md that links to ../<legacy_dir_target>/<name>/; a file must be short and name
     <legacy_file_target>/<name>. Their number is capped (max_legacy_redirects) and they do not count
     towards max_root_entries.
"""
import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path


def load_config(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def glob_re(pattern):
    """Segment-aware glob. See rule 6 in the module docstring."""
    segs = pattern.split("/")
    out = []
    for i, seg in enumerate(segs):
        if seg == "**":
            out.append(r"(?!\.)[^/]+(?:/(?!\.)[^/]+)*" if i == len(segs) - 1 else r"(?:(?!\.)[^/]+/)+")
            if i != len(segs) - 1:
                out[-1] = out[-1][:-1] + r"/"  # keep the separator inside the group
            continue
        body = "".join("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in seg)
        out.append(("" if seg.startswith(".") else r"(?!\.)") + body)
    rx = ""
    for i, piece in enumerate(out):
        rx += piece
        if i < len(out) - 1 and not piece.endswith("/"):
            rx += "/"
    return re.compile("^" + rx + "$")


def listed_files(root):
    """Relative paths of the files and links the repository holds: git's list when there is one, else the tree."""
    root = Path(root)
    if (root / ".git").exists():
        r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True)
        if r.returncode == 0:
            return sorted({Path(p) for p in r.stdout.decode("utf-8").split("\0") if p})
    return sorted(p.relative_to(root) for p in root.rglob("*")
                  if (p.is_file() or p.is_symlink()) and ".git" not in p.relative_to(root).parts)


def check(root, cfg):
    root = Path(root)
    files = listed_files(root)
    errors = []
    legacy = set(cfg.get("legacy_redirects", []))
    allowed = set(cfg["root_files"]) | set(cfg["root_dirs"])
    parent = cfg.get("incident_parent")          # null : pas de dossier d'incidents (profil, site, showcases)
    markers = set(cfg.get("incident_markers", [])) if parent else set()
    patterns = [glob_re(p) for p in cfg.get("allowed_paths", [])]

    # 1 and 2: the root
    tops = {}
    for rel in files:
        tops.setdefault(rel.parts[0], []).append(rel)
    visible = 0
    for name in sorted(tops):
        if name in legacy:
            continue
        if name not in allowed:
            kind = "file" if len(tops[name]) == 1 and len(tops[name][0].parts) == 1 else "folder"
            errors.append(f"unexpected {kind} at the root: {name}")
        elif not name.startswith("."):
            visible += 1
    if visible > cfg["max_root_entries"]:
        errors.append(f"{visible} visible entries at the root, the ceiling is {cfg['max_root_entries']}")

    for rel in files:
        if rel.parts[0] in legacy:
            continue
        posix = rel.as_posix()
        # 7: links
        if (root / rel).is_symlink():
            errors.append(f"symbolic link: {posix}")
        # 5: names
        hit = next((part for part in rel.parts if any(fnmatch.fnmatch(part.lower(), pat.lower()) for pat in cfg["forbidden_names"])), None)
        if hit:
            errors.append(f"forbidden name '{hit}' in {posix}")
        # 3: incident files in the wrong place
        if parent and rel.name in markers and (rel.parts[0] != parent or len(rel.parts) != 3):
            errors.append(f"incident file {posix} is outside {parent}/<slug>/")
        # 6: the written layout
        if patterns and len(rel.parts) > 1 and not any(p.match(posix) for p in patterns):
            errors.append(f"file outside the layout: {posix}")

    # 4: the incident parent
    under = [rel for rel in files if parent and rel.parts[0] == parent]
    if parent and not under:
        errors.append(f"missing folder {parent}/")
    for name in sorted({rel.parts[1] for rel in under}):
        mine = [rel for rel in under if rel.parts[1] == name]
        if len(mine[0].parts) == 2 and len(mine) == 1:
            errors.append(f"{parent}/ holds a loose file: {name}")
        elif Path(parent, name, "README.md") not in mine:
            errors.append(f"{parent}/{name}/ has no README.md")

    # 9: the README stays within its line ceiling and holds no em dash or en dash
    readme = root / "README.md"
    limit_readme = cfg.get("readme_max_lines")
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        if limit_readme and len(text.splitlines()) > limit_readme:
            errors.append(f"README.md has {len(text.splitlines())} lines, the ceiling is {limit_readme}")
        if "\u2014" in text or "\u2013" in text:
            errors.append("README.md holds an em dash or an en dash")
    elif cfg.get("readme_required", True):
        errors.append("README.md is missing")

    # 8: legacy redirects
    if len(legacy) > cfg.get("max_legacy_redirects", 0):
        errors.append(f"{len(legacy)} legacy redirects listed, the cap is {cfg.get('max_legacy_redirects', 0)}")
    for name in sorted(n for n in legacy if n in tops):
        mine = tops[name]
        if len(mine) == 1 and len(mine[0].parts) == 1:
            target = f"{cfg.get('legacy_file_target', 'tools')}/{name}"
            text, where, limit = (root / name).read_text(encoding="utf-8"), name, cfg.get("legacy_file_max_lines", 8)
            ok = target in text
        else:
            if [m.as_posix() for m in mine] != [f"{name}/README.md"]:
                errors.append(f"legacy redirect {name} must hold only a README.md, found {sorted(m.as_posix() for m in mine)}")
                continue
            target = f"{cfg.get('legacy_dir_target', parent)}/{name}"
            text, where, limit = (root / name / "README.md").read_text(encoding="utf-8"), f"{name}/README.md", cfg.get("legacy_max_lines", 8)
            ok = f"(../{target}/)" in text
            target = f"../{target}/"
        if len(text.splitlines()) > limit or not ok:
            errors.append(f"legacy redirect {where} must be short and name {target}")
    return errors


def main(argv=None):
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(here.parent))
    ap.add_argument("--config", default=str(here / "structure.json"))
    a = ap.parse_args(argv)
    errors = check(a.root, load_config(a.config))
    for e in errors:
        print(f"STRUCTURE: {e}", file=sys.stderr)
    if errors:
        print(f"Structure check FAILED: {len(errors)} violation(s).", file=sys.stderr)
        return 1
    print("Structure check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
