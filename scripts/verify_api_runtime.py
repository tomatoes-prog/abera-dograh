"""Offline smoke check for the production API image; no provider credentials needed."""

import importlib
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import wave


def run(*args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT)


for tool in ("gcc", "g++", "make", "git", "npm", "yarn", "uv"):
    assert shutil.which(tool) is None, f"Build tool leaked into runtime: {tool}"
for module in ("av", "aiortc", "pipecat.transports.smallwebrtc.transport", "onnxruntime", "numba", "soundfile", "api.app"):
    importlib.import_module(module)
assert importlib.util.find_spec("cv2") is None, "Video dependency leaked into voice-only runtime"
for binary in ("ffmpeg", "ffprobe", "node"):
    assert b"not found" not in run("ldd", shutil.which(binary))

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / "source.wav"
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 440 * n / 48000))) for n in range(48000)))
    for suffix, codec in (("mp3", "libmp3lame"), ("ogg", "libopus"), ("flac", "flac"), ("aac", "aac")):
        encoded = root / f"roundtrip.{suffix}"
        run("ffmpeg", "-v", "error", "-i", str(source), "-c:a", codec, str(encoded))
        run("ffprobe", "-v", "error", "-show_streams", str(encoded))
        pcm = run("ffmpeg", "-v", "error", "-i", str(encoded), "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1")
        assert len(pcm) > 30000, f"Empty or truncated audio: {suffix}"
    stereo = root / "stereo.mp3"
    run("ffmpeg", "-v", "error", "-i", str(source), "-ac", "2", "-codec:a", "libmp3lame", str(stereo))
    assert stereo.stat().st_size > 1000

# The TypeScript validator needs Node itself, but no package manager.
assert run("node", "--version").startswith(b"v22.")
print("API runtime passed: imports, shared libraries, audio codecs, resampling, Node, no build tools")
