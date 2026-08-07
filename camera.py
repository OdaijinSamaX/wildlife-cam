import datetime
import logging
import os
import time
from app_paths import get_videos_dir

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FfmpegOutput
except ImportError:
    Picamera2 = None
    H264Encoder = None
    FfmpegOutput = None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


class WildlifeCamera:
    """録画用カメラ。

    Pi Zero 2 W(実メモリ424MB)向けに既定構成を絞っている。
    create_video_configuration は既定でセンサ解像度のRAWストリームを併走させ、
    1フレーム約6MBをバッファ枚数ぶん確保する。これが実メモリを食い潰し、
    エンコーダとの間でデッドロック(futex待ち)を起こしてプロセスが固まる。
    実測では raw=None を指定するだけで 720p/1080p いずれも安定して録画できた。
    """

    def __init__(self):
        self._log = logging.getLogger("wildlife_cam")
        self._width = _env_int("CAMERA_WIDTH", 1280)
        self._height = _env_int("CAMERA_HEIGHT", 720)
        self._bitrate = _env_int("CAMERA_BITRATE", 3_000_000)
        self._buffer_count = _env_int("CAMERA_BUFFER_COUNT", 4)
        self._camera = None

        if Picamera2 is None:
            self._stub = True
            self._log.warning("picamera2 not available - running in stub mode")
            return

        self._stub = False
        self._camera = Picamera2()
        config = self._camera.create_video_configuration(
            main={"size": (self._width, self._height), "format": "YUV420"},
            raw=None,
            buffer_count=self._buffer_count,
        )
        self._camera.configure(config)
        self._log.info(
            "Camera configured: %dx%d YUV420 (raw stream disabled, buffers=%d)",
            self._width,
            self._height,
            self._buffer_count,
        )

    def record_clip(
        self,
        output_dir: str | None = None,
        duration: int = 10,
    ) -> str:
        if self._stub:
            self._log.warning("Camera stub - cannot record")
            return ""

        if not output_dir:
            output_dir = get_videos_dir()
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(output_dir, f"clip_{timestamp}.mp4")
        # RTCなしで時刻が戻った場合や同秒の再録画でも既存動画を上書きしない。
        sequence = 1
        while os.path.exists(filepath):
            filepath = os.path.join(output_dir, f"clip_{timestamp}_{sequence:02d}.mp4")
            sequence += 1

        encoder = H264Encoder(bitrate=self._bitrate)
        output = FfmpegOutput(filepath)
        started = False
        try:
            self._camera.start_recording(encoder, output)
            started = True
            time.sleep(duration)
        except Exception:
            self._log.exception("Recording failed")
            raise
        finally:
            if started:
                try:
                    self._camera.stop_recording()
                except Exception:
                    self._log.exception("stop_recording failed")

        # 空ファイルを後段が拾って送信を試みるのを防ぐ。
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            self._log.error("Recording produced no data: %s", filepath)
            if os.path.exists(filepath):
                os.remove(filepath)
            return ""

        self._log.info(
            "Recorded %s (%.2f MB)", filepath, os.path.getsize(filepath) / 1048576
        )
        return filepath

    def close(self) -> None:
        """カメラを確実に解放する。

        解放し損ねると /dev/video* を掴んだままになり、次回以降
        'Device or resource busy' で撮影できなくなる。
        """
        if self._stub or not self._camera:
            return
        try:
            self._camera.close()
        except Exception:
            self._log.exception("Camera close failed")
        finally:
            self._camera = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
