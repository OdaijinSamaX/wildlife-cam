import os
import time
from datetime import datetime

from app_paths import get_videos_dir
from camera import WildlifeCamera
from link import ChildLinkClient, ParentLinkServer, apply_timestamp
from sensor import MotionSensor
from uploader import DriveUploader, WorkerUploader


def create_uploader(log, *, require_trap_id: bool = True):
    api_url = os.getenv("WILDLIFE_API_URL", "")
    device_token = os.getenv("WILDLIFE_DEVICE_TOKEN", "")
    trap_id = os.getenv("TRAP_ID", "")

    if api_url and device_token and (trap_id or not require_trap_id):
        log.info("Using Cloudflare Worker uploader")
        return WorkerUploader(api_url, device_token, trap_id)

    script_url = os.getenv("GOOGLE_SCRIPT_URL", "")
    if not script_url:
        if api_url and device_token and not trap_id and require_trap_id:
            log.warning("TRAP_ID is missing, so Worker uploader is disabled")
        else:
            log.warning("No uploader env is set -- uploads will fail")
    return DriveUploader(script_url)


def get_node_role() -> str:
    role = os.getenv("WILDLIFE_NODE_ROLE", "standalone").strip().lower()
    return role or "standalone"


def run_standalone(log):
    motion_sensor = MotionSensor()
    camera = WildlifeCamera()
    uploader = create_uploader(log)
    was_armed = None

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
            if not file_path:
                log.warning("Recording returned no file path")
                time.sleep(1)
                continue
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


def run_child(log):
    trap_id = os.getenv("TRAP_ID", "").strip()
    if not trap_id:
        raise RuntimeError("TRAP_ID is required in child mode")

    motion_sensor = MotionSensor()
    camera = WildlifeCamera()
    link_client = ChildLinkClient(trap_id=trap_id)
    arm_state_client = create_uploader(log)
    was_armed = None

    try:
        while True:
            try:
                is_armed = (
                    arm_state_client.is_armed()
                    if isinstance(arm_state_client, WorkerUploader)
                    else link_client.is_armed()
                )
                if is_armed != was_armed:
                    if is_armed:
                        log.info("Trap %s is armed -- resuming motion detection", trap_id)
                    else:
                        log.info("Trap %s is disarmed -- skipping motion detection", trap_id)
                    was_armed = is_armed

                if not is_armed:
                    time.sleep(5)
                    continue
            except Exception as exc:
                log.warning("Failed to fetch arm state: %s", exc)
                time.sleep(5)
                continue

            motion_detected = motion_sensor.wait_for_sustained_motion(
                1.0,
                should_continue=(
                    arm_state_client.is_armed
                    if isinstance(arm_state_client, WorkerUploader)
                    else link_client.is_armed
                ),
            )
            if not motion_detected:
                if was_armed is not False:
                    log.info("Trap %s changed to disarmed while waiting for motion", trap_id)
                    was_armed = False
                continue

            log.info("Motion detected on child node -- starting recording")
            file_path = camera.record_clip(get_videos_dir(), 10)
            if not file_path:
                log.warning("Recording returned no file path")
                time.sleep(1)
                continue
            log.info("Recording complete on child node: %s", file_path)

            captured_at = datetime.fromtimestamp(os.path.getmtime(file_path)).astimezone().isoformat()
            success = link_client.send_video(
                file_path,
                trap_id=trap_id,
                captured_at=captured_at,
            )
            if success:
                os.remove(file_path)
                log.info("Parent relay OK, local child file deleted: %s", file_path)
            else:
                log.info("Parent relay FAILED, child file retained: %s", file_path)

            time.sleep(0.5)
    finally:
        try:
            camera._camera.close()
            log.info("Camera closed")
        except Exception:
            pass


def run_parent(log):
    uploader = create_uploader(log, require_trap_id=False)
    server = ParentLinkServer()

    def handle_request(request, file_path):
        action = request.get("action")
        request_trap_id = (request.get("trap_id") or "").strip() or None
        if action == "get_arm_state":
            if isinstance(uploader, WorkerUploader):
                if not request_trap_id:
                    raise RuntimeError("get_arm_state request did not include trap_id")
                is_armed = uploader.is_armed(trap_id=request_trap_id, cache_ttl_seconds=0.0)
            else:
                is_armed = True
            return {"ok": True, "is_armed": is_armed}

        if action == "upload_video":
            if not file_path:
                raise RuntimeError("upload_video request did not include a file payload")
            apply_timestamp(file_path, request.get("captured_at"))
            success = uploader.upload(
                file_path,
                trap_id=request_trap_id,
                captured_at=request.get("captured_at") or None,
                source_filename=request.get("filename") or None,
            )
            if success:
                os.remove(file_path)
                log.info("Parent upload OK, relay file deleted: %s", file_path)
            else:
                log.warning("Parent upload FAILED, relay file retained: %s", file_path)
            return {
                "ok": success,
                "accepted_at": datetime.now().astimezone().isoformat(),
                "error": None if success else "Parent uploader failed",
            }

        raise RuntimeError(f"Unsupported action: {action}")

    server.serve_forever(handle_request)


def run_role(role: str, log) -> None:
    log.info("Wildlife Camera System starting in %s mode...", role)

    if role == "parent":
        log.info("Parent node ready. Waiting for child node connections...")
        run_parent(log)
        return

    if role == "child":
        log.info("Child node ready. Monitoring for motion...")
        run_child(log)
        return

    log.info("Standalone node ready. Monitoring for motion...")
    run_standalone(log)
