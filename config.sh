# Optional shared model root. Set SOCIAL_NEXUS_MODELS_DIR in the environment
# to the same library root used by Social Music Beat.
if [ -n "${SOCIAL_NEXUS_MODELS_DIR:-}" ]; then
  export SOCIAL_SOUND_MODELS_DIR="${SOCIAL_NEXUS_MODELS_DIR}/LLM"
  export HF_HOME="${SOCIAL_NEXUS_MODELS_DIR}/HuggingFace"
  export HF_HUB_CACHE="${SOCIAL_NEXUS_MODELS_DIR}/HuggingFace/hub"
  export HUGGINGFACE_HUB_CACHE="${SOCIAL_NEXUS_MODELS_DIR}/HuggingFace/hub"
  export TRANSFORMERS_CACHE="${SOCIAL_NEXUS_MODELS_DIR}/HuggingFace/hub"
  export TORCH_HOME="${SOCIAL_NEXUS_MODELS_DIR}/Torch"
fi

# Optional manual GGUF directory when not using the shared library:
# export SOCIAL_SOUND_MODELS_DIR="$HOME/IA_MODELS/LLM"
# Optional: force CPU mode for VoxCPM2:
# export DEVICE=cpu
# On Apple Silicon, DEVICE=mps may work, but has not been tested.
