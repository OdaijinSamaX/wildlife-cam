import os
import re
import time
from datetime import datetime

from app_paths import get_videos_dir
from arm_monitor import ArmStateMonitor
from camera import WildlifeCamera
from illuminator import Illuminator
from link import ChildLinkClient, ParentLinkServer, apply_timestamp
from sensor import MotionSensor
from field_limits import FieldLimiter, on_lte
from uploader import DriveUploader, WorkerUploader
from video_storage import (
    clear_retry,
    enforce_limits,
    looks_like_mp4,
    quarantine,
    record_retry,
)
from watchdog import mark_progress


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


def _captured_at_from_path(file_path: str) -> str:
    """clip_YYYYMMDD_HHMMSS.mp4 から撮影時刻を復元する。

    取り残されたクリップを後から送るとき、送信時刻ではなく撮影時刻を
    記録しないと、夜間に撮れたものが翌朝の記録になってしまう。
    命名規則から読めなければファイルの更新時刻で代替する。
    """
    name = os.path.basename(file_path)
    match = re.search(r"(?:^|_)(\d{8})_(\d{6})(?:_|\.|$)", name)
    if match:
        try:
            dt = datetime.strptime(f"{match.group(1)}_{match.group(2)}", "%Y%m%d_%H%M%S")
            return dt.astimezone().isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(os.path.getmtime(file_path)).astimezone().isoformat()


def drain_pending_clips(
    log,
    uploader,
    *,
    skip_newer_than: float = 60.0,
    limit: int = 5,
    limiter: FieldLimiter | None = None,
    is_lte: bool = False,
) -> int:
    """videos/ に取り残されたクリップを送信して回収する。

    強制終了・電源断・送信失敗・送信予算切れで残ったファイルは、これまで誰も拾わなかった。
    起動時とループ先頭で呼ぶことで、撮り逃しを防ぐ。

    skip_newer_than: 直近に更新されたファイルは録画中の可能性があるため触らない。
    limit: 1回の呼び出しで送る上限。溜まっていてもモーション検知を長時間止めない。
    limiter/is_lte: LTE 送信予算のゲートと送信量カウントに使う。

    送信順序: 通常はバックログ解消のため古い順。ただしバックログが閾値を超えたら
    「新しい順」に切り替える。予算上限でバックログが膨らんだとき、実演で見せたい
    「いま撮れた最新の動画」が古い山の後ろに埋もれないようにするため（設計判断は docs 参照）。
    """
    videos_dir = get_videos_dir()
    if not os.path.isdir(videos_dir):
        return 0

    # 保留中クリップの保護と SD 保護の優先順位:
    #   enforce_limits は SD を守るため古い順に削除しうる。送信予算で保留中の動画も
    #   対象になりうるが、予算は最長でも約1時間の遅延にすぎず、既定の保存期間(14日)を
    #   はるかに下回るので通常は消えない。SD が本当に逼迫した場合のみ、端末保護(録画継続)を
    #   優先して古い順に削除する（削除は必ずログに残る。黙って消さない）。
    enforce_limits(log, videos_dir)

    now = time.time()
    pending = []
    for name in os.listdir(videos_dir):
        if not name.endswith(".mp4"):
            continue
        path = os.path.join(videos_dir, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        if stat.st_size == 0:
            # 録画が中断された残骸。送っても意味がないので捨てる。
            log.warning("Removing zero-byte clip: %s", path)
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        if not looks_like_mp4(path):
            try:
                quarantine(log, path, "MP4 header check failed")
            except OSError as exc:
                log.warning("Could not quarantine invalid clip %s: %s", path, exc)
            continue
        if now - stat.st_mtime < skip_newer_than:
            continue
        pending.append((stat.st_mtime, path))

    if not pending:
        return 0

    pending.sort()  # 既定は古い順
    if limiter is not None and limiter.prefer_newest_first(len(pending)):
        pending.reverse()  # バックログ過多時は新しい順
        log.info("Backlog %d clip(s) -- draining newest-first", len(pending))
    else:
        log.info("Found %d pending clip(s) to retry", len(pending))

    sent = 0
    for _, path in pending[:limit]:
        # 送信予算切れ(LTE時)ならこの回は送らず SD に残す。失敗としては数えない。
        if limiter is not None and limiter.upload_blocked_by_budget(is_lte):
            limiter.note_budget_log()
            break
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        try:
            ok = uploader.upload(path, captured_at=_captured_at_from_path(path))
        except Exception as exc:
            log.warning("Retry upload raised for %s: %s", path, exc)
            ok = False
        if ok:
            if limiter is not None:
                limiter.note_uploaded(size, is_lte)
            try:
                os.remove(path)
            except OSError:
                pass
            log.info("Retry upload OK, local file deleted: %s", path)
            clear_retry(path)
            sent += 1
        else:
            max_retries = max(1, int(os.getenv("WILDLIFE_UPLOAD_MAX_RETRIES", "3")))
            retries = record_retry(path)
            if retries >= max_retries:
                try:
                    quarantine(log, path, f"upload failed {retries} times")
                except OSError as exc:
                    log.warning("Could not quarantine failed clip %s: %s", path, exc)
                    break
                # 恒久的に失敗する1本で後続を止めない。
                continue
            log.warning(
                "Retry upload still failing (%d/%d), keeping: %s",
                retries,
                max_retries,
                path,
            )
            # 多数同時失敗は通信断とみなし、この回はここで止める。
            break

    remaining = len(pending) - sent
    if remaining > 0:
        log.info("%d clip(s) still pending", remaining)
    return sent


def run_standalone(log):
    motion_sensor = MotionSensor()
    camera = WildlifeCamera()
    illuminator = Illuminator()
    uploader = create_uploader(log)
    was_armed = None
    limiter = FieldLimiter(log)
    enforce_limits(log, get_videos_dir())

    # 安全思想「通信断=保留(作動しない)」は WorkerUploader 経路でしか成立しない。
    # 設定不備で DriveUploader に落ちると arm ゲートが消え、無条件に撮影し続ける。
    # 静かに安全機構を失うより、起動時に気づける形にする。
    if not isinstance(uploader, WorkerUploader):
        log.warning(
            "Uploader is %s, not WorkerUploader -- the arm gate and "
            "comms-loss hold are NOT active. Check WILDLIFE_API_URL / "
            "WILDLIFE_DEVICE_TOKEN / TRAP_ID in config/.env",
            type(uploader).__name__,
        )
        if os.getenv("WILDLIFE_REQUIRE_ARM_GATE", "1").strip() != "0":
            raise RuntimeError(
                "Arm gate unavailable (uploader is not WorkerUploader). "
                "Fix config/.env, or set WILDLIFE_REQUIRE_ARM_GATE=0 to run without it."
            )

    # arm 状態は背景スレッドで定期取得し、検知ループはメモリ値だけを読む。
    # 待機ループから毎回ブロッキング HTTP を呼ぶと、LTE で v6 がブラックホール化した
    # 際に 1 周が最長 30 秒ブロックし、PIR サンプリング周期が壊れて sustained motion が
    # 成立しなくなる (2026-08-08 障害)。通信断=保留の安全思想は monitor 側で維持する。
    arm_monitor = (
        ArmStateMonitor(uploader, log=log)
        if isinstance(uploader, WorkerUploader)
        else None
    )
    if arm_monitor is not None:
        arm_monitor.start()

    # 前回の稼働で取り残されたクリップを先に回収する。
    # 電源断や強制終了で残ったファイルは、これまで永久に放置されていた。
    try:
        drain_pending_clips(log, uploader, skip_newer_than=0.0, limiter=limiter, is_lte=on_lte())
    except Exception:
        log.exception("Startup drain failed - continuing anyway")

    try:
        while True:
            mark_progress()
            limiter.maybe_resume_breaker()
            lte = on_lte()
            try:
                drain_pending_clips(log, uploader, limiter=limiter, is_lte=lte)
            except Exception:
                log.exception("Pending clip drain failed - continuing anyway")

            if arm_monitor is not None:
                # 背景スレッドが更新したメモリ値のみを読む。ここでは通信しない。
                arm_state = arm_monitor.state()
                is_armed = arm_state == "armed"
                if is_armed != was_armed:
                    if is_armed:
                        log.info("Trap %s is armed -- resuming motion detection", uploader.trap_id)
                    else:
                        log.info("Trap %s is disarmed -- skipping motion detection", uploader.trap_id)
                    was_armed = is_armed

                if not is_armed:
                    # サーバが disarmed と応えた場合と、通信断/起動直後で保留の場合を
                    # 現地表示に区別して出す (どちらも作動はしない=安全側)。
                    status = "disarmed" if arm_state == "disarmed" else "comms_loss"
                    limiter.write_status(status, lte)
                    mark_progress()
                    time.sleep(5)
                    continue

                # 待機中の arm 確認はメモリ読みのみ。ブロッキング HTTP を呼ばないので
                # PIR サンプリング周期 (0.1s) が保たれる。通信断で状態が古くなれば
                # monitor.is_armed() が False を返し、待機を中断して保留に戻す。
                def _armed_or_pause() -> bool:
                    mark_progress()
                    return arm_monitor.is_armed()

                limiter.write_status("armed_idle", lte)
                motion_detected = motion_sensor.wait_for_sustained_motion(
                    1.0,
                    should_continue=_armed_or_pause,
                )
                if not motion_detected:
                    if was_armed is not False:
                        log.info("Trap %s changed to disarmed while waiting for motion", uploader.trap_id)
                        was_armed = False
                    continue
            else:
                motion_sensor.wait_for_sustained_motion(1.0)

            # 撮影ゲート(既定では無効。クールダウン>0 かブレーカー有効時のみ効く)。
            # 既定方針は「撮影を絞らない」なので通常はここを素通りする。
            block = limiter.record_block_reason()
            if block is not None:
                limiter.note_skip(block)
                limiter.write_status(block, lte)
                time.sleep(2)
                continue

            log.info("Motion detected -- starting recording")

            if not enforce_limits(log, get_videos_dir()):
                mark_progress()
                time.sleep(30)
                continue

            # 夜間は IR 投光器を点けたまま録画する。投光器側の光量センサーが
            # 明るい場所では点灯を抑えるので、昼夜の判定はソフトに持たない。
            with illuminator.lit():
                file_path = camera.record_clip(get_videos_dir(), 10)
            if not file_path:
                log.warning("Recording returned no file path")
                time.sleep(1)
                continue
            log.info("Recording complete: %s", file_path)
            limiter.note_recording()
            mark_progress()

            # LTE 送信予算を超えていたら、この新しい1本も送らず SD に残す。
            # 録画は止めない。予算回復後、drain 側が(バックログ過多なら新しい順で)送る。
            if limiter.upload_blocked_by_budget(lte):
                limiter.note_budget_log()
                limiter.write_status("upload_paused", lte)
                log.info("Upload budget reached -- keeping clip on SD: %s", file_path)
                time.sleep(0.5)
                continue

            try:
                size = os.path.getsize(file_path)
            except OSError:
                size = 0
            limiter.write_status("recording", lte)
            success = uploader.upload(file_path)
            mark_progress()
            if success:
                limiter.note_uploaded(size, lte)
                os.remove(file_path)
                log.info("Upload OK, local file deleted: %s", file_path)
            else:
                log.info("Upload FAILED, file retained: %s", file_path)

            time.sleep(0.5)
    finally:
        if arm_monitor is not None:
            try:
                arm_monitor.stop()
            except Exception:
                log.exception("Arm monitor stop failed")
        try:
            illuminator.close()
        except Exception:
            log.exception("Illuminator close failed")
        try:
            camera.close()
            log.info("Camera closed")
        except Exception:
            log.exception("Camera close failed")


def run_child(log):
    trap_id = os.getenv("TRAP_ID", "").strip()
    if not trap_id:
        raise RuntimeError("TRAP_ID is required in child mode")

    motion_sensor = MotionSensor()
    camera = WildlifeCamera()
    illuminator = Illuminator()
    link_client = ChildLinkClient(trap_id=trap_id)
    arm_state_client = create_uploader(log)
    was_armed = None

    # 子機も arm 確認を背景スレッドに追い出し、待機ループはメモリ値のみ読む。
    # arm の取得元は Worker 直 (WorkerUploader) か親機経由 (ChildLinkClient)。
    # どちらも .is_armed() を持つ。通信断=保留は monitor 側で担保する。
    arm_source = (
        arm_state_client
        if isinstance(arm_state_client, WorkerUploader)
        else link_client
    )
    arm_monitor = ArmStateMonitor(arm_source, log=log)
    arm_monitor.start()

    try:
        while True:
            is_armed = arm_monitor.is_armed()
            if is_armed != was_armed:
                if is_armed:
                    log.info("Trap %s is armed -- resuming motion detection", trap_id)
                else:
                    log.info("Trap %s is disarmed -- skipping motion detection", trap_id)
                was_armed = is_armed

            if not is_armed:
                time.sleep(5)
                continue

            motion_detected = motion_sensor.wait_for_sustained_motion(
                1.0,
                should_continue=arm_monitor.is_armed,
            )
            if not motion_detected:
                if was_armed is not False:
                    log.info("Trap %s changed to disarmed while waiting for motion", trap_id)
                    was_armed = False
                continue

            log.info("Motion detected on child node -- starting recording")
            with illuminator.lit():
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
            arm_monitor.stop()
        except Exception:
            log.exception("Arm monitor stop failed")
        try:
            illuminator.close()
        except Exception:
            log.exception("Illuminator close failed")
        try:
            camera.close()
            log.info("Camera closed")
        except Exception:
            log.exception("Camera close failed")


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
