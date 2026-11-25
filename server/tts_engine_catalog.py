"""Reviewed TTS engine catalogue; metadata is separate from engine runtimes."""
from __future__ import annotations

REVIEWED_ON = "2026-11-25"

ENGINES = [
    {
        "id": "voxcpm2",
        "name": "VoxCPM2",
        "model": "openbmb/VoxCPM2",
        "code_license": "Apache-2.0",
        "weights_license": "Apache-2.0",
        "commercial_use": True,
        "commercial_label": "Comercial permitido",
        "category": "commercial",
        "installed": True,
        "voice_cloning": True,
        "notes": "Motor atualmente integrado. A licença permite uso comercial; o cartão do modelo proíbe impersonação, fraude e desinformação e recomenda identificar conteúdo gerado por IA.",
        "model_url": "https://huggingface.co/openbmb/VoxCPM2",
        "code_url": "https://github.com/OpenBMB/VoxCPM",
        "license_url": "https://huggingface.co/openbmb/VoxCPM2",
    },
    {
        "id": "supertonic3",
        "name": "Supertonic 3",
        "model": "Supertone/supertonic-3",
        "package": "supertonic==1.3.1",
        "code_license": "MIT",
        "weights_license": "OpenRAIL-M",
        "commercial_use": True,
        "commercial_label": "Comercial permitido com restrições de uso",
        "category": "commercial",
        "installed": False,
        "voice_cloning": False,
        "notes": "Modelo ONNX leve, 31 idiomas incluindo português e 10 vozes predefinidas. O SDK Python oficial foi arquivado em setembro de 2026; a versão 1.3.1 permanece disponível, sem novas correções ou suporte. OpenRAIL-M impõe restrições de uso, inclusive contra impersonação sem consentimento e conteúdo enganoso.",
        "model_url": "https://huggingface.co/Supertone/supertonic-3",
        "code_url": "https://github.com/supertone-oss-archive/supertonic-py",
        "license_url": "https://huggingface.co/Supertone/supertonic-3/blob/main/LICENSE",
    },
    {
        "id": "omnivoice",
        "name": "OmniVoice",
        "model": "k2-fsa/OmniVoice",
        "code_license": "Apache-2.0",
        "weights_license": "CC-BY-NC",
        "commercial_use": False,
        "commercial_label": "Somente uso não comercial",
        "category": "non_commercial",
        "installed": False,
        "voice_cloning": True,
        "notes": "O código é Apache-2.0, mas os pesos oficiais são CC-BY-NC por restrições dos dados de treinamento. Não usar para conteúdo monetizado ou outras finalidades comerciais sem autorização/licença diferente.",
        "model_url": "https://huggingface.co/k2-fsa/OmniVoice",
        "code_url": "https://github.com/k2-fsa/OmniVoice",
        "license_url": "https://huggingface.co/k2-fsa/OmniVoice",
    },
    {
        "id": "f5tts",
        "name": "F5-TTS",
        "model": "Cataldir/F5-TTS-pt-br",
        "code_license": "MIT",
        "weights_license": "CC-BY-NC-4.0",
        "commercial_use": False,
        "commercial_label": "Somente uso não comercial",
        "category": "non_commercial",
        "installed": False,
        "voice_cloning": True,
        "notes": "Checkpoint comunitário ajustado para português brasileiro, usando a API oficial F5-TTS. Pesos CC-BY-NC-4.0: somente uso não comercial. O checkpoint não é mantido pelo projeto oficial e a qualidade deve ser validada antes de uso em produção.",
        "model_url": "https://huggingface.co/Cataldir/F5-TTS-pt-br",
        "code_url": "https://github.com/SWivid/F5-TTS",
        "license_url": "https://huggingface.co/Cataldir/F5-TTS-pt-br",
    },
]


def public_catalog(*, supertonic_installed: bool = False, omnivoice_installed: bool = False, f5tts_installed: bool = False) -> list[dict]:
    return [
        dict(engine, installed=(supertonic_installed if engine["id"] == "supertonic3" else omnivoice_installed if engine["id"] == "omnivoice" else f5tts_installed if engine["id"] == "f5tts" else engine["installed"]),
             reviewed_on=REVIEWED_ON)
        for engine in ENGINES
    ]
