# Traefik release automation

The source repository `pheelee/hassio-addon-traefik` uses the pinned Home Assistant
Community Apps CI/deployment workflows and publishes GHCR images. This catalog
uses a small data-only exporter for its stable, beta and edge entries. It does
not install or execute the community `repository-updater` library, whose template
and file-copy behavior is unsuitable for a job holding a catalog write token.

## Credential boundary

1. The **prepare** job has read-only `GITHUB_TOKEN` permissions. It reads public
   GitHub API blobs at a source revision belonging to `main`, parses config with
   `yaml.safe_load`, and checks that the selected image exists. It never checks
   out or executes source files. Symlinks, submodules, path escapes, incomplete
   trees and source `.README.j2` templates are rejected. File sizes are bounded.
2. The JSON candidate is transferred through an artifact scoped to the same
   workflow run. The **publish** job validates it again and uses only Python's
   standard library to write an explicit allowlist of catalog files. Template
   syntax in Markdown remains literal text. Existing catalog symlinks are rejected.
   No third-party Python dependency is installed in this job.
3. Only the final Git push step receives the short-lived, repository-scoped
   `GITHUB_TOKEN`. Checkout credentials are not persisted and Git hooks are disabled.
   The preparation job never receives a write credential. Both jobs run only for
   the catalog's `main` ref.

`UPDATER_TOKEN` is no longer used or required. If you created a PAT solely for it,
remove that repository secret and revoke the unused PAT. The remaining source-side
`DISPATCH_TOKEN` is a separate fine-grained PAT (or GitHub App token) scoped to
`pheelee/hassio` with Contents write, needed by the community cross-repository
`repository_dispatch` action. Enter it in GitHub repository Actions secrets.

The updater listens only for dispatches and manual runs, never for its own pushes.
Its built-in-token push also receives GitHub's usual protection against cascading
push workflows. Do not configure a workflow that dispatches back to the source
in response to these updates.

## Channels and deployment

`.apps.yml` maps stable to `traefik`, beta to the existing `traefik-beta`, and edge
to `traefik-edge`. The preparer validates these mappings against its fixed source
and target allowlist. Non-stable entries have distinct names and slugs.
Unrelated catalog add-ons and the root README remain unchanged.

Dispatch payloads must name Traefik and its expected source repository; GitHub
requires authorization to send the dispatch. Stable events refresh stable/beta,
prerelease events refresh beta, and main events refresh edge. The current eligible
release or main revision is selected afresh, so stale events cannot force rollback.
The catalog never resolves historical installed versions to source tags: the old
beta `0.5.2` entry can migrate without inventing its missing tag.

Merge this integration first, configure `DISPATCH_TOKEN` in the source repo, then
merge the source pipeline. After the first publication, make the Traefik GHCR
packages public so Home Assistant can download without credentials. If an image
or manifest is not ready yet, the updater fails closed; retry **Update Traefik
catalog** with `stable`, `beta` or `edge` when publication is complete.

Release Drafter owns the next version. Current catalog versions and image names
stay unchanged until a new published image is selected. ARMv7 is retired by that
release; users must migrate to supported amd64/aarch64 installations.

Catalog commits are attributed to `pheelee <pri@irbe.ch>` and pushed using the
repository's GitHub Actions identity. Repository rules must allow the automated
push; failing a rule stops publication rather than bypassing it.

## Validation

Install `scripts/requirements.txt` in a virtual environment and run
`python -m unittest discover -s tests -v`. Tests exercise source/template/symlink
rejection, literal Markdown handling, path confinement, release selection,
credential/job boundaries and the real isolated publisher entrypoint.
