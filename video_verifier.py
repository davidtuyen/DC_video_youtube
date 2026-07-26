import os
import platform
import subprocess
import json
import shutil
import sys
from tinytag import TinyTag, TinyTagException

# --- Global Variables ---
FFPROBE_CMD_TO_USE = None
FFMPEG_CMD_TO_USE = None


def get_script_directory():
    if "__file__" in globals() and os.path.exists(__file__):
        return os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


SCRIPT_BASE_DIR = get_script_directory()
LOCAL_FFMPEG_DATA_DIR = os.path.join(SCRIPT_BASE_DIR, "data", "ffmpeg", "bin")


def _find_ffmpeg_tool(tool_name: str) -> str | None:
    tool_filename = f"{tool_name}.exe" if platform.system() == "Windows" else tool_name
    local_tool_path = os.path.join(LOCAL_FFMPEG_DATA_DIR, tool_filename)
    if os.path.exists(local_tool_path) and os.access(local_tool_path, os.X_OK):
        return local_tool_path
    return shutil.which(tool_name)


def initialize_ffmpeg_paths():
    global FFPROBE_CMD_TO_USE, FFMPEG_CMD_TO_USE
    if FFPROBE_CMD_TO_USE is None:
        FFPROBE_CMD_TO_USE = _find_ffmpeg_tool("ffprobe")
    if FFMPEG_CMD_TO_USE is None:
        FFMPEG_CMD_TO_USE = _find_ffmpeg_tool("ffmpeg")
    return FFPROBE_CMD_TO_USE, FFMPEG_CMD_TO_USE


class VerificationResult:
    def __init__(self):
        self.success = False
        self.file_readable = False
        self.verified_duration = None
        self.verified_title = None
        self.verified_resolution = None
        self.video_stream_exists = False
        self.audio_stream_exists = False
        self.error_message = None
        self.raw_ffprobe_output = None

    def __str__(self):
        return (
            f"VerificationResult(success={self.success}, readable={self.file_readable}, "
            f"duration={self.verified_duration}, title='{self.verified_title}', "
            f"video_stream={self.video_stream_exists}, audio_stream={self.audio_stream_exists}, "
            f"error='{self.error_message}')"
        )


def verify_video_file(file_path: str, process_callback=None) -> VerificationResult:
    if FFPROBE_CMD_TO_USE is None:
        initialize_ffmpeg_paths()

    result = VerificationResult()
    if not os.path.exists(file_path):
        result.error_message = f"File not found: {file_path}"
        return result

    # --- STRATEGY 1: FFPROBE (Primary) ---
    if FFPROBE_CMD_TO_USE:
        try:
            cmd = [
                FFPROBE_CMD_TO_USE,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]
            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "encoding": "utf-8",
                "creationflags": subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            }
            if platform.system() != "Windows":
                popen_kwargs["start_new_session"] = True
            process = subprocess.Popen(cmd, **popen_kwargs)
            if process_callback:
                process_callback(process)
            stdout, _ = process.communicate(timeout=20)

            if process.returncode == 0:
                data = json.loads(stdout)
                result.success = True
                result.file_readable = True
                result.raw_ffprobe_output = stdout

                if "format" in data and "duration" in data["format"]:
                    try:
                        result.verified_duration = float(data["format"]["duration"])
                    except (TypeError, ValueError):
                        pass

                if "format" in data and "tags" in data["format"]:
                    result.verified_title = data["format"]["tags"].get("title")

                if "streams" in data:
                    for stream in data["streams"]:
                        if stream.get("codec_type") == "video":
                            result.video_stream_exists = True
                            width = stream.get("width")
                            height = stream.get("height")
                            if width and height and not result.verified_resolution:
                                result.verified_resolution = f"{width}x{height}"
                        elif stream.get("codec_type") == "audio":
                            result.audio_stream_exists = True

                if not result.verified_resolution and result.video_stream_exists:
                    result.verified_resolution = "Video (Res N/A)"
                elif not result.video_stream_exists and result.audio_stream_exists:
                    result.verified_resolution = "Audio Only"

                result.error_message = None
                return result
        except Exception as e:
            result.error_message = f"FFprobe failed: {e}. Trying fallback..."

    # --- STRATEGY 2: TINYTAG (Fallback) ---
    try:
        tag = TinyTag.get(file_path)
        result.success = True
        result.file_readable = True
        result.verified_duration = getattr(tag, "duration", None)
        result.verified_title = getattr(tag, "title", None)
        width = getattr(tag, "width", None)
        height = getattr(tag, "height", None)
        if width and height:
            result.verified_resolution = f"{width}x{height}"
            result.video_stream_exists = True
        else:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in [".mp4", ".mkv", ".webm", ".avi"]:
                result.verified_resolution = "Video (TinyTag)"
                result.video_stream_exists = True
            else:
                result.verified_resolution = "Audio Only"
                result.audio_stream_exists = True
        result.error_message = None
    except (TinyTagException, OSError) as e:
        result.success = False
        result.error_message = f"All verifiers failed. TinyTag error: {e}"
    except Exception as e:
        result.success = False
        result.error_message = f"Unexpected verification failure: {e}"

    return result
