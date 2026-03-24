#!/usr/bin/env python3
"""
patch_sbom.py  —  Post-process a Trivy-generated SPDX JSON file to:
  1. Set name               to the package name (not the scanned folder name)
  2. Set documentNamespace  to the required pattern
  3. Set creationInfo.creators  (Organization + Tool line)
  4. Set creationInfo.created   (current UTC timestamp)
  5. Set spdxVersion            to SPDX-2.3
  6. Remove any annotations / comments Trivy adds to packages

Usage:
    python patch_sbom.py \\
        --input  trivy_raw.spdx.json \\
        --output spotfire.sbom.spdx.json \\
        --name    "spotfire-2.5.0" \\
        --namespace "https://spotfire.com/spdx/spotfire-2.5.0/2026-03-24T12:00:00Z" \\
        --org     "Cloud Software Group, Inc., Spotfire" \\
        --tool    "trivy-0.69.3"
"""

import argparse
import json
from datetime import datetime, timezone

_STRIP_PKG_FIELDS = {"annotations", "comment"}


def patch(input_path: str, output_path: str,
          name: str, namespace: str, org: str, tool: str) -> None:

    with open(input_path, encoding="utf-8") as f:
        doc = json.load(f)

    # 1. SPDX version
    doc["spdxVersion"] = "SPDX-2.3"

    # 2. Document name — replace Trivy's folder name with the real package name
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

    # 5. Strip Trivy annotations / comments from every package
    for pkg in doc.get("packages", []):
        for field in _STRIP_PKG_FIELDS:
            pkg.pop(field, None)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Patched SBOM written to {output_path}")
    print(f"  name      : {name}")
    print(f"  namespace : {namespace}")
    print(f"  created   : {now}")
    print(f"  creators  : Organization: {org} | Tool: {tool}")
    print(f"  packages  : {len(doc.get('packages', []))}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",     required=True)
    p.add_argument("--output",    required=True)
    p.add_argument("--name",      required=True,  help="SPDX document name (package name + version)")
    p.add_argument("--namespace", required=True)
    p.add_argument("--org",       required=True)
    p.add_argument("--tool",      required=True)
    args = p.parse_args()
    patch(args.input, args.output, args.name, args.namespace, args.org, args.tool)


if __name__ == "__main__":
    main()

