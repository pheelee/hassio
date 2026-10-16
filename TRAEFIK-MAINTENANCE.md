# Traefik release automation

The source lives in `pheelee/hassio-addon-traefik`, following Home Assistant
Community Apps' shared CI and deployment workflows. This catalog uses the
community `repository-updater==2.0.1` library. A small adapter selects stable,
beta or edge within this existing repository instead of requiring three catalog
repositories. It preserves unrelated add-ons and this repository's README.

The `.apps.yml` stable manifest remains compatible with the upstream CLI.
Its `channels` extension maps stable to `traefik`, beta to the existing
`traefik-beta`, and edge to `traefik-edge`. Beta and edge receive distinct slugs
and names so installations in this single catalog do not collide.

The source's pinned deployment workflow dispatches `update` events here after
successful GHCR publishing. Only events naming `traefik` and the expected source
repository are accepted. Main builds refresh edge, prereleases refresh beta,
and stable releases refresh both stable and beta. The updater checks that the
selected version's multi-architecture image exists before advertising it.

Before merging the source pipeline, merge this integration and configure:

- `DISPATCH_TOKEN` in the source repository: Contents write permission here,
  needed by the shared deployment's repository-dispatch action.
- `UPDATER_TOKEN` here: Contents write here and read access to the public source,
  needed by the community updater to commit and push catalog changes.

One appropriately scoped personal access token can supply both repository secrets.
Enter it in GitHub Settings → Secrets and variables → Actions; never commit it.
The updater runs as that token's account, with commits attributed to
`pheelee <pri@irbe.ch>`. It follows the upstream updater's direct-push behavior;
repository rules must permit those automated updates.

After the source's first GHCR publication, make its Traefik packages public in
GitHub package settings so Home Assistant can download without credentials.
To retry a channel, run **Update Traefik catalog** with `stable`, `beta` or `edge`.
The first new stable release is planned as `v0.5.5`. Until it exists, the existing
catalog versions and images remain unchanged by this PR; only missing source
URL metadata is added to the existing entries for updater compatibility.

ARMv7 is retired by that release, matching the current community pipeline.
Users must move to supported amd64/aarch64 installations before upgrading.

Run `python -m pip install -r scripts/requirements.txt` and
`python -m unittest discover -s tests -v` to validate dispatch/channel selection.
