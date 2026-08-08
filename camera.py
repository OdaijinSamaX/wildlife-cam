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

try:
    # AfMode の列挙は libcamera 側にある。無い/古い環境でも整数値で代替する。
    from libcamera import controls as _libcontrols
except ImportError:
    _libcontrols = None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
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
        # レンズ焦点位置(ジオプター=1/焦点距離[m])。既定は過焦点寄りに固定する。詳細は _apply_fixed_focus。
        self._lens_position = _env_float("WILDLIFE_LENS_POSITION", 0.5)
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
        self._apply_fixed_focus()

    def _apply_fixed_focus(self) -> None:
        """レンズ焦点を手動で固定する。

        Camera Module 3 (NoIR/標準) は起動時にオートフォーカスを実行せず、
        LensPosition を無指定のままだとレンズが既定位置(約1m相当)に留まる。
        罠の実距離は 3〜5m 以遠のため、そのままでは被写体が常に甘くなる。
        ここで AfMode=Manual と LensPosition を明示し、~1m から無限遠までを
        被写界深度に収める過焦点寄りの位置へ固定する。

        LensPosition の単位はジオプター(= 1/焦点距離[m])。
        既定 0.5 dioptre ≒ 焦点 2m。CM3 標準(f=4.74mm, F1.8, IMX708)の
        過焦点距離 H は許容錯乱円 c≈0.003mm として
        H ≒ f²/(F·c) ≒ 4.74² / (1.8×0.003) ≒ 4m 前後。
        焦点を 2〜4m に置くと 3〜5m の罠と無限遠の双方が実用上シャープに入る。
        既定を過焦点そのもの(≒0.25)より近い 0.5 にしているのは、
        近距離側(1〜3m)を確実に捉えることを優先したため。遠側が甘い場合は
        WILDLIFE_LENS_POSITION を 0.25(≒4m)〜0.6(≒1.7m) の範囲で下げて詰める。
        (8/9 実機 A/B で確定予定。)

        出典: picamera2 マニュアル(LensPosition はジオプター指定)、
        Raspberry Pi Camera Module 3 データシート(IMX708, f=4.74mm / F1.8)。

        AF 非搭載カメラ(v2 / HQ 等)は LensPosition 制御を持たず例外になるため、
        警告を出して既定レンズのまま続行する(録画自体は落とさない)。
        """
        if self._stub or not self._camera:
            return
        try:
            af_manual = 0  # AfModeEnum.Manual 相当のフォールバック値
            if _libcontrols is not None:
                af_manual = _libcontrols.AfModeEnum.Manual
            self._camera.set_controls(
                {"AfMode": af_manual, "LensPosition": self._lens_position}
            )
            focus_m = 1.0 / self._lens_position if self._lens_position > 0 else float("inf")
            self._log.info(
                "Fixed focus applied: LensPosition=%.3f dioptre (~%.1f m), AfMode=Manual",
                self._lens_position,
                focus_m,
            )
        except Exception:
            self._log.warning(
                "Fixed focus not applied (camera may lack autofocus); "
                "continuing with default lens position",
                exc_info=True,
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
