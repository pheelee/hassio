#!/usr/bin/env python3
"""Prepare public source data, then materialize it without executing source code."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

SOURCE = "pheelee/hassio-addon-traefik"
CATALOG = "pheelee/hassio"
IMAGE = "ghcr.io/pheelee/traefik"
TARGETS = {"stable": "traefik", "beta": "traefik-beta", "edge": "traefik-edge"}
STATIC = {"logo.png", "icon.png", "README.md", "DOCS.md", "apparmor.txt"}
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")
MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 20 * 1024 * 1024
DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
ARCHITECTURES = {"aarch64": "arm64", "amd64": "amd64"}
EMPTY_STATE = hashlib.sha256(b"\0\0").hexdigest()


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def version_key(version):
    """SemVer precedence, including numeric versus lexical prerelease identifiers."""
    if not VERSION.fullmatch(version):
        raise ValueError("Invalid semantic version")
    core, _, prerelease = version.partition("-")
    numbers = core.split(".")
    parts = prerelease.split(".") if prerelease else []
    if any(len(part) > 1 and part.startswith("0") for part in numbers):
        raise ValueError("Leading zero in semantic version")
    if any(not part or (part.isdigit() and len(part) > 1 and part.startswith("0")) for part in parts):
        raise ValueError("Invalid prerelease identifier")
    return (tuple(map(int, numbers)), not bool(prerelease),
            tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts))


def inspect_image(reference, field):
    return json.loads(subprocess.check_output(
        ["docker", "buildx", "imagetools", "inspect", reference, "--format", "{{json ." + field + "}}"],
        text=True))


def image_index(reference):
    manifest = inspect_image(reference, "Manifest")
    if not DIGEST.fullmatch(manifest["digest"]):
        raise ValueError("Invalid image digest")
    platforms = {}
    attestations = []
    for descriptor in manifest["manifests"]:
        digest = descriptor["digest"]
        if not DIGEST.fullmatch(digest):
            raise ValueError("Invalid platform digest")
        platform = descriptor["platform"]
        if platform == {"os": "unknown", "architecture": "unknown"}:
            annotations = descriptor.get("annotations", {})
            if annotations.get("vnd.docker.reference.type") != "attestation-manifest":
                raise ValueError("Unknown image platform")
            attestations.append(annotations.get("vnd.docker.reference.digest"))
            continue
        architecture = platform["architecture"]
        if platform["os"] != "linux" or architecture not in ARCHITECTURES.values() or architecture in platforms:
            raise ValueError("Unexpected or duplicate image platform")
        platforms[architecture] = digest
    if any(digest not in platforms.values() for digest in attestations):
        raise ValueError("Attestation does not reference an image platform")
    return manifest["digest"], platforms


def verify_images(version, revision):
    _, combined = image_index(f"{IMAGE}:{version}")
    if set(combined) != set(ARCHITECTURES.values()):
        raise ValueError("Combined image must contain both supported architectures")
    verified = {}
    for addon_arch, platform_arch in ARCHITECTURES.items():
        reference = f"{IMAGE}/{addon_arch}"
        digest, platforms = image_index(f"{reference}:{version}")
        if platforms != {platform_arch: combined[platform_arch]}:
            raise ValueError("Catalog architecture tag does not match combined image")
        image = inspect_image(f"{reference}@{platforms[platform_arch]}", "Image")
        if image["os"] != "linux" or image["architecture"] != platform_arch:
            raise ValueError("Image configuration platform mismatch")
        labels = image["config"]["Labels"]
        expected = {"org.opencontainers.image.source": f"https://github.com/{SOURCE}",
                    "org.opencontainers.image.revision": revision,
                    "org.opencontainers.image.version": version,
                    "io.hass.arch": addon_arch, "io.hass.version": version, "io.hass.type": "addon"}
        if any(labels.get(key) != value for key, value in expected.items()):
            raise ValueError("Image labels do not match the reviewed source, version and architecture")
        verified[addon_arch] = digest
    return verified


def select_channels(event, fetch=api):
    if "client_payload" not in event:
        channel = event.get("inputs", {}).get("channel", "stable")
        if channel not in TARGETS:
            raise ValueError("Unknown catalog channel")
        return [channel]
    payload = event["client_payload"]
    if payload.get("app") != "traefik" or payload.get("repository") != SOURCE:
        raise ValueError("Unexpected dispatch source")
    version = payload.get("version", "")
    if re.fullmatch(r"[a-f0-9]{7}", version):
        return ["edge"]
    if not VERSION.fullmatch(version.removeprefix("v")):
        raise ValueError("Invalid dispatch version")
    release = fetch(f"repos/{SOURCE}/releases/tags/{version}")
    if release["draft"]:
        raise ValueError("Draft releases cannot be published")
    prerelease = release["prerelease"] or "-" in version
    return ["beta"] if prerelease else ["stable", "beta"]


def asset_path(path):
    return path in STATIC or bool(re.fullmatch(r"translations/[A-Za-z0-9_-]+\.(?:yaml|yml|json)", path))


def validate_source_tree(tree):
    if tree.get("truncated"):
        raise ValueError("Incomplete source tree")
    entries = {}
    for entry in tree["tree"]:
        path = entry["path"]
        if path != "traefik" and not path.startswith("traefik/"):
            continue
        parts = path.split("/")
        if any(part in ("", ".", "..") for part in parts) or "\\" in path:
            raise ValueError("Unsafe source path")
        if entry["mode"] not in ("040000", "100644", "100755"):
            raise ValueError("Source symlinks, submodules and special entries are forbidden")
        if path.endswith("/.README.j2"):
            raise ValueError("Source templates are forbidden")
        if entry["type"] == "blob":
            if entry["mode"] not in ("100644", "100755"):
                raise ValueError("Invalid source blob mode")
            if entry.get("size", MAX_FILE + 1) > MAX_FILE:
                raise ValueError("Source file too large")
            entries[path.removeprefix("traefik/")] = entry
    return entries


def blob(entry, fetch):
    data = fetch(f"repos/{SOURCE}/git/blobs/{entry['sha']}")
    if data["encoding"] != "base64":
        raise ValueError("Unexpected blob encoding")
    result = base64.b64decode("".join(data["content"].split()), validate=True)
    if len(result) > MAX_FILE:
        raise ValueError("Source file too large")
    return result


def prepare_channel(channel, fetch=api, root=Path(".")):
    # PyYAML is used only in the read-only preparation job, never in publishing.
    import yaml

    release = None
    if channel == "edge":
        ref = "main"
    else:
        releases = fetch(f"repos/{SOURCE}/releases?per_page=100")
        release = next((item for item in releases if not item["draft"]
                        and VERSION.fullmatch(item["tag_name"].removeprefix("v"))
                        and (channel == "beta" or not (item["prerelease"] or "-" in item["tag_name"]))), None)
        if release is None:
            raise ValueError("No eligible release")
        ref = release["tag_name"]
    commit = fetch(f"repos/{SOURCE}/commits/{ref}")
    revision = commit["sha"]
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Invalid source revision")
    comparison = fetch(f"repos/{SOURCE}/compare/{revision}...main")
    if comparison["status"] not in ("ahead", "identical"):
        raise ValueError("Source revision must belong to reviewed main history")
    version = revision[:7] if channel == "edge" else ref.removeprefix("v")
    entries = validate_source_tree(fetch(f"repos/{SOURCE}/git/trees/{commit['commit']['tree']['sha']}?recursive=1"))
    config_entry = next((entries[name] for name in ("config.yaml", "config.json") if name in entries), None)
    if config_entry is None:
        raise ValueError("Missing source configuration")
    config = yaml.safe_load(blob(config_entry, fetch))
    if not isinstance(config, dict) or config.get("version") != "dev" or config.get("arch") != ["aarch64", "amd64"]:
        raise ValueError("Unexpected source configuration")
    files = {name: base64.b64encode(blob(entry, fetch)).decode()
             for name, entry in entries.items() if asset_path(name)}
    changelog = release.get("body") or "" if release else f"Edge build from commit {revision}.\n"
    files["CHANGELOG.md"] = base64.b64encode(changelog.encode()).decode()
    result = dict(channel=channel, version=version, revision=revision, source=SOURCE, config=config, files=files,
                  previous_state=catalog_state(Path(root) / TARGETS[channel]))
    # Source content is never checked out, imported, rendered or executed.
    result["images"] = verify_images(version, revision)
    validate_candidate([result])
    return result


def validate_candidate(updates):
    if not isinstance(updates, list) or not updates or len(updates) > 3:
        raise ValueError("Invalid candidate")
    channels = set()
    total = 0
    for update in updates:
        channel = update["channel"]
        if channel not in TARGETS or channel in channels or update["source"] != SOURCE:
            raise ValueError("Invalid candidate channel/source")
        channels.add(channel)
        revision, version = update["revision"], update["version"]
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("Invalid candidate revision")
        if channel == "edge":
            if version != revision[:7]:
                raise ValueError("Edge version does not match source")
        elif not VERSION.fullmatch(version) or (channel == "stable" and "-" in version):
            raise ValueError("Invalid release version")
        if channel != "edge":
            version_key(version)
        if not re.fullmatch(r"[a-f0-9]{64}", update["previous_state"]):
            raise ValueError("Invalid previous catalog state")
        if set(update["images"]) != set(ARCHITECTURES) or any(
                not DIGEST.fullmatch(digest) for digest in update["images"].values()):
            raise ValueError("Invalid verified image digests")
        if not isinstance(update["config"], dict) or update["config"].get("arch") != ["aarch64", "amd64"]:
            raise ValueError("Invalid candidate configuration")
        for name, encoded in update["files"].items():
            if not asset_path(name) and name != "CHANGELOG.md":
                raise ValueError("Unexpected candidate path")
            data = base64.b64decode(encoded, validate=True)
            total += len(data)
            if len(data) > MAX_FILE or total > MAX_TOTAL:
                raise ValueError("Candidate too large")


def reject_links(directory):
    if directory.is_symlink():
        raise ValueError("Catalog symlink forbidden")
    if directory.exists():
        for entry in directory.rglob("*"):
            if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
                raise ValueError("Catalog links/special files forbidden")


def catalog_state(directory):
    reject_links(directory)
    digest = hashlib.sha256()
    for name in ("config.json", ".publication.json"):
        path = directory / name
        if path.exists():
            data = path.read_bytes()
            digest.update(b"\1" + len(data).to_bytes(8, "big") + data)
        else:
            digest.update(b"\0")
    return digest.hexdigest()


def validate_transition(update, directory):
    if catalog_state(directory) != update["previous_state"]:
        raise ValueError("Stale candidate: catalog changed since preparation; start a fresh workflow run")
    current = directory / "config.json"
    if current.exists() and update["channel"] != "edge":
        old_version = json.loads(current.read_text())["version"]
        if version_key(update["version"]) < version_key(old_version):
            raise ValueError("Catalog version rollback forbidden")
    publication = directory / ".publication.json"
    if publication.exists():
        previous = json.loads(publication.read_text())
        if previous["version"] == update["version"] and (
                previous["revision"] != update["revision"] or previous["images"] != update["images"]):
            raise ValueError("Published version cannot be replaced with different source or image digests")


def materialize(updates, root):
    validate_candidate(updates)
    root = Path(root).resolve()
    # Validate every target before changing any file. No source-defined filenames.
    for update in updates:
        validate_transition(update, root / TARGETS[update["channel"]])
    for update in updates:
        channel = update["channel"]
        directory = root / TARGETS[channel]
        directory.mkdir(exist_ok=True)
        for name in (*STATIC, "CHANGELOG.md", "config.json", "config.yaml", "config.yml"):
            (directory / name).unlink(missing_ok=True)
        if (directory / "translations").exists():
            shutil.rmtree(directory / "translations")
        config = dict(update["config"])
        config.update(version=update["version"], image=f"{IMAGE}/{{arch}}", slug=TARGETS[channel],
                      name="Traefik" if channel == "stable" else f"Traefik ({channel.title()})",
                      url=f"https://github.com/{SOURCE}")
        (directory / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        publication = {key: update[key] for key in ("version", "revision", "images")}
        (directory / ".publication.json").write_text(json.dumps(publication, indent=2) + "\n")
        for name, encoded in update["files"].items():
            path = directory.joinpath(*PurePosixPath(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(encoded, validate=True))


def validate_catalog_manifest(path):
    import yaml

    manifest = yaml.safe_load(Path(path).read_text())
    expected = {channel: {target: dict(repository=SOURCE, target="traefik", image=f"{IMAGE}/{{arch}}")}
                for channel, target in TARGETS.items()}
    if manifest.get("channels") != expected:
        raise ValueError("Catalog manifest does not match the allowed source and targets")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "materialize"])
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") != CATALOG:
        raise ValueError("Unexpected catalog repository")
    if args.mode == "prepare":
        validate_catalog_manifest(Path.cwd() / ".apps.yml")
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        updates = [prepare_channel(channel) for channel in select_channels(event)]
        args.candidate.write_text(json.dumps(updates))
    else:
        if args.candidate.stat().st_size > MAX_TOTAL * 2:
            raise ValueError("Candidate too large")
        materialize(json.loads(args.candidate.read_text()), Path.cwd())


if __name__ == "__main__":
    main()
