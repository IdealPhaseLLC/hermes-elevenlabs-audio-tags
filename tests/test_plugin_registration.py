import importlib.util
import sys
from pathlib import Path


def _load_plugin_module():
    """Load this repository's plugin package without relying on the CWD."""
    package_name = "elevenlabs_audio_tags_plugin_under_test"
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        package_name,
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module


def test_plugin_registers_a_tag_task_that_follows_the_main_model():
    plugin = _load_plugin_module()
    calls = []

    class Context:
        def register_auxiliary_task(self, **kwargs):
            calls.append(("aux", kwargs))

        def register_tts_provider(self, provider):
            calls.append(("tts", provider))

        def get_config(self, key, default=None):
            return default

    plugin.register(Context())

    kind, aux = calls[0]
    assert kind == "aux"
    assert aux["key"] == "idealphase_elevenlabs_audio_tags"
    assert aux["defaults"] == {"timeout": 15}
    assert "provider" not in aux["defaults"]
    assert "model" not in aux["defaults"]
    assert calls[1][0] == "tts"
