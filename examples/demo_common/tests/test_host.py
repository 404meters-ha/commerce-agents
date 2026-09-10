# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os

import pytest
from starlette.testclient import TestClient

from demo_common import host as host_module
from demo_common import host_approval_default, load_demo_env, spawn_background
from demo_common.host import _background_tasks, build_app


@pytest.mark.parametrize(
    ("value", "expected"), [(None, True), ("0", False), ("1", True), ("", True), ("true", True)]
)
def test_only_an_explicit_zero_turns_host_approval_off(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("MERCHANT_REQUIRE_HOST_APPROVAL", raising=False)
    else:
        monkeypatch.setenv("MERCHANT_REQUIRE_HOST_APPROVAL", value)
    assert host_approval_default() is expected


@pytest.fixture
def env_dirs(tmp_path, monkeypatch):
    """A repo root and an example directory under ``tmp_path``, with the loader pointed at
    the former and no credential variables in the environment."""
    repo_root, example_root = tmp_path / "repo", tmp_path / "repo" / "examples" / "retail"
    example_root.mkdir(parents=True)
    monkeypatch.setattr(host_module, "REPO_ROOT", repo_root)
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "COMMERCE_DEMO_AUTH",
    ):
        monkeypatch.delenv(name, raising=False)
    return repo_root, example_root


def test_a_key_in_the_environment_survives_a_blank_env_file(env_dirs, monkeypatch):
    repo_root, example_root = env_dirs
    (repo_root / ".env").write_text("DEEPSEEK_API_KEY=\n")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-the-shell")

    load_demo_env(example_root)

    assert os.environ["ANTHROPIC_API_KEY"] == "from-the-shell"


def test_the_example_env_file_fills_in_before_the_repo_root_one(env_dirs):
    repo_root, example_root = env_dirs
    (repo_root / ".env").write_text("DEEPSEEK_API_KEY=root-key\n")
    (example_root / ".env").write_text("DEEPSEEK_API_KEY=example-key\n")

    load_demo_env(example_root)

    assert os.environ["ANTHROPIC_API_KEY"] == "example-key"


def test_the_repo_root_env_file_is_read_when_the_example_has_none(env_dirs):
    repo_root, example_root = env_dirs
    (repo_root / ".env").write_text("DEEPSEEK_API_KEY=root-key\n")

    load_demo_env(example_root)

    assert os.environ["ANTHROPIC_API_KEY"] == "root-key"


def test_a_deepseek_key_maps_onto_the_client_variables(env_dirs):
    repo_root, example_root = env_dirs
    (repo_root / ".env").write_text("DEEPSEEK_API_KEY=deepseek-key\n")

    load_demo_env(example_root)

    assert os.environ["ANTHROPIC_API_KEY"] == "deepseek-key"
    assert os.environ["ANTHROPIC_BASE_URL"] == host_module.DEEPSEEK_BASE_URL


def test_the_deepseek_mapping_replaces_an_inherited_base_url(env_dirs, monkeypatch):
    repo_root, example_root = env_dirs
    (repo_root / ".env").write_text("DEEPSEEK_API_KEY=deepseek-key\n")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://stale-gateway.internal.example")

    load_demo_env(example_root)

    assert os.environ["ANTHROPIC_BASE_URL"] == host_module.DEEPSEEK_BASE_URL


def test_deepseek_base_url_overrides_the_default(env_dirs, monkeypatch):
    repo_root, example_root = env_dirs
    (repo_root / ".env").write_text("DEEPSEEK_API_KEY=deepseek-key\n")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://proxy.internal.example/anthropic")

    load_demo_env(example_root)

    assert os.environ["ANTHROPIC_BASE_URL"] == "https://proxy.internal.example/anthropic"


def test_an_inherited_anthropic_key_does_not_beat_the_deepseek_key(env_dirs, monkeypatch):
    repo_root, example_root = env_dirs
    (repo_root / ".env").write_text("DEEPSEEK_API_KEY=deepseek-key\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-the-shell")

    load_demo_env(example_root)

    assert os.environ["ANTHROPIC_API_KEY"] == "deepseek-key"
    assert os.environ["ANTHROPIC_BASE_URL"] == host_module.DEEPSEEK_BASE_URL


def test_an_inherited_anthropic_key_without_a_deepseek_key_is_dropped(env_dirs, monkeypatch):
    repo_root, example_root = env_dirs
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-the-shell")

    load_demo_env(example_root)

    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "ANTHROPIC_BASE_URL" not in os.environ


def test_an_inherited_base_url_without_a_deepseek_key_is_dropped(env_dirs, monkeypatch):
    repo_root, example_root = env_dirs
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://stale-gateway.internal.example")

    load_demo_env(example_root)

    assert "ANTHROPIC_BASE_URL" not in os.environ


def test_a_deepseek_key_clears_an_inherited_auth_token(env_dirs, monkeypatch):
    repo_root, example_root = env_dirs
    (repo_root / ".env").write_text("DEEPSEEK_API_KEY=deepseek-key\n")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "a-token-for-other-tooling")

    load_demo_env(example_root)

    assert os.environ["ANTHROPIC_API_KEY"] == "deepseek-key"
    assert "ANTHROPIC_AUTH_TOKEN" not in os.environ
    assert os.environ["ANTHROPIC_BASE_URL"] == host_module.DEEPSEEK_BASE_URL


def test_sdk_auth_clears_key_variables_and_reads_no_file(env_dirs, monkeypatch):
    repo_root, example_root = env_dirs
    (repo_root / ".env").write_text("ANTHROPIC_API_KEY=root-key\nDEEPSEEK_API_KEY=deep-key\n")
    monkeypatch.setenv("COMMERCE_DEMO_AUTH", "sdk")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-the-shell")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-the-shell")

    load_demo_env(example_root)

    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "DEEPSEEK_API_KEY" not in os.environ


def test_demanded_origins_preflight_besides_localhost(monkeypatch):
    monkeypatch.setenv("DEMO_ALLOWED_ORIGINS", "http://203.0.113.7:3000,  ")
    client = TestClient(build_app("test"), base_url="http://localhost")
    preflight = {
        "Access-Control-Request-Method": "GET",
        "Origin": "http://203.0.113.7:3000",
    }
    allowed = client.options("/api/health", headers=preflight)
    assert allowed.headers["access-control-allow-origin"] == "http://203.0.113.7:3000"
    other = client.options(
        "/api/health", headers={**preflight, "Origin": "http://203.0.113.9:3000"}
    )
    assert "access-control-allow-origin" not in other.headers


async def test_spawn_background_holds_the_task_until_it_finishes():
    started, release = asyncio.Event(), asyncio.Event()

    async def work() -> None:
        started.set()
        await release.wait()

    spawn_background(work())
    await asyncio.wait_for(started.wait(), 1)
    assert _background_tasks
    release.set()
    for _ in range(10):
        if not _background_tasks:
            break
        await asyncio.sleep(0)
    assert not _background_tasks
