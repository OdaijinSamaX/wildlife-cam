import os
import time
from dotenv import load_dotenv

load_dotenv("/home/pi/wildlife-cam/config/.env")

from logger import get_logger
from sensor import MotionSensor
from camera import WildlifeCamera
from uploader import DriveUploader


def main():
    log = get_logger("wildlife_cam")
    log.info("Wildlife Camera System starting...")

    script_url = os.getenv("GOOGLE_SCRIPT_URL", "")
    if not script_url:
        log.warning("GOOGLE_SCRIPT_URL is not set -- uploads will fail")

    motion_sensor = MotionSensor()
    camera = WildlifeCamera()
    uploader = DriveUploader(script_url)

    log.info("System ready. Monitoring for motion...")

    while True:
        motion_sensor.wait_for_sustained_motion(1.0)
        log.info("Motion detected -- starting recording")

        file_path = camera.record_clip("/home/pi/wildlife-cam/videos", 10)
        log.info("Recording complete: %s", file_path)

        success = uploader.upload(file_path)
        if success:
            os.remove(file_path)
            log.info("Upload OK, local file deleted: %s", file_path)
        else:
            log.info("Upload FAILED, file retained: %s", file_path)

        time.sleep(0.5)


if __name__ == "__main__":
    camera = None
    try:
        from logger import get_logger
        from sensor import MotionSensor
        from camera import WildlifeCamera

        log = get_logger("wildlife_cam")
        log.info("Wildlife Camera System starting...")

        script_url = os.getenv("GOOGLE_SCRIPT_URL", "")
        if not script_url:
            log.warning("GOOGLE_SCRIPT_URL is not set -- uploads will fail")

        motion_sensor = MotionSensor()
        camera = WildlifeCamera()
        uploader = DriveUploader(script_url)

        log.info("System ready. Monitoring for motion...")

        while True:
            motion_sensor.wait_for_sustained_motion(1.0)
            log.info("Motion detected -- starting recording")

            file_path = camera.record_clip("/home/pi/wildlife-cam/videos", 10)
            log.info("Recording complete: %s", file_path)

            success = uploader.upload(file_path)
            if success:
                os.remove(file_path)
                log.info("Upload OK, local file deleted: %s", file_path)
            else:
                log.info("Upload FAILED, file retained: %s", file_path)

            time.sleep(0.5)

    except KeyboardInterrupt:
        log = get_logger("wildlife_cam")
        log.info("Shutting down...")
        if camera is not None:
            try:
                camera._camera.close()
                log.info("Camera closed")
            except Exception:
                pass