#!/usr/bin/env python3
"""
patch_sbom.py  —  Post-process a Trivy-generated SPDX JSON file to:
  1. Set name               to the package name (not the scanned folder name)
  2. Set documentNamespace  to the required pattern
  3. Set creationInfo.creators  (Organization + Tool line)
  4. Set creationInfo.created   (current UTC timestamp)
  5. Set spdxVersion            to SPDX-2.3
  6. Remove synthetic Trivy APPLICATION package (requirements.txt container)
  7. Remove synthetic Trivy filesystem/source root packages
  8. Remove internal test/noise packages (e.g. setuptools' my-test-package)
  9. Remove the files[] section (internal test eggs, not real deliverables)
  10. Promote relationships: replace the removed container's SPDXID with
      SPDXRef-DOCUMENT so each real package becomes DESCRIBED BY the document
  11. Remove annotations / comments Trivy adds to packages
"""

import argparse
import json
from datetime import datetime, timezone

_STRIP_PKG_FIELDS = {"annotations", "comment"}

# Packages Trivy picks up from setuptools internals — not real deliverable deps
_NOISE_PACKAGE_NAMES = {
    "my-test-package",
    "my_test_package",
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

    # 7. Rewrite relationships:
    #    - Drop any rel whose *target* was removed
    #    - Replace the *source* of CONTAINS rels that came from a removed
    #      synthetic container (requirements.txt / filesystem root) with
    #      SPDXRef-DOCUMENT, and change type to DESCRIBES
    kept_rels = []
    seen_describes = set()   # avoid duplicate DESCRIBES entries

    for rel in doc.get("relationships", []):
        src  = rel["spdxElementId"]
        tgt  = rel["relatedSpdxElement"]
        kind = rel["relationshipType"]

        # Drop if the target was removed
        if tgt in removed_spdxids:
            continue

        # Promote: if the source was a removed synthetic container,
        # rewrite as SPDXRef-DOCUMENT DESCRIBES <package>
        if src in removed_spdxids:
            if kind == "CONTAINS":
                key = ("SPDXRef-DOCUMENT", tgt)
                if key not in seen_describes:
                    kept_rels.append({
                        "spdxElementId": "SPDXRef-DOCUMENT",
                        "relatedSpdxElement": tgt,
                        "relationshipType": "DESCRIBES",
                    })
                    seen_describes.add(key)
            continue   # drop the original rel with the removed source

        kept_rels.append(rel)

    # Ensure every kept package has at least a DESCRIBES from the document
    kept_pkg_ids = {p["SPDXID"] for p in kept_packages}
    described = {r["relatedSpdxElement"]
                 for r in kept_rels if r["relationshipType"] == "DESCRIBES"
                 and r["spdxElementId"] == "SPDXRef-DOCUMENT"}
    for spdx_id in kept_pkg_ids - described:
        kept_rels.append({
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relatedSpdxElement": spdx_id,
            "relationshipType": "DESCRIBES",
        })

    doc["relationships"] = kept_rels

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

