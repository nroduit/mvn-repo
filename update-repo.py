#!/usr/bin/env python3
"""Regenerate maven-metadata.xml and .sha1/.md5 checksums for this flat Maven repo.

Replaces the old mvn-metadata-gen.pl + mvn-sha1md5-gen.pl pair. Self-contained:
Python 3 standard library only (no Perl, no XML::Simple, no GNU coreutils), so it
runs identically on macOS and Linux. Operates on the directory that contains this
script, so it works regardless of the current working directory.

Usage:
    python3 update-repo.py            # apply changes
    python3 update-repo.py --dry-run  # show what would change, write nothing

What it does, in a single pass:
  1. For every artifact (groupId:artifactId) it finds all version directories
     (each holding a *.pom) and writes <artifact>/maven-metadata.xml.
  2. Writes a .sha1 and .md5 next to every artifact file (.pom and every binary,
     including .dylib) and next to each maven-metadata.xml.

To keep git diffs minimal, files are only rewritten when their content actually
changes, and maven-metadata.xml keeps its previous <lastUpdated> when the set of
versions is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# Files that get .sha1/.md5 siblings. Anything not in here (README, checksums,
# .DS_Store, ...) is ignored.
ARTIFACT_EXTS = {
    ".pom", ".jar", ".war", ".zip",
    ".dll", ".so", ".dylib", ".jnilib",
}
CHECKSUMS = {"sha1": hashlib.sha1, "md5": hashlib.md5}

changed = 0  # number of files written (or that would be written)


def write_if_changed(path: str, content: bytes, dry_run: bool) -> bool:
    """Write content only when it differs from what's on disk. Returns True if changed."""
    global changed
    try:
        with open(path, "rb") as f:
            if f.read() == content:
                return False
    except FileNotFoundError:
        pass
    changed += 1
    rel = os.path.relpath(path, REPO_ROOT)
    print(f"  {'would update' if dry_run else 'updated'}: {rel}")
    if not dry_run:
        with open(path, "wb") as f:
            f.write(content)
    return True


def write_checksums(path: str, dry_run: bool) -> None:
    """Write <path>.sha1 and <path>.md5 (40/32 hex chars, no newline — Maven format)."""
    with open(path, "rb") as f:
        data = f.read()
    for ext, algo in CHECKSUMS.items():
        digest = algo(data).hexdigest().encode("ascii")
        write_if_changed(f"{path}.{ext}", digest, dry_run)


# --- version ordering (Maven-ish, good enough to pick release/latest) -------

def version_key(version: str):
    """Sort key: split into numeric and alpha tokens; numbers compare as ints."""
    key = []
    for tok in re.findall(r"\d+|[a-zA-Z]+", version.lower()):
        key.append((1, int(tok)) if tok.isdigit() else (0, tok))
    return key


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]  # strip XML namespace


def pom_ga(pom_path: str):
    """Return (groupId, artifactId), falling back to <parent> for groupId."""
    root = ET.parse(pom_path).getroot()

    def child_text(parent, name):
        for c in parent:
            if _local(c.tag) == name:
                return (c.text or "").strip()
        return ""

    group = child_text(root, "groupId")
    artifact = child_text(root, "artifactId")
    if not group:
        for c in root:
            if _local(c.tag) == "parent":
                group = child_text(c, "groupId")
                break
    return group, artifact


# --- maven-metadata.xml -----------------------------------------------------

def existing_last_updated(meta_path: str):
    """Return (lastUpdated, versions) from an existing metadata file, or (None, None)."""
    try:
        root = ET.parse(meta_path).getroot()
    except (FileNotFoundError, ET.ParseError):
        return None, None
    versioning = root.find("versioning")
    if versioning is None:
        return None, None
    ts = versioning.findtext("lastUpdated")
    versions = [v.text for v in versioning.findall("versions/version")]
    return ts, versions


def build_metadata(group: str, artifact: str, versions: list[str], last_updated: str) -> bytes:
    release = max((v for v in versions if "snapshot" not in v.lower()),
                  key=version_key, default=versions[-1])
    lines = [
        '<?xml version="1.0"?>',
        "<metadata>",
        f"  <groupId>{group}</groupId>",
        f"  <artifactId>{artifact}</artifactId>",
        f"  <version>{release}</version>",
        "  <versioning>",
        f"    <release>{release}</release>",
        "    <versions>",
    ]
    lines += [f"      <version>{v}</version>" for v in versions]
    lines += [
        "    </versions>",
        f"    <lastUpdated>{last_updated}</lastUpdated>",
        "  </versioning>",
        "</metadata>",
    ]
    return "\n".join(lines).encode("utf-8")


# --- per-version SNAPSHOT metadata (non-unique / "localCopy" layout) ---------

def snapshot_last_updated(meta_path: str):
    """Return the <lastUpdated> of an existing snapshot metadata file, or None."""
    try:
        root = ET.parse(meta_path).getroot()
    except (FileNotFoundError, ET.ParseError):
        return None
    return root.findtext("versioning/lastUpdated")


def artifacts_changed(version_dir: str) -> bool:
    """True if any artifact file in the dir differs from its stored .sha1 (i.e. rebuilt).

    Read before the checksum pass overwrites the .sha1 files, so it detects a jar
    that was replaced since the last run -> the snapshot's lastUpdated must advance.
    """
    for name in os.listdir(version_dir):
        if os.path.splitext(name)[1].lower() not in ARTIFACT_EXTS:
            continue
        path = os.path.join(version_dir, name)
        try:
            with open(f"{path}.sha1") as f:
                stored = f.read().strip()
        except FileNotFoundError:
            return True
        with open(path, "rb") as f:
            if hashlib.sha1(f.read()).hexdigest() != stored:
                return True
    return False


def build_snapshot_metadata(group: str, artifact: str, version: str, last_updated: str) -> bytes:
    lines = [
        '<?xml version="1.0"?>',
        '<metadata modelVersion="1.1.0">',
        f"  <groupId>{group}</groupId>",
        f"  <artifactId>{artifact}</artifactId>",
        f"  <version>{version}</version>",
        "  <versioning>",
        "    <snapshot>",
        "      <localCopy>true</localCopy>",
        "    </snapshot>",
        f"    <lastUpdated>{last_updated}</lastUpdated>",
        "  </versioning>",
        "</metadata>",
    ]
    return "\n".join(lines).encode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="show what would change without writing anything")
    args = ap.parse_args()
    dry = args.dry_run

    # 1. Collect versions per artifact directory (parent of each version dir).
    artifacts: dict[str, dict] = {}
    for dirpath, _dirs, files in os.walk(REPO_ROOT):
        for name in files:
            if not name.endswith(".pom"):
                continue
            pom = os.path.join(dirpath, name)
            artifact_dir = os.path.dirname(dirpath)
            version = os.path.basename(dirpath)
            entry = artifacts.setdefault(artifact_dir, {"ga": None, "versions": set()})
            entry["versions"].add(version)
            if entry["ga"] is None:
                entry["ga"] = pom_ga(pom)

    # 2. Write maven-metadata.xml for each artifact.
    now = time.strftime("%Y%m%d%H%M%S", time.localtime())
    print("== maven-metadata.xml ==")
    for artifact_dir, entry in sorted(artifacts.items()):
        group, artifact = entry["ga"]
        if not group or not artifact:
            print(f"  SKIP (no groupId/artifactId): {os.path.relpath(artifact_dir, REPO_ROOT)}")
            continue
        versions = sorted(entry["versions"], key=version_key)
        meta_path = os.path.join(artifact_dir, "maven-metadata.xml")
        old_ts, old_versions = existing_last_updated(meta_path)
        # Keep the old timestamp when the version set is unchanged -> stable diffs.
        ts = old_ts if (old_ts and old_versions == versions) else now
        write_if_changed(meta_path, build_metadata(group, artifact, versions, ts), dry)

    # 2b. Per-version maven-metadata.xml for non-unique SNAPSHOTs, so Maven resolves
    #     them cleanly. lastUpdated advances only when the artifact was rebuilt, which
    #     is the signal that makes consumers re-download a daily-built snapshot.
    print("== snapshot metadata ==")
    for artifact_dir, entry in sorted(artifacts.items()):
        group, artifact = entry["ga"]
        if not group or not artifact:
            continue
        for version in sorted(entry["versions"], key=version_key):
            if "snapshot" not in version.lower():
                continue
            meta_path = os.path.join(artifact_dir, version, "maven-metadata.xml")
            old_ts = snapshot_last_updated(meta_path)
            ts = old_ts if (old_ts and not artifacts_changed(os.path.dirname(meta_path))) else now
            write_if_changed(meta_path, build_snapshot_metadata(group, artifact, version, ts), dry)

    # 3. Checksums for every artifact file and every maven-metadata.xml.
    print("== checksums ==")
    for dirpath, _dirs, files in os.walk(REPO_ROOT):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in ARTIFACT_EXTS or name == "maven-metadata.xml":
                write_checksums(os.path.join(dirpath, name), dry)

    print(f"\n{'Would update' if dry else 'Updated'} {changed} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())