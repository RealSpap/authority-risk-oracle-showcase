# E-2026-11-16: the command in my message 459 of the ERC-8183 thread could not run

Date of this entry: 2026-11-16. Status: corrected in place, by edits of the message that this entry dates. Nothing was deleted: the forum keeps the three versions of the message, and anyone can read them.

## What I said

In [message 459 of the ERC-8183 thread on Ethereum Magicians](https://ethereum-magicians.org/t/erc-8183-agentic-commerce/27902/459), posted on 2026-11-14 at 19:29:07 UTC, I gave one command that checks the hash chain of my public journal (`events.jsonl` on the `watch-data` branch of this repository). The command prints how many links of the chain are valid. The message said that it printed 286 of 286 links valid at 19:14Z on 14 November.

## What was wrong

In the first version the command stood inside the sentence, not in a code block. The forum displayed it with typographic quotation marks around the Python code and turned the address into a link, so pasted as displayed it could not run. The text stored for that version also held a backslash before each square bracket, which the display hid. In the second version the command was in a code block, the backslashes became visible, and a reader who pasted it got a syntax error. The raw text of the first and of the second version contains those backslashes, and the raw text of the third contains none. Where the backslashes came from is not recorded anywhere I can read: the forum keeps the text of each version, not how it was entered, so I make no claim about the cause.

The note at the end of version 3 says that the first version of the command showed a backslash before each square bracket. That is true of the second version and not of the first, whose display had no backslash. The note stays as written in version 3, and its word "first" is imprecise; this entry gives the precise account.

## The three versions, read on the forum at 16:02Z on 18 November 2026

- Version 1, 2026-11-14 at 19:29:07 UTC: the command stood inside the sentence, displayed with typographic quotation marks and a link on its address; the stored text held a backslash before each square bracket.
- Version 2, 2026-11-14 at 19:40:30 UTC ([revision 2](https://ethereum-magicians.org/posts/76651/revisions/2.json)): I put the command in a code block; the backslashes became visible.
- Version 3, 2026-11-16 at 13:40:02 UTC ([revision 3](https://ethereum-magicians.org/posts/76651/revisions/3.json)): I rewrote the command without any square bracket, in a code block with straight quotation marks, gave the two readings of the message again at 12:59Z on 16 November (the count of links of the journal, and the empty answer of `eth_getCode` for the address `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` on Ethereum mainnet, chain ID 1), and wrote the edit into the message itself. The result of the first version, 286 of 286 links valid at 19:14Z on 14 November, stays in the message.

## What is true

The command of version 3 is:

```
curl -s https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/watch-data/events.jsonl | python3 -c "import sys,json,hashlib as h;L=sys.stdin.buffer.read().splitlines();i=iter(L);next(i);print(sum(json.loads(b).get('prev')==h.sha256(a).hexdigest() for a,b in zip(L,i)),'of',len(L)-1,'links valid')"
```

Run exactly as the forum displays it, read at 16:02Z on 18 November 2026, it printed 309 of 309 links valid. The count grows with the journal. As the message says, the command does not see a cut of the newest lines, so the head of the journal has to be pinned elsewhere.

## Why I edited the message in place

The README of this folder says that a published statement is never edited or removed to hide the error. I chose to edit this one because the command did not run as displayed, and a correction posted under it would have left the broken command at the place where readers copy it from. The edit hides nothing: the message says what was edited, the three versions stay readable at the two links above, and this entry gives the time of each. The choice to edit is mine.

## Replay

Each command is one line. On the forum, `curl -s https://ethereum-magicians.org/posts/76651/revisions/3.json` prints the third version of the message and what changed against the second. The command of version 3 is in the section above; run it in any terminal with `curl` and `python3`.

## What this entry does not claim

- Why the backslashes appeared.
- Anything about the rest of message 459 beyond its command and its two readings.
