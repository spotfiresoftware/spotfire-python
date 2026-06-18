#!/usr/bin/env python3
"""
patch_sbom.py  —  Post-process a Trivy-generated SPDX JSON file to:
  1. Set document metadata (name, namespace, spdxVersion, creationInfo)
  2. Remove synthetic Trivy packages (requirements.txt container, filesystem root)
  3. Remove internal noise packages (e.g. setuptools' my-test-package)
  4. Remove the files[] section and strip annotations/comments from packages
  5. Inject a root package (spotfire-python) with DEPENDS_ON relationships
     to each dependency (Trivy does not generate dependency graphs for pip)
  6. Inject vendored sbdf-c package with a CONTAINS relationship from root
"""

import argparse
import json
from datetime import datetime, timezone

_ROOT_SPDXID = "SPDXRef-Package-spotfire-python"
_STRIP_PKG_FIELDS = {"annotations", "comment"}

# Packages Trivy picks up from setuptools internals — not real deliverable deps
_NOISE_PACKAGE_NAMES = {
    "my-test-package",
    "my_test_package",
}

# Vendored package that pip freeze cannot detect
_VENDORED_SBDF_C = {
    "name": "spotfire-sbdf-c",
    "SPDXID": "SPDXRef-Package-vendored-sbdf-c",
    "versionInfo": "1.0.1",
    "downloadLocation": "https://github.com/spotfiresoftware/spotfire-sbdf-c",
    "filesAnalyzed": False,
    "licenseConcluded": "BSD-3-Clause",
    "licenseDeclared": "BSD-3-Clause",
    "supplier": "Organization:Cloud Software Group, Inc., Spotfire",
    "originator": "Organization:Cloud Software Group, Inc., Spotfire",
    "primaryPackagePurpose": "LIBRARY",
    "copyrightText": "Copyright (c) Cloud Software Group, Inc. All Rights Reserved.",
    "description": "C library for reading and writing files in the Spotfire Binary Data Format (SBDF). Vendored into spotfire-python.",
    "externalRefs": [
        {
            "referenceCategory": "PACKAGE-MANAGER",
            "referenceType": "purl",
            "referenceLocator": "pkg:generic/spotfire/sbdf-c",
        }
    ],
}

# SPDX package purposes that are Trivy synthetic scan-root / container artefacts
_SYNTHETIC_PURPOSES = {"SOURCE", "APPLICATION"}


def _is_synthetic(pkg: dict) -> bool:
    """True for Trivy's scan-root and requirements.txt container packages."""
    if pkg.get("primaryPackagePurpose") not in _SYNTHETIC_PURPOSES:
        return False
    # Only remove if it has no purl (i.e. it's not a real package)
    refs = pkg.get("externalRefs", [])
    return not any(r.get("referenceType") == "purl" for r in refs)


def _is_noise(pkg: dict) -> bool:
    """True for known internal test packages bundled inside setuptools."""
    return pkg.get("name", "").lower().replace("-", "_") in {
        n.replace("-", "_") for n in _NOISE_PACKAGE_NAMES
    }


def _make_root_package(name: str, org: str) -> dict:
    """Build the root package entry from the document name (e.g. 'spotfire-2.5.0')."""
    parts = name.rsplit("-", 1)
    pkg_name = parts[0] if len(parts) == 2 else name
    version = parts[1] if len(parts) == 2 else "NOASSERTION"
    return {
        "SPDXID": _ROOT_SPDXID,
        "name": pkg_name,
        "versionInfo": version,
        "downloadLocation": f"https://pypi.org/project/{pkg_name}/{version}/",
        "filesAnalyzed": False,
        "licenseConcluded": "BSD-3-Clause",
        "licenseDeclared": "BSD-3-Clause",
        "supplier": f"Organization:{org}",
        "primaryPackagePurpose": "LIBRARY",
        "copyrightText": f"Copyright (c) {org.split(',')[0]}. All Rights Reserved.",
        "description": "Package for Building Python Extensions to Spotfire.",
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": f"pkg:pypi/{pkg_name}@{version}",
            }
        ],
    }


def patch(input_path: str, output_path: str,
          name: str, namespace: str, org: str, tool: str) -> None:

    with open(input_path, encoding="utf-8") as f:
        doc = json.load(f)

    # 1. SPDX version
    doc["spdxVersion"] = "SPDX-2.3"

    # 2. Document name
    doc["name"] = name

    # 3. Namespace
    doc["documentNamespace"] = namespace

    # 4. creationInfo
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc.setdefault("creationInfo", {})
    doc["creationInfo"]["created"] = now
    doc["creationInfo"]["creators"] = [
        f"Organization: {org}",
        f"Tool: {tool}",
    ]

    # 5. Document-level notice
    doc["comment"] = (
        "This SBOM was generated at release time. Dependency versions listed "
        "here were resolved during the build and may differ when the package "
        "is installed by end users, as pip resolves versions dynamically based "
        "on the version constraints declared in the package metadata."
    )

    # 5. Filter packages — track removed SPDXIDs so we can fix relationships
    removed_spdxids = set()   # synthetic / noise packages to remove
    kept_packages = []
    for pkg in doc.get("packages", []):
        if _is_synthetic(pkg) or _is_noise(pkg):
            removed_spdxids.add(pkg["SPDXID"])
            continue
        for field in _STRIP_PKG_FIELDS:
            pkg.pop(field, None)
        kept_packages.append(pkg)
    doc["packages"] = kept_packages

    # 6. Remove files[] section (internal test eggs, not deliverables)
    doc.pop("files", None)

    # 7. Build root package and rewrite relationships:
    #    DOCUMENT DESCRIBES root, root DEPENDS_ON each dependency
    root_pkg = _make_root_package(name, org)
    dep_spdxids = set()

    for rel in doc.get("relationships", []):
        src  = rel["spdxElementId"]
        tgt  = rel["relatedSpdxElement"]

        if tgt in removed_spdxids:
            continue
        if src in removed_spdxids:
            dep_spdxids.add(tgt)
            continue
        dep_spdxids.add(tgt)

    kept_pkg_ids = {p["SPDXID"] for p in kept_packages}
    for spdx_id in kept_pkg_ids - dep_spdxids:
        dep_spdxids.add(spdx_id)

    new_rels = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relatedSpdxElement": _ROOT_SPDXID,
            "relationshipType": "DESCRIBES",
        },
    ]
    for spdx_id in sorted(dep_spdxids):
        new_rels.append({
            "spdxElementId": _ROOT_SPDXID,
            "relatedSpdxElement": spdx_id,
            "relationshipType": "DEPENDS_ON",
        })

    # 8. Inject vendored sbdf-c as CONTAINS (compiled into the wheel)
    doc["packages"].append(dict(_VENDORED_SBDF_C))
    new_rels.append({
        "spdxElementId": _ROOT_SPDXID,
        "relatedSpdxElement": _VENDORED_SBDF_C["SPDXID"],
        "relationshipType": "CONTAINS",
    })

    doc["packages"].insert(0, root_pkg)
    doc["relationships"] = new_rels

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Patched SBOM written to {output_path}")
    print(f"  name      : {name}")
    print(f"  namespace : {namespace}")
    print(f"  created   : {now}")
    print(f"  creators  : Organization: {org} | Tool: {tool}")
    print(f"  packages  : {len(kept_packages)} kept, {len(removed_spdxids)} removed")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",     required=True)
    p.add_argument("--output",    required=True)
    p.add_argument("--name",      required=True, help="Clean package name e.g. spotfire-2.5.0")
    p.add_argument("--namespace", required=True)
    p.add_argument("--org",       required=True)
    p.add_argument("--tool",      required=True)
    args = p.parse_args()
    patch(args.input, args.output, args.name, args.namespace, args.org, args.tool)


if __name__ == "__main__":
    main()

