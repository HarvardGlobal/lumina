import importlib.util
from pathlib import Path

import pytest

def load_components_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "components.py"
    spec = importlib.util.spec_from_file_location("lumina_components", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_component_manifest_uses_immutable_full_shas(monkeypatch, tmp_path):
    module = load_components_module()
    monkeypatch.setenv("LUMINA_COMPONENTS_DIR", str(tmp_path / "components"))
    components = module.parse_manifest()

    assert [component["name"] for component in components] == [
        "promop",
        "lumina-wearables",
        "open-wearables",
    ]
    assert all(module.SHA.fullmatch(component["git_ref"]) for component in components)
    assert module.REQUIRED_FILES["open-wearables"] == ("docker-compose.yml", "backend/app/main.py")
    assert {component["name"]: component.get("version") for component in components} == {
        "promop": None,
        "lumina-wearables": "1.1.5",
        "open-wearables": "0.7.0",
    }
    assert module.components_dir() == tmp_path / "components"


def test_open_wearables_layout_requires_declared_release_version(tmp_path):
    module = load_components_module()
    target = tmp_path / "open-wearables"
    (target / "backend" / "app").mkdir(parents=True)
    (target / "docker-compose.yml").touch()
    (target / "backend" / "app" / "main.py").touch()
    pyproject = target / "backend" / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "0.7.0"\n')
    component = {"name": "open-wearables", "git_ref": "a" * 40, "version": "0.7.0"}

    module.validate_layout(component, target)

    pyproject.write_text('[project]\nversion = "0.7.1"\n')
    with pytest.raises(RuntimeError, match="expected '0.7.0'"):
        module.validate_layout(component, target)
