# Publishing authority-risk-mcp (what the maintainer does by hand, once, and then per release)

The workflow `.github/workflows/publish-mcp.yml` holds no secret. PyPI and npm each trust this repository's workflow, by identity (OIDC trusted publishing); an upload token is created for one run and expires. What can only be done by hand is the account side.

## Once

1. **Accounts** (nothing here is created by an assistant). Create a PyPI account and an npm account with a masked e-mail alias, turn on two-factor authentication (an authenticator app or a hardware key), save the recovery codes offline. Keep the e-mail hidden in both public profiles. The name `authority-risk-mcp` was free on both registries on 2026-10-14 (404 on both).
2. **GitHub environments.** Repository Settings > Environments > New environment, twice: `pypi` and `npm`. In each, turn on "Required reviewers" and add yourself, and limit "Deployment branches and tags" to the tag pattern `mcp-v*`. A publish job then waits for your click.
3. **PyPI trusted publisher (no project needed yet).** pypi.org > Account settings > Publishing > "Add a new pending publisher": PyPI project name `authority-risk-mcp`; owner `RealSpap`; repository `authority-risk-oracle-showcase`; workflow filename `publish-mcp.yml`; environment `pypi`. A pending publisher does not hold the name until it is used: publish soon after, and if someone else takes the name first, the pending publisher stops working.
4. **npm trusted publisher.** It is configured on the package's own settings page (npmjs.com > the package > Settings > Trusted publishing: user `RealSpap`, repository `authority-risk-oracle-showcase`, workflow `publish-mcp.yml`, environment `npm`), so the package must exist. The npm documentation read on 2026-10-14 does not say whether the page can be reached before a first publish. Try it. If it cannot, publish once by hand: from the tarball of the first workflow run (artifact `npm-dist`) or from `packages/authority-risk-mcp/npm` after `python3 vendor_tools.py --npm`, run `npm login` (with your two-factor code), `npm publish --access public`, then `npm logout`; then configure the trusted publisher. From then on npm is published by the workflow with provenance, and a trusted publisher not used within 2 days of being created expires (the docs say so): configure it right before the release. The first manual version has no provenance; say so in the release notes.
5. **Confirm the pinned key.** The package trusts one Ed25519 public key for the Watch's signed manifest: `11baca3ef6a69de4901c185f6cbbd3f93318fbb74f9961a8d39aead841adf409` (read from `watch-data/signature.json` on 2026-10-14). Check that it is the public half of your `WATCH_SIGNING_KEY`, and consider writing it in the repository README so that anyone can compare. If you rotate the signing key, release a new version with the new key (users can pass `--trust-key` meanwhile).

## For each release

1. The lot that adds `packages/authority-risk-mcp` and the workflow is pushed to `main` (the tag must contain the workflow file).
2. Check the three version numbers agree (`pyproject.toml`, `npm/package.json`, `server.json`); the workflow refuses otherwise.
3. Tag and push the tag yourself: `git tag mcp-v0.1.0 && git push origin mcp-v0.1.0`.
4. GitHub > Actions > "Publish authority-risk-mcp" > Run workflow > "Use workflow from": Tag `mcp-v0.1.0`. It tests, builds, installs both packages in throwaway environments and calls the tools; then it waits for you at `pypi` and `npm`.
5. Approve `pypi`, then `npm`. Check `pip index versions authority-risk-mcp` and `npm view authority-risk-mcp`.
6. **Registry.** With both packages published, in `packages/authority-risk-mcp`: `mcp-publisher login github` (device code in a browser), then `mcp-publisher publish`. The registry checks `mcpName` in the npm package and the `mcp-name:` line in the PyPI README against `server.json`. Then check: `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.RealSpap/authority-risk-mcp"`.
7. **Try it as a user:** `uvx authority-risk-mcp --version` and `npx -y authority-risk-mcp --version`, then the configuration block of the README in Claude Desktop or Cursor.

## If something is wrong after a release

PyPI: "yank" the version in the project's page (it stays installable by exact pin). npm: `npm deprecate authority-risk-mcp@0.1.0 "reason"`. Neither can be deleted and re-used: fix forward with 0.1.1.

## The build is checked before any tag

`build_packages.sh` holds every build command (copy the tool modules, `python -m build`, `twine check`, `npm pack`, and checks that the wheel, the sdist and the tarball contain what they need). The publish workflow and the workflow `package-build.yml` (on every push that touches the package, the tool modules or the workflows) both run that same file, then the tests and the install tests on the files it built. The first release attempt failed because a file named `build.py` in the package folder hid the PyPA `build` module from `python -m build`; the pre-build script is now `vendor_tools.py` and a test refuses any top-level file that carries the name of a module the build chain uses.

## What the packages do not contain

No secret, no real name, no private e-mail. The author field is `RealSpap`; the only URLs are the repository's. The tool modules inside are copied byte for byte from `scripts/` by `vendor_tools.py` (a test checks it); the rules engine and the alert senders of the repository are not part of the package.
