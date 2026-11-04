#!/usr/bin/env node
// Launches the Python MCP server that ships inside this package (./python/authority_risk_mcp). It needs python3 3.9 or newer on the PATH
// and says so when it cannot find one. Standard input and output are handed straight to the server: this file adds nothing to the protocol.
"use strict";
const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");

const python = path.join(__dirname, "..", "python");
const candidates = process.platform === "win32" ? [["py", ["-3"]], ["python", []], ["python3", []]] : [["python3", []], ["python", []]];
const probe = "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 3)";

let found = null;
for (const [cmd, pre] of candidates) {
  const r = spawnSync(cmd, [...pre, "-c", probe], { stdio: "ignore" });
  if (r.status === 0) { found = [cmd, pre]; break; }
}
if (!found) {
  process.stderr.write("authority-risk-mcp: Python 3.9 or newer was not found on the PATH (tried " + candidates.map((c) => c[0]).join(", ") + ").\n" +
    "This npm package is a launcher for a Python server. Install Python, or use the same server through uvx: { \"command\": \"uvx\", \"args\": [\"authority-risk-mcp\"] }.\n");
  process.exit(1);
}

const env = { ...process.env, PYTHONPATH: python + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""), PYTHONDONTWRITEBYTECODE: "1" };
// The server starts in the package folder, not in the folder the user is in: `python -m` puts the current directory first on the import path, and a file of the project the agent is reading
// (agent_tools.py, json.py ...) must not run inside the server. A path given on the command line is made absolute first so that it still means what the user typed.
const args = process.argv.slice(2).map((a, i, all) => (all[i - 1] === "--data-dir" ? path.resolve(a) : a.startsWith("--data-dir=") ? "--data-dir=" + path.resolve(a.slice(11)) : a));
const child = spawn(found[0], [...found[1], "-m", "authority_risk_mcp", ...args], { stdio: "inherit", env, cwd: python });
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
child.on("exit", (code, signal) => process.exit(code === null ? (signal ? 1 : 0) : code));
child.on("error", (e) => { process.stderr.write("authority-risk-mcp: could not start Python: " + e.message + "\n"); process.exit(1); });
