# What we do not read

A score is a reading of public chain state, and some things do not show in it. This page lists them, each with the document where it is written. Numbers are counts over the 202 targets the Watch tracks, recomputed from the public files of the site and of the Watch, read between 22 and 24 October 2026.

## We read exposure, not what happens next

The score reads how much one compromise could do. It does not say who is hit. In a test written before any measurement, the composite did not separate 5 incident victims from 18 untouched peers of similar size read one month before each incident.

Written in: METHODOLOGY.md.

## We do not detect a compromise

The Watch reports changes to who controls a contract, upgrades and queued operations. It does not detect that a key has been stolen. The attacks we studied went around the configuration (a spoofed signing interface, compromised devices, a service key), which a configuration score does not show.

Written in: METHODOLOGY.md; README.md.

## We do not see how a key is kept

A plain key (an account with no code behind it) reads the same on a chain whether it sits in a hardware wallet, was leaked, or is an exchange hot wallet. In the Watch, 15 of the 202 tracked targets have a plain key as the holder of admin power.

Written in: METHODOLOGY.md.

## We do not see the people behind the keys

Three owners of a Safe could be three employees of one company, or one person's three wallets. The multisig score measures the strength of the threshold, not the independence of the signers. Approvals and arrangements made off the chain are not visible from chain state.

Written in: METHODOLOGY.md.

## The cross-ecosystem check compares EVM chains with each other

A shared-signer check between ecosystems is made among the EVM chains. On Solana, Zcash and the native multisigs of Hyperliquid, the cross exposure score compares signers inside the same ecosystem: a 100 there means that no shared signer was found inside it, not that none exists elsewhere. Key formats differ (Solana, Zcash), or the tool cannot list the signers (native Hyperliquid multisigs). 27 of the 42 Solana and Hyperliquid targets publish a cross exposure score of 100.

Written in: METHODOLOGY.md.

## Day-to-day roles are not all scored

A score follows the path that upgrades or reconfigures a contract. It does not list every role or every getter that could grant some privilege. How a role that can pause is treated is not uniform in the current reading: some targets list it without scoring it, others score it, and for many no written rule exists yet. See METHODOLOGY.md for what the method says.

Written in: METHODOLOGY.md.

## Some delays and key counts are not read

A line that could not be read is written as not read, never as a zero. Of the 202 tracked targets, 89 list the time anyone has to react as not read, and 115 list the number of keys it takes to move the contract as not read. Each target page says which.

Written in: METHODOLOGY.md; WHAT-THE-SCORE-SAYS.md.

## The oracle is a plain-key target itself

On the Ethereum oracle (Sepolia), the admin role is held by one account with no code, a plain key; scores are pushed by one updater key with no timelock. By this project's own method a bare key scores (5, 0, 0), a composite of 2 out of 100. The test oracles hold no user funds, and it is disclosed here so that a consumer weighs it first.

Written in: METHODOLOGY.md; REFERENCE.md; SECURITY.md.

