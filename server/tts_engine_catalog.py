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
        "code_license": "MIT",
        "weights_license": "OpenRAIL-M",
        "commercial_use": True,
        "commercial_label": "Comercial permitido com restrições de uso",
        "category": "commercial",
        "installed": False,
        "voice_cloning": False,
        "notes": "Modelo ONNX leve com vozes predefinidas. OpenRAIL-M não é uma licença sem restrições: proíbe, entre outros usos, deepfakes sem consentimento, fraude e conteúdo enganoso.",
        "model_url": "https://huggingface.co/Supertone/supertonic-3",
        "code_url": "https://github.com/supertone-oss-archive/supertonic",
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
        "model": "SWivid/F5-TTS",
        "code_license": "MIT",
        "weights_license": "CC-BY-NC-4.0",
        "commercial_use": False,
        "commercial_label": "Somente uso não comercial",
        "category": "non_commercial",
        "installed": False,
        "voice_cloning": True,
        "notes": "O código é MIT, mas os pesos oficiais são CC-BY-NC-4.0. Não usar para conteúdo monetizado ou outras finalidades comerciais sem autorização/licença diferente.",
        "model_url": "https://huggingface.co/SWivid/F5-TTS",
        "code_url": "https://github.com/SWivid/F5-TTS",
        "license_url": "https://huggingface.co/SWivid/F5-TTS",
    },
]


def public_catalog() -> list[dict]:
    return [dict(engine, reviewed_on=REVIEWED_ON) for engine in ENGINES]
