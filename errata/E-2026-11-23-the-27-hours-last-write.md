# E-2026-11-23: the note on the PumpSwap buffer took a transfer for the last write

Date of this entry: 2026-11-23. Status: corrected in the note itself, with the old and the new value on the page. Nothing was deleted: my post of 18 November 2026 that links the note stays as written, and this entry and the corrected note are the correction.

## What I said

In the note [The 27 hours before the PumpSwap upgrade](https://realspap.github.io/oracle/notes/the-27-hours/), published on 17 November 2026, I said:

- that the buffer of the PumpSwap upgrade was "fully written at 13:49:21 UTC" on 14 November 2026, and that it waited 27 hours 30 minutes 59 seconds before the upgrade at 17:20:20 UTC on 15 November 2026;
- that the buffer "receives 1,258 transactions in all, and together they write 1,270,696 bytes of code";
- that "the newest three transactions of the buffer" are the upgrade, the change of authority and the last write, and that "from block 469350454" to the upgrade no transaction touches the buffer except the change of authority.

My post of 18 November 2026 that links the note repeats the count: "written in 1,258 transactions".

## What is true

Read at 18:56Z on 25 November 2026, on the node api.mainnet-beta.solana.com of Solana mainnet-beta, for the buffer `HBGEzR1n1ZKCN97KRSWQUSuBoM2CGXCZf2zpWCHbV6Fj` on Solana mainnet-beta: 1,260 transactions, none failed. The block times were read on a second node of the same network, solana-mainnet.gateway.tatum.io, and are the same. The 1,260 transactions of the buffer are:

| Transactions of the buffer | Count | Block and time, 14 November 2026 (UTC) |
|---|---|---|
| Creation of the account and its set-up as a buffer | 1 | block 469350301, 13:48:49 |
| Writes, one write instruction each | 1,256 | blocks 469350322 to 469350379, 13:48:53 to 13:49:06 |
| Transfer of 1 lamport to each of 19 accounts, one of them the buffer | 1 | block 469350454, 13:49:21 |
| Change of authority | 1 | block 469354509, 14:03:45 |
| Upgrade, on 15 November 2026 | 1 | block 469811067, 17:20:20 |

- The last write is in block 469350379, at 13:49:06 UTC. The transaction of 13:49:21 UTC is not a write. It is signed by the account `4yWkD5KrH6knPLfBzaFG5oZuYGgDp4jQDBfgpVsG1hqh` on Solana mainnet-beta, which is neither the authority of the buffer (`92gWFZMpGhWzVq5tjBnJxF9VnFwE3ydB2idJp9z2D9Nr` on Solana mainnet-beta) nor the vault (`7gZufwwAo17y5kg8FMyJy2phgpvv9RSdzWtdXiWHjFr8` on Solana mainnet-beta), and it sends 1 lamport to each of 19 accounts, one of which is the buffer. The chain does not say why.
- The wait between the last write and the upgrade is 99,074 seconds, 27 hours 31 minutes 14 seconds. The headline figure of the note, 27 h 31 min, was right. The wait I wrote, 27 hours 30 minutes 59 seconds, was 15 seconds short, because I started it at the transfer.
- The 1,258 transactions I counted are the transactions of the buffer before the change of authority. 1,256 of them hold a write, one creates the buffer and one is the transfer. The 1,270,696 bytes and their SHA-256 `d2ed30147f5eb202da7094567a7e5aec35d471487eeb8a081278c519d6b04966` are unchanged, because they come from the write instructions only.
- After block 469350454 and before the upgrade, one transaction touches the buffer: the change of authority. My sentence said "from block 469350454", which included the block of the transfer. The newest five transactions of the buffer are the upgrade, the change of authority, the transfer and two writes.

## Cause

My reading script took the newest transaction before the change of authority as the last write, without looking at what it holds. That transaction is the transfer. The rebuild of the bytes counted write instructions only, so the bytes and the hash were right, and the time, and the description of the 1,258 transactions as writes, were wrong. The error is mine. DAO Times raised the time on 21 November 2026 in [its article](https://daotimes.com/realspap-pumpswap-november-20-upgrade-public-buffer/).

## Changed since the note was written

PumpSwap was upgraded again at 19:28:12 UTC on 20 November 2026, in slot 471854493. The ProgramData account of the program now holds other code, so the last line printed by the last command of the note differs from the line before it. My reading of 19:04Z on 17 November 2026, which found the 1,270,696 bytes of the buffer equal to the code then held, is a dated record that the command cannot repeat any more.

## Replay

Commands 1, 6 and 7 of the note do it, each in one command. Command 6 returns the transfer: `curl -s https://api.mainnet-beta.solana.com -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"getTransaction","params":["wctUbGW2pMfBqqDM5mzUMow5jdpRpwGJACPKutdShoqGhJd6AczV8rBTzqAYHKgYsXfxabFneBvnMfHZajZUG1x",{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}]}'` prints 19 instructions of the System program, each moving 1 lamport, one of them to `HBGEzR1n1ZKCN97KRSWQUSuBoM2CGXCZf2zpWCHbV6Fj` on Solana mainnet-beta. Command 7 prints the newest write of the buffer with its block time and the wait before the upgrade.

## What this entry does not claim

- Why the transfer was sent, or by whom beyond the account that signed it.
- Why PumpSwap was upgraded, who chose the timing, or whether 27 hours is long or short.
