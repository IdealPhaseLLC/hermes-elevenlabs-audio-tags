"""Run this suite without a Hermes install, and use Hermes when it is present.

The tests check this plugin's behavior. They already fake ElevenLabs and the
model call. They are not a Hermes integration test. When ``agent`` imports,
those real classes stay in place, so a Hermes checkout still exercises the
current base class. When it does not, this installs an import anchor so
``provider.py`` can subclass ``TTSProvider`` and the auxiliary-client test can
patch its call sites. That anchor does not prove the plugin still loads inside
Hermes. ``hermes plugins doctor`` does.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from types import ModuleType
from typing import Any


def _install_agent_stub() -> None:
    agent = ModuleType("agent")
    agent.__path__ = []

    provider_base = ModuleType("agent.provider_base")

    class ProviderBase(ABC):
        @property
        @abstractmethod
        def name(self) -> str:
            raise NotImplementedError

    class CatalogProviderBase(ProviderBase):
        def is_available(self) -> bool:
            return True

        def get_setup_schema(self) -> dict[str, Any]:
            return {}

    setattr(provider_base, "ProviderBase", ProviderBase)
    setattr(provider_base, "CatalogProviderBase", CatalogProviderBase)

    tts = ModuleType("agent.tts_provider")

    class TTSProvider(CatalogProviderBase):
        @abstractmethod
        def synthesize(self, text: str, output_path: str, **kwargs: Any) -> str:
            raise NotImplementedError

        @property
        def voice_compatible(self) -> bool:
            return False

    setattr(tts, "TTSProvider", TTSProvider)

    auxiliary = ModuleType("agent.auxiliary_client")

    def _missing(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Hermes auxiliary client is not installed")

    setattr(auxiliary, "_get_auxiliary_task_config", _missing)
    setattr(auxiliary, "resolve_provider_client", _missing)
    setattr(auxiliary, "call_llm", _missing)

    setattr(agent, "provider_base", provider_base)
    setattr(agent, "tts_provider", tts)
    setattr(agent, "auxiliary_client", auxiliary)
    sys.modules["agent"] = agent
    sys.modules["agent.provider_base"] = provider_base
    sys.modules["agent.tts_provider"] = tts
    sys.modules["agent.auxiliary_client"] = auxiliary


def _install_auxiliary_stub() -> None:
    auxiliary = ModuleType("agent.auxiliary_client")

    def _missing(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Hermes auxiliary client is not installed")

    setattr(auxiliary, "_get_auxiliary_task_config", _missing)
    setattr(auxiliary, "resolve_provider_client", _missing)
    setattr(auxiliary, "call_llm", _missing)
    agent = sys.modules.get("agent")
    if agent is not None:
        setattr(agent, "auxiliary_client", auxiliary)
    sys.modules["agent.auxiliary_client"] = auxiliary


def pytest_configure() -> None:
    try:
        import agent.tts_provider  # noqa: F401
    except ImportError:
        _install_agent_stub()
        return
    try:
        import agent.auxiliary_client  # noqa: F401
    except ImportError:
        _install_auxiliary_stub()
