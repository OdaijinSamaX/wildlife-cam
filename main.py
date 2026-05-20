import os
import time
from dotenv import load_dotenv

from app_paths import get_env_file, get_videos_dir

load_dotenv(get_env_file())

from logger import get_logger
from sensor import MotionSensor
from camera import WildlifeCamera
from uploader import DriveUploader, WorkerUploader


def create_uploader(log):
    api_url = os.getenv("WILDLIFE_API_URL", "")
    device_token = os.getenv("WILDLIFE_DEVICE_TOKEN", "")
    trap_id = os.getenv("TRAP_ID", "")

    if api_url and device_token and trap_id:
        log.info("Using Cloudflare Worker uploader")
        return WorkerUploader(api_url, device_token, trap_id)

    script_url = os.getenv("GOOGLE_SCRIPT_URL", "")
    if not script_url:
        log.warning("No uploader env is set -- uploads will fail")
    return DriveUploader(script_url)


def main():
    log = get_logger("wildlife_cam")
    log.info("Wildlife Camera System starting...")

    motion_sensor = MotionSensor()
    camera = WildlifeCamera()
    uploader = create_uploader(log)
    was_armed = None

    log.info("System ready. Monitoring for motion...")

    try:
        while True:
            if isinstance(uploader, WorkerUploader):
                try:
                    is_armed = uploader.is_armed()
                    if is_armed != was_armed:
                        if is_armed:
                            log.info("Trap %s is armed -- resuming motion detection", uploader.trap_id)
                        else:
                            log.info("Trap %s is disarmed -- skipping motion detection", uploader.trap_id)
                        was_armed = is_armed

                    if not is_armed:
                        time.sleep(5)
                        continue
                except Exception as exc:
                    log.warning("Failed to fetch trap arm state: %s", exc)
                    time.sleep(5)
                    continue

                motion_detected = motion_sensor.wait_for_sustained_motion(
                    1.0,
                    should_continue=uploader.is_armed,
                )
                if not motion_detected:
                    if was_armed is not False:
                        log.info("Trap %s changed to disarmed while waiting for motion", uploader.trap_id)
                        was_armed = False
                    continue
            else:
                motion_sensor.wait_for_sustained_motion(1.0)

            log.info("Motion detected -- starting recording")

            file_path = camera.record_clip(get_videos_dir(), 10)
            log.info("Recording complete: %s", file_path)

            success = uploader.upload(file_path)
            if success:
                os.remove(file_path)
                log.info("Upload OK, local file deleted: %s", file_path)
            else:
                log.info("Upload FAILED, file retained: %s", file_path)

            time.sleep(0.5)
    finally:
        try:
            camera._camera.close()
            log.info("Camera closed")
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log = get_logger("wildlife_cam")
        log.info("Shutting down...")
