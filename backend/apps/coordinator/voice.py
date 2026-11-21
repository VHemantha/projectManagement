"""Speaking to the Practice Manager AI (AFIT, 21 Nov 2026): a recording from the browser is turned into text
by Amazon Transcribe, and the text is put in the message box for the person to check and send - so a
spoken "create a job for ..." works exactly like a typed one.

The recording is uploaded to a private S3 bucket (VOICE_TRANSCRIBE_BUCKET), transcribed in New Zealand
English, and deleted with its transcript straight after (the bucket also expires anything left after a
day). The server's instance role gives the access; no keys are stored in the app.
"""
import json
import time
import uuid

from django.conf import settings

FORMATS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
           "audio/flac": "flac", "audio/m4a": "m4a", "audio/x-m4a": "m4a"}
MAX_BYTES = 10 * 1024 * 1024  # about ten minutes of speech
WAIT_SECONDS = 90


class VoiceUnavailable(Exception):
    """Speech can't be turned into text just now (not set up, or AWS refused): say so plainly."""


def media_format(content_type: str, name: str = "") -> str | None:
    base = (content_type or "").split(";")[0].strip().lower()
    if base in FORMATS:
        return FORMATS[base]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext if ext in set(FORMATS.values()) else None


def transcribe(data: bytes, fmt: str) -> str:
    """The words spoken in the recording."""
    bucket = getattr(settings, "VOICE_TRANSCRIBE_BUCKET", "")
    if not bucket:
        raise VoiceUnavailable("Speaking to the Practice Manager AI isn't set up on this server yet. Type your message instead.")
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    region = getattr(settings, "VOICE_TRANSCRIBE_REGION", "ap-south-1")
    s3, transcribe_client = boto3.client("s3", region_name=region), boto3.client("transcribe", region_name=region)
    job = f"tasko-voice-{uuid.uuid4().hex}"
    key, out_key = f"voice/{job}.{fmt}", f"voice/{job}.json"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=data, ServerSideEncryption="AES256")
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job, Media={"MediaFileUri": f"s3://{bucket}/{key}"}, MediaFormat=fmt,
            LanguageCode=getattr(settings, "VOICE_TRANSCRIBE_LANGUAGE", "en-NZ"), OutputBucketName=bucket, OutputKey=out_key)
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            status = transcribe_client.get_transcription_job(TranscriptionJobName=job)["TranscriptionJob"]["TranscriptionJobStatus"]
            if status == "COMPLETED":
                break
            if status == "FAILED":
                raise VoiceUnavailable("The recording couldn't be understood. Try again, a little closer to the microphone.")
            if time.monotonic() > deadline:
                raise VoiceUnavailable("Turning the recording into text took too long. Try a shorter message, or type it.")
            time.sleep(1.5)
        result = json.loads(s3.get_object(Bucket=bucket, Key=out_key)["Body"].read())
        return " ".join(t.get("transcript", "") for t in result.get("results", {}).get("transcripts", [])).strip()
    except (BotoCoreError, ClientError) as exc:
        raise VoiceUnavailable("Amazon Transcribe couldn't be reached just now. Type your message instead.") from exc
    finally:
        for k in (key, out_key):
            try:
                s3.delete_object(Bucket=bucket, Key=k)
            except Exception:  # noqa: BLE001 - the bucket's lifecycle rule removes what is left
                pass
        try:
            transcribe_client.delete_transcription_job(TranscriptionJobName=job)
        except Exception:  # noqa: BLE001
            pass
