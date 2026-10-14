#!/usr/bin/env bash
# The exact build of both packages. The publish workflow and the build check that runs on every push both call this file, so a defect here is found before a tag, not at publication.
# It publishes nothing. Needs python3 (3.9 or newer) with pip, and node with npm.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf dist dist-npm
python3 vendor_tools.py                  # copy the repository's tool modules into the package
python3 -m pip install --quiet build twine
python3 -m build --outdir dist           # the sdist, then the wheel built from it
python3 -m twine check dist/*
python3 vendor_tools.py --npm            # the Python package, the README and the LICENSE into npm/
mkdir -p dist-npm
(cd npm && npm pack --silent --pack-destination ../dist-npm)
ls -l dist dist-npm
python3 - <<'PY'
import glob, tarfile, zipfile
wheels = glob.glob("dist/*.whl"); sdists = glob.glob("dist/*.tar.gz"); tgz = glob.glob("dist-npm/*.tgz")
assert len(wheels) == 1 and len(sdists) == 1 and len(tgz) == 1, (wheels, sdists, tgz)
w = zipfile.ZipFile(wheels[0]).namelist()
for need in ("authority_risk_mcp/store.py", "authority_risk_mcp/ed25519.py", "authority_risk_mcp/server.py", "authority_risk_mcp/_vendor/agent_tools.py", "authority_risk_mcp/_vendor/evaluate_rules.py"):
    assert need in w, ("the wheel lacks " + need, w)
assert any(n.endswith("entry_points.txt") for n in w)
s = tarfile.open(sdists[0]).getnames()
assert any(n.endswith("authority_risk_mcp/_vendor/agent_tools.py") for n in s), ("the sdist lacks the vendored modules", s)
t = tarfile.open(tgz[0]).getnames()
for need in ("package/bin/authority-risk-mcp.js", "package/package.json", "package/python/authority_risk_mcp/store.py", "package/python/authority_risk_mcp/_vendor/agent_tools.py", "package/README.md", "package/LICENSE"):
    assert need in t, ("the npm tarball lacks " + need, t)
print("packages built: 1 wheel, 1 sdist, 1 npm tarball, all with the modules they need")
PY
