#!/usr/bin/env python3
"""Use the community updater with stable/beta/edge entries in one catalog."""
import json
import os
from pathlib import Path
import re
import subprocess

import yaml
from repositoryupdater.github import GitHub
from repositoryupdater.app import App
from repositoryupdater.repository import Repository

SOURCE = "pheelee/hassio-addon-traefik"
CATALOG = "pheelee/hassio"


def select_channels(event, github):
    """Treat dispatch payloads as untrusted; accept only our app and real tags."""
    if "client_payload" not in event:
        channel = event.get("inputs", {}).get("channel", "stable")
        if channel not in ("stable", "beta", "edge"):
            raise ValueError("Unknown catalog channel")
        return [channel]
    payload = event["client_payload"]
    if payload.get("app") != "traefik" or payload.get("repository") != SOURCE:
        raise ValueError("Only the Traefik source repository is accepted")
    version = payload.get("version", "")
    if re.fullmatch(r"[a-f0-9]{7}", version):
        return ["edge"]
    if not re.fullmatch(r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise ValueError("Invalid version in repository dispatch")
    release = github.get_repo(SOURCE).get_release(version)
    if release.draft:
        raise ValueError("Draft releases cannot be published")
    return ["beta"] if release.prerelease else ["stable", "beta"]


class CatalogRepository(Repository):
    def __init__(self, *args, channel, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_channel = channel

    def load_repository(self, app_filter):
        manifest = yaml.safe_load(self.github_repository.get_contents(".apps.yml").decoded_content)
        self.channel = self.selected_channel
        for target, config in manifest["channels"][self.channel].items():
            self.apps.append(App(self.github, self.git_repo, target, config["image"],
                                 self.github.get_repo(config["repository"]),
                                 config["target"], self.channel, True))

    def update_app(self, app):
        app.update()
        if app.channel != "stable":
            directory = Path(self.git_repo.working_dir) / app.repository_target
            path = next(path for path in (directory / "config.yaml", directory / "config.json") if path.exists())
            config = yaml.safe_load(path.read_text())
            config["slug"] = app.repository_target
            config["name"] = f"Traefik ({app.channel.title()})"
            path.write_text((json.dumps(config, indent=2) + "\n") if path.suffix == ".json"
                            else yaml.safe_dump(config, sort_keys=False))
        return self.commit_changes(f"Update {app.repository_target} to {app.current_version}")

    def generate_readme(self):
        # This repository also contains independently maintained, unrelated add-ons.
        # Preserve its hand-maintained README; the updater still generates app docs.
        return


def main():
    if os.environ["GITHUB_REPOSITORY"] != CATALOG:
        raise ValueError("This updater is restricted to the pheelee/hassio catalog")
    github = GitHub(os.environ["UPDATER_TOKEN"])
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    for channel in select_channels(event, github):
        repository = CatalogRepository(github, CATALOG, None, force=False, channel=channel)
        try:
            # An app's latest source can advance while an older deployment finishes.
            # Do not advertise a version until its complete multi-arch image exists.
            for app in repository.apps:
                version = app.latest_version
                image = app.image.replace("/{arch}", "")
                subprocess.run(["docker", "buildx", "imagetools", "inspect", f"{image}:{version}"],
                               check=True, stdout=subprocess.DEVNULL)
            repository.update()
        finally:
            repository.cleanup()


if __name__ == "__main__":
    main()
