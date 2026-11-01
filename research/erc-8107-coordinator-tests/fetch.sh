#!/bin/bash
# Downloads the three reference files of ERC-8107 at the pinned commit of ethereum/ERCs and checks their sha256. Nothing else is fetched.
set -eu
cd "$(dirname "$0")"
C=6b7a48ffa791e30ceee94d869b5eae9521fe158f; B=https://raw.githubusercontent.com/ethereum/ERCs/$C/assets/erc-8107
mkdir -p ercs/contracts ercs/tests/continuity
curl -sSf -o ercs/contracts/TrustRegistry.sol $B/contracts/TrustRegistry.sol
curl -sSf -o ercs/contracts/ITrustRegistry.sol $B/contracts/ITrustRegistry.sol
curl -sSf -o ercs/tests/continuity/RegistrationBoundary.sol $B/tests/continuity/RegistrationBoundary.sol
shasum -a 256 -c <<SUMS
844dff3ec88729729f5cb99e16fa55a01859866a5955a855a4c8331be747cd1e  ercs/contracts/TrustRegistry.sol
529e6800a184c6aa35969b2dbbd2a19f302ee706ff2441bb95f702425979c40d  ercs/contracts/ITrustRegistry.sol
98f155a69da7966a25b93f0623369152ee2d1a262ce08862796189cc1051e1a8  ercs/tests/continuity/RegistrationBoundary.sol
SUMS
