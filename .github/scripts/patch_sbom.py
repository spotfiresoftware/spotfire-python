#!/usr/bin/env python3
"""
patch_sbom.py  —  Post-process a Trivy-generated SPDX JSON file to:
  1. Set name               to the package name (not the wheel filename)
  2. Set documentNamespace  to the required pattern
  3. Set creationInfo.creators  (Organization + Tool line)
  4. Set creationInfo.created   (current UTC timestamp)
  5. Set spdxVersion            to SPDX-2.3
  6. Remove synthetic Trivy filesystem/source root packages
  7. Remove internal test/noise packages (e.g. setuptools' my-test-package)
  8. Remove the files[] section (internal test eggs, not real deliverables)
  9. Remove annotations / comments Trivy adds to packages
"""

import argparse
import json
import re
from datetime import datetime, timezone

_STRIP_PKG_FIELDS = {"annotations", "comment"}

# Packages Trivy picks up from setuptools internals — not real deliverable deps
_NOISE_PACKAGE_NAMES = {
    "my-test-package",
    "my_test_package",
}

# SPDX package purposes that are Trivy synthetic scan-root artefacts
_SYNTHETIC_PURPOSES = {"SOURCE"}


def _is_synthetic(pkg: dict) -> bool:
    """True for Trivy's filesystem scan-root package (not a real dependency)."""
    if pkg.get("primaryPackagePurpose") in _SYNTHETIC_PURPOSES:
        # Must also have no purl to be sure it's the scan root
        refs = pkg.get("externalRefs", [])
        if not any(r.get("referenceType") == "purl" for r in refs):
            return True
    return False


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

    # 2. Document name — clean package name, not wheel filename
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

    # 5. Filter packages — remove synthetic scan-root + noise packages
    removed_spdxids = set()
    kept_packages = []
    for pkg in doc.get("packages", []):
        if _is_synthetic(pkg) or _is_noise(pkg):
            removed_spdxids.add(pkg.get("SPDXID"))
            continue
        # Strip Trivy-added fields
        for field in _STRIP_PKG_FIELDS:
            pkg.pop(field, None)
        kept_packages.append(pkg)
    doc["packages"] = kept_packages

    # 6. Remove files[] section entirely (internal test eggs, not deliverables)
    doc.pop("files", None)

    # 7. Remove relationships that reference removed packages or files
    kept_rels = []
    for rel in doc.get("relationships", []):
        if (rel.get("spdxElementId") in removed_spdxids or
                rel.get("relatedSpdxElement") in removed_spdxids):
            continue
        # Also drop DESCRIBES relationships pointing at the old scan-root
        kept_rels.append(rel)
    doc["relationships"] = kept_rels

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Patched SBOM written to {output_path}")
    print(f"  name      : {name}")
    print(f"  namespace : {namespace}")
    print(f"  created   : {now}")
    print(f"  creators  : Organization: {org} | Tool: {tool}")
    print(f"  packages  : {len(doc.get('packages', []))} kept, {len(removed_spdxids)} removed")
    print(f"  files     : removed (internal test artefacts)")


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

