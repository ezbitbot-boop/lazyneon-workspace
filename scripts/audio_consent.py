"""Single consent boundary for all external audio transcription providers."""
def require_audio_upload_consent(allow_upload: bool = False) -> None:
    if allow_upload is not True:
        raise PermissionError("External audio transmission requires explicit --upload-audio consent.")
