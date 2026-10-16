# Traefik catalog publication

The read-only preparation job obtains source files as data through GitHub's API.
It accepts source commits in the add-on's main history and rejects source links,
templates and unexpected file paths. It never checks out or executes source code.

Before preparing an update, image inspection requires both Linux amd64 and arm64
in the combined version manifest. Each architecture tag must reference the same
platform image digest as the combined manifest. Image configuration labels must
match the source repository, full source commit, release version and add-on
architecture. Inspection reads manifests and image configurations without pulling
or running image layers. Missing, inconsistent or not-yet-published images fail
closed; start a fresh update run after the image publication finishes.

Each candidate records a SHA-256 fingerprint of the current target's `config.json`
and `.publication.json` (including their absence). The credential-free publisher
compares this with current catalog main before changing anything. If another
publication changed either file, the candidate is stale and rejected. Start a
new workflow run to prepare fresh data; rerunning an old publish job cannot
refresh its artifact. A concurrent change after checkout is also rejected by the
ordinary, non-force git push.

Stable and beta candidates must not lower the installed semantic version.
Prereleases follow SemVer ordering, including numeric identifiers (`rc.10` is
newer than `rc.2`). A same-version candidate cannot replace an already recorded
revision or image index digest. All requested channels are validated before any
target is modified. Existing catalog entries without publication metadata are
migrated on their first successful update, still with version and state checks.

`.publication.json` records the full source revision and the verified architecture
index digests. The Home Assistant config continues to use versioned image tags.
The digest record supports consistency checks and auditing; it does not pin Home
Assistant's pulls to those digests. Image labels are publisher assertions, not
signed provenance, and registry tags could change after inspection. Cryptographic
provenance verification and promotion of the exact tested images remain separate
work. Only users trusted to publish images should have package write access.

There is no automated rollback override. A deliberate rollback requires a
reviewed change to the catalog and an explicit maintainer decision. Do not edit
candidate artifacts to bypass freshness or version checks.

The publisher executes only repository-owned Python with the standard library.
Only its final push step receives the short-lived write token. Generated commits
use `chore(catalog): update published Traefik entries`; they remain unsigned.

Run the regression suite with:

```sh
python -m pip install -r scripts/requirements.txt
python -m unittest discover -s tests -v
```
