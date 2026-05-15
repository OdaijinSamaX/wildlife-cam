import datetime
import logging
import os
import time

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FfmpegOutput
except ImportError:
    Picamera2 = None
    H264Encoder = None
    FfmpegOutput = None


class WildlifeCamera:
    def __init__(self):
        self._log = logging.getLogger("wildlife_cam")
        if Picamera2 is None:
            self._stub = True
            self._log.warning("picamera2 not available - running in stub mode")
        else:
            self._stub = False
            self._camera = Picamera2()
            config = self._camera.create_video_configuration(
                main={"size": (1920, 1080)}
            )
            self._camera.configure(config)

    def record_clip(
        self,
        output_dir: str = "/home/pi/wildlife-cam/videos",
        duration: int = 10,
    ) -> str:
        if self._stub:
            self._log.warning("Camera stub - cannot record")
            return ""

        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"clip_{timestamp}.mp4"
        filepath = os.path.join(output_dir, filename)

        encoder = H264Encoder()
        output = FfmpegOutput(filepath)
        try:
            self._camera.start_recording(encoder, output)
            time.sleep(duration)
        finally:
            self._camera.stop_recording()

        return filepath

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if not self._stub and self._camera:
            self._camera.close()