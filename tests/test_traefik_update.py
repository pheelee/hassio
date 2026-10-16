import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from types import SimpleNamespace
import yaml
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("updater", Path(__file__).resolve().parents[1] / "scripts/update-traefik.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class ChannelTests(unittest.TestCase):
    def event(self, version):
        return {"client_payload": {"app": "traefik", "repository": updater.SOURCE, "version": version}}

    def test_edge_dispatch(self):
        github = Mock()
        self.assertEqual(updater.select_channels(self.event("abcdef1"), github), ["edge"])
        github.get_repo.assert_not_called()

    def test_stable_refreshes_beta_too(self):
        github = Mock()
        github.get_repo.return_value.get_release.return_value = Mock(draft=False, prerelease=False)
        self.assertEqual(updater.select_channels(self.event("v0.5.5"), github), ["stable", "beta"])

    def test_prerelease_only_refreshes_beta(self):
        github = Mock()
        github.get_repo.return_value.get_release.return_value = Mock(draft=False, prerelease=True)
        self.assertEqual(updater.select_channels(self.event("v0.5.5-rc.1"), github), ["beta"])

    def test_draft_rejected(self):
        github = Mock()
        github.get_repo.return_value.get_release.return_value = Mock(draft=True)
        with self.assertRaises(ValueError):
            updater.select_channels(self.event("v0.5.5"), github)

    def test_untrusted_source_rejected(self):
        event = self.event("v0.5.5")
        event["client_payload"]["repository"] = "someone/else"
        with self.assertRaises(ValueError):
            updater.select_channels(event, Mock())

    def test_unsafe_version_rejected(self):
        with self.assertRaises(ValueError):
            updater.select_channels(self.event("../../main"), Mock())

    def test_manual_channel_validation(self):
        self.assertEqual(updater.select_channels({"inputs": {"channel": "edge"}}, Mock()), ["edge"])
        with self.assertRaises(ValueError):
            updater.select_channels({"inputs": {"channel": "unknown"}}, Mock())


class LibraryIntegrationTests(unittest.TestCase):
    def test_upstream_generated_config_keeps_distinct_channel_slugs(self):
        for channel, target in (("stable", "traefik"), ("beta", "traefik-beta"), ("edge", "traefik-edge")):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as catalog:
                source_app = Path(source) / "traefik"
                source_app.mkdir()
                (source_app / "config.yaml").write_text(yaml.safe_dump({
                    "name": "Traefik", "slug": "traefik", "version": "dev", "arch": ["amd64", "aarch64"]}))
                (Path(catalog) / target).mkdir()
                app = object.__new__(updater.App)
                app.repository = SimpleNamespace(working_dir=catalog)
                app.git_repo = SimpleNamespace(working_dir=source)
                app.app_target = "traefik"
                app.repository_target = target
                app.current_version = "0.5.5"
                app.channel = channel
                app.image = "ghcr.io/pheelee/traefik/{arch}"
                app.update = app.generate_app_config
                repository = object.__new__(updater.CatalogRepository)
                repository.git_repo = SimpleNamespace(working_dir=catalog)
                repository.commit_changes = Mock(return_value=True)
                self.assertTrue(repository.update_app(app))
                result = yaml.safe_load((Path(catalog) / target / "config.yaml").read_text())
                self.assertEqual(result["slug"], target)
                self.assertEqual(result["version"], "0.5.5")
                self.assertEqual(result["image"], "ghcr.io/pheelee/traefik/{arch}")


class LegacyCatalogTests(unittest.TestCase):
    def test_legacy_beta_without_source_tag_can_migrate(self):
        app = object.__new__(updater.CatalogApp)
        app.repository_target = "traefik-beta"
        app.current_version = "0.5.2"
        with patch.object(updater.App, "_App__load_current_info", side_effect=updater.UnknownObjectException(404, {})):
            app._App__load_current_info()
        self.assertIsNone(app.current_commit)
        self.assertEqual(app.current_version, "0.5.2")

    def test_other_missing_tags_still_fail(self):
        app = object.__new__(updater.CatalogApp)
        app.repository_target = "traefik"
        app.current_version = "0.5.5"
        with patch.object(updater.App, "_App__load_current_info", side_effect=updater.UnknownObjectException(404, {})):
            with self.assertRaises(updater.UnknownObjectException):
                app._App__load_current_info()
