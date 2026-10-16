import base64
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("updater", Path(__file__).resolve().parents[1] / "scripts/update-traefik.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)
SHA = "a" * 40
TEMPLATE = "{{ cycler.__init__.__globals__.os.environ.get('UPDATER_TOKEN') }}"


def candidate(channel="stable"):
    return dict(channel=channel, source=updater.SOURCE, revision=SHA,
                version=SHA[:7] if channel == "edge" else "1.0.0",
                config={"arch": ["aarch64", "amd64"], "version": "dev", "slug": "../../escape"},
                files={"README.md": base64.b64encode(TEMPLATE.encode()).decode()})


class FakeAPI:
    def __init__(self):
        self.tree = {"tree": [
            dict(path="traefik/config.yaml", mode="100644", type="blob", sha="b" * 40, size=100),
            dict(path="traefik/README.md", mode="100644", type="blob", sha="c" * 40, size=100)]}
        self.blobs = {"b" * 40: b"version: dev\narch: [aarch64, amd64]\n", "c" * 40: TEMPLATE.encode()}
        self.status = "ahead"
        self.release = dict(draft=False, prerelease=False, tag_name="v1.0.0", body="Release notes")

    def __call__(self, path):
        if "/releases/tags/" in path:
            return self.release
        if "/releases?" in path:
            return [self.release]
        if "/commits/" in path:
            return {"sha": SHA, "commit": {"tree": {"sha": "d" * 40}}}
        if "/compare/" in path:
            return {"status": self.status}
        if "/git/trees/" in path:
            return self.tree
        if "/git/blobs/" in path:
            return {"encoding": "base64", "content": base64.b64encode(self.blobs[path.rsplit("/", 1)[1]]).decode()}
        raise AssertionError(path)


class DispatchTests(unittest.TestCase):
    def event(self, version):
        return {"client_payload": {"app": "traefik", "repository": updater.SOURCE, "version": version}}

    def test_edge(self):
        self.assertEqual(updater.select_channels(self.event("abcdef1"), FakeAPI()), ["edge"])

    def test_stable_and_beta(self):
        self.assertEqual(updater.select_channels(self.event("v1.0.0"), FakeAPI()), ["stable", "beta"])

    def test_prerelease(self):
        fetch = FakeAPI()
        fetch.release["prerelease"] = True
        self.assertEqual(updater.select_channels(self.event("v1.0.0-rc.1"), fetch), ["beta"])

    def test_semantic_prerelease_even_if_flag_unset(self):
        self.assertEqual(updater.select_channels(self.event("v1.0.0-rc.1"), FakeAPI()), ["beta"])

    def test_reject_draft(self):
        fetch = FakeAPI()
        fetch.release["draft"] = True
        with self.assertRaises(ValueError):
            updater.select_channels(self.event("v1.0.0"), fetch)

    def test_reject_untrusted_dispatch(self):
        for version in ("../main", "--config=oops"):
            with self.assertRaises(ValueError):
                updater.select_channels(self.event(version), FakeAPI())
        event = self.event("v1.0.0")
        event["client_payload"]["repository"] = "another/repo"
        with self.assertRaises(ValueError):
            updater.select_channels(event, FakeAPI())

    def test_manual(self):
        self.assertEqual(updater.select_channels({"inputs": {"channel": "edge"}}), ["edge"])
        with self.assertRaises(ValueError):
            updater.select_channels({"inputs": {"channel": "other"}})


class PreparationTests(unittest.TestCase):
    def prepare(self, fetch):
        with patch.object(updater.subprocess, "run"):
            return updater.prepare_channel("stable", fetch)

    def test_full_preparation_and_materialization(self):
        update = self.prepare(FakeAPI())
        with tempfile.TemporaryDirectory() as root:
            updater.materialize([update], root)
            config = json.loads((Path(root) / "traefik/config.json").read_text())
            self.assertEqual(config["version"], "1.0.0")
            self.assertEqual(config["image"], "ghcr.io/pheelee/traefik/{arch}")

    def test_prepares_edge_and_beta_versions(self):
        fetch = FakeAPI()
        with patch.object(updater.subprocess, "run"):
            self.assertEqual(updater.prepare_channel("edge", fetch)["version"], SHA[:7])
            fetch.release.update(tag_name="v1.0.0-rc.1", prerelease=True)
            self.assertEqual(updater.prepare_channel("beta", fetch)["version"], "1.0.0-rc.1")

    def test_source_symlink_rejected_before_any_blob_read(self):
        fetch = FakeAPI()
        fetch.tree["tree"].append(dict(path="traefik/logo.png", mode="120000", type="blob", sha="e" * 40, size=18))
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.prepare(fetch)

    def test_nested_translation_symlink_rejected(self):
        fetch = FakeAPI()
        fetch.tree["tree"].append(dict(path="traefik/translations/en.yaml", mode="120000", type="blob", sha="e" * 40, size=18))
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.prepare(fetch)

    def test_template_rejected(self):
        fetch = FakeAPI()
        fetch.tree["tree"].append(dict(path="traefik/.README.j2", mode="100644", type="blob", sha="e" * 40, size=100))
        with self.assertRaisesRegex(ValueError, "templates"):
            self.prepare(fetch)

    def test_unsafe_and_incomplete_trees(self):
        for path in ("traefik/../logo.png", "traefik/translations/../../logo.png", "traefik/dir\\logo.png"):
            fetch = FakeAPI()
            fetch.tree["tree"][0]["path"] = path
            with self.assertRaises(ValueError):
                self.prepare(fetch)
        fetch.tree["truncated"] = True
        with self.assertRaises(ValueError):
            self.prepare(fetch)

    def test_unreviewed_commit_rejected(self):
        fetch = FakeAPI()
        fetch.status = "diverged"
        with self.assertRaisesRegex(ValueError, "reviewed main"):
            self.prepare(fetch)

    def test_missing_image_blocks_update(self):
        with patch.object(updater.subprocess, "run", side_effect=updater.subprocess.CalledProcessError(1, ["docker"])):
            with self.assertRaises(updater.subprocess.CalledProcessError):
                updater.prepare_channel("stable", FakeAPI())


class MaterializationTests(unittest.TestCase):
    def test_templates_are_literal_and_token_is_not_copied(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"UPDATER_TOKEN": "synthetic-secret"}):
            updater.materialize([candidate()], root)
            content = (Path(root) / "traefik/README.md").read_text()
            self.assertEqual(content, TEMPLATE)
            self.assertNotIn("synthetic-secret", content)

    def test_distinct_slugs_and_unrelated_addons_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / "unrelated"
            marker.mkdir()
            (marker / "config.json").write_text("unchanged")
            updater.materialize([candidate(channel) for channel in updater.TARGETS], root)
            for channel, target in updater.TARGETS.items():
                config = json.loads((Path(root) / target / "config.json").read_text())
                self.assertEqual(config["slug"], target)
            self.assertEqual((marker / "config.json").read_text(), "unchanged")

    def test_candidate_path_traversal_rejected(self):
        for path in ("../outside", "/tmp/outside", "translations/../../outside", ".git/config", ".README.j2"):
            update = candidate()
            update["files"][path] = "eA=="
            with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
                updater.materialize([update], root)

    def test_existing_catalog_symlink_cannot_overwrite_external_file(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as external:
            private = Path(external) / "canary"
            private.write_text("unchanged")
            target = Path(root) / "traefik"
            target.mkdir()
            (target / "README.md").symlink_to(private)
            with self.assertRaises(ValueError):
                updater.materialize([candidate()], root)
            self.assertEqual(private.read_text(), "unchanged")

    def test_malformed_candidate_rejected(self):
        for field, value in (("revision", "../main"), ("source", "other/repo"), ("version", "1.0.0-rc.1")):
            update = candidate()
            update[field] = value
            with self.assertRaises(ValueError):
                updater.validate_candidate([update])
        update = candidate()
        update["files"]["README.md"] = "invalid base64!"
        with self.assertRaises(ValueError):
            updater.validate_candidate([update])

    def test_real_publisher_entrypoint_needs_only_standard_library(self):
        script = Path(updater.__file__).resolve()
        with tempfile.TemporaryDirectory() as root:
            payload = Path(root) / "candidate.json"
            payload.write_text(json.dumps([candidate()]))
            result = subprocess.run([sys.executable, "-I", "-S", str(script), "materialize", str(payload)],
                                    cwd=root, env={**os.environ, "GITHUB_REPOSITORY": updater.CATALOG},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(root) / "traefik/config.json").is_file())



class WorkflowBoundaryTests(unittest.TestCase):
    def test_manifest_is_restricted_to_known_source_and_targets(self):
        updater.validate_catalog_manifest(Path(__file__).resolve().parents[1] / ".apps.yml")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / ".apps.yml"
            path.write_text("channels: {stable: {other: {repository: attacker/repo}}}")
            with self.assertRaises(ValueError):
                updater.validate_catalog_manifest(path)

    def test_only_push_step_receives_write_token(self):
        import yaml
        workflow = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/traefik-update.yml").read_text())
        self.assertEqual(workflow["jobs"]["prepare"]["permissions"], {"contents": "read"})
        publisher = workflow["jobs"]["publish"]
        self.assertEqual(publisher["permissions"], {"contents": "write"})
        for step in publisher["steps"]:
            if "run" in step and "GH_TOKEN" in step.get("env", {}):
                self.assertIn("push", step["run"])
                self.assertNotIn("python", step["run"])
                self.assertNotIn("pip", step["run"])
        self.assertNotIn("secrets.UPDATER_TOKEN", json.dumps(workflow))
        self.assertNotIn("pip install", json.dumps(publisher))
