# Traefik catalog updater

The add-on uses the pinned community deployment workflow to build GHCR images
and dispatch catalog updates. This adapter keeps stable, beta and edge entries
in one catalog, with distinct slugs for each channel.

Preparation reads source files through GitHub's API and checks that the versioned
image exists. It rejects source templates, links and unexpected file paths.
Publishing materializes the prepared data with Python's standard library; only
the final git push receives the short-lived repository write token.

Candidates include the catalog version seen during preparation. Before changing
any files, publishing checks that each target still has that version. A stale
candidate fails: start a fresh workflow run instead of rerunning its publish job.
Fresh same-version updates are allowed, as in the community updater. This guard
prevents stale artifacts from overwriting changed versions; it is not a general
version-downgrade policy or an image provenance check.

Runs are serialized, and git pushes never use force. Generated commits use
`chore(catalog): update published Traefik entries`.

Run the tests with:

```sh
python -m pip install -r scripts/requirements.txt
python -m unittest discover -s tests -v
```
