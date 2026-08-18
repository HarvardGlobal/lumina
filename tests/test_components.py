import importlib.util
from pathlib import Path


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
    assert module.components_dir() == tmp_path / "components"
