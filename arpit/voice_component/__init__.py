import streamlit.components.v1 as components

_voice_recorder = components.declare_component(
    "voice_recorder",
    path="./voice_component/frontend"
)


def voice_recorder(key=None):
    """Custom component for voice recording with speech-to-text.
    Returns transcribed text or None."""
    result = _voice_recorder(key=key, default=None)
    return result
