#!/usr/bin/env python3
"""Example of Authority Levels v0.1: the R-1 measurement (mesure_aave_niveaux.py, unchanged) pointed at two contracts of the Aave V3 Ethereum deployment instead of the reserves:
the PoolAddressesProvider (owner = who can change the Pool's code) and its ACLManager (holders of the roles, among them the emergency admin = who can pause the Pool).
Nothing of the script is modified: only `reserves()` and `symbol()` are replaced here, and the pass keeps its two nodes, its witnesses before and after, its refresh of the multisig thresholds and its NOT READ list.
Usage: python3 exemple_niveaux_13_11.py BLOCK HASHES OUT_PREFIX [node1=url,node2=url]"""
import importlib.util, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("r1", os.path.join(HERE, "mesure_aave_niveaux.py")); r1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r1)
PROVIDER = "0x2f39d218133afab8f2b819b1066c7e434ad94e9e"   # Pool.ADDRESSES_PROVIDER(), read on two nodes the same evening

LABELS = {PROVIDER: "PoolAddressesProvider (Aave V3 Ethereum)"}
if len(sys.argv) < 4:
    sys.exit(__doc__)
block, hashes, out = sys.argv[1], sys.argv[2], sys.argv[3]
nodes = sys.argv[4] if len(sys.argv) > 4 else None
ACL = os.environ["ACL_MANAGER"].lower()
LABELS[ACL] = "ACLManager (Aave V3 Ethereum)"
r1.reserves = lambda: [PROVIDER, ACL]
r1.symbol = lambda a: LABELS.get(a.lower(), a)
r1.EXTRA = []
sys.argv = ["mesure_aave_niveaux.py", "--block", block, "--hashes", hashes, "--limit", "2", "--no-extra", "--out", out] + (["--nodes", nodes] if nodes else [])
r1.main()
