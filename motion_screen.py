"""透明な送信ゲート: 決定論的な動体スクリーニング。

設計原則 (docs/transparent-gate.md に全文):
  - 学習モデルを使わない。フレーム差分とブロブ特徴量、および人間可読な閾値
    (config/screen_rules_v1.json・バージョン管理) だけで判定する。
  - 全クリップについて judgment.json (特徴量の生値・各ルールの評価・判定) を必ず残す。
  - 「動物なし」の動画も削除しない (videos/held/ に保管、SD回収で全量が手に入る)。
    したがって偽陰性率は回収後に実測できる = 検出確率を定量化できる。
  - 判定に迷う場合 (uncertain) は必ず送信に倒す。偽陰性をデータに焼き付けない。

依存: ffmpeg (デコード) + numpy (差分)。どちらも Pi に導入済み。新規依存なし。
"""

import json
import math
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import numpy as np

SCREENER_VERSION = "motion_screen/1.0"

DEFAULT_RULES_FILE = Path(__file__).resolve().parent / "config" / "screen_rules_v1.json"

# 判定値
DECISION_WILDLIFE = "wildlife"    # 動物候補 → 送信
DECISION_NONE = "none"            # 動物なし → held/ へ保管
DECISION_UNCERTAIN = "uncertain"  # 境界例 → 送信 (保守側)
DECISION_ERROR = "error"          # 解析失敗 → 送信 (保守側)


def load_rules(rules_file: str | Path | None = None) -> dict:
    path = Path(rules_file) if rules_file else DEFAULT_RULES_FILE
    with open(path, encoding="utf-8") as handle:
        rules = json.load(handle)
    if "version" not in rules:
        raise ValueError(f"rules file has no version: {path}")
    return rules


def _decode_gray_frames(clip_path: str, rules: dict, progress=None):
    """ffmpeg で低解像度グレイスケールのフレーム列を取り出す (ストリーミング)。"""
    decode = rules["decode"]
    width, height, fps = decode["width"], decode["height"], decode["fps"]
    frame_bytes = width * height
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", clip_path,
        "-vf", f"fps={fps},scale={width}:{height}",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            if progress is not None:
                progress()
            yield np.frombuffer(buf, dtype=np.uint8).reshape(height, width)
    finally:
        proc.stdout.close()
        proc.wait(timeout=10)


def _blocks_from_mask(mask: np.ndarray, block: int, min_active_px: int) -> np.ndarray:
    """画素マスクをブロック格子に落とす (ノイズ粒の除去を兼ねる)。"""
    h, w = mask.shape
    gh, gw = h // block, w // block
    trimmed = mask[: gh * block, : gw * block]
    counts = trimmed.reshape(gh, block, gw, block).sum(axis=(1, 3))
    return counts >= min_active_px


def _largest_blob(grid: np.ndarray) -> tuple[int, tuple[float, float]]:
    """ブロック格子上の最大連結成分 (4近傍BFS)。戻り値: (ブロック数, 重心(gx, gy))。"""
    gh, gw = grid.shape
    seen = np.zeros_like(grid, dtype=bool)
    best_size, best_centroid = 0, (0.0, 0.0)
    for y in range(gh):
        for x in range(gw):
            if not grid[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            cells = []
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < gh and 0 <= nx < gw and grid[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(cells) > best_size:
                ys = sum(c[0] for c in cells) / len(cells)
                xs = sum(c[1] for c in cells) / len(cells)
                best_size, best_centroid = len(cells), (xs, ys)
    return best_size, best_centroid


def extract_features(clip_path: str, rules: dict, progress=None) -> dict:
    """クリップから決定論的な特徴量を抽出する。"""
    decode = rules["decode"]
    block = decode["block"]
    fps = decode["fps"]
    grid_w = decode["width"] // block
    grid_h = decode["height"] // block
    total_blocks = grid_w * grid_h

    pixel_delta = rules["pixel_delta"]
    min_active_px = rules["block_active_min_px"]
    # 活動フレームの定義は decide() の「実質的な動体」と同じ土俵 (ブロック数) で持つ。
    # pct と blocks を別々に閾値化すると、active_seconds は立つのに
    # substantial_motion は落ちる自己矛盾 (=静かな偽陰性) が起きる。
    blob_floor_blocks = blob_floor(rules, total_blocks)

    prev = None
    frames = 0
    active_frames = 0
    max_blob_blocks = 0
    track: list[tuple[float, float]] = []

    for frame in _decode_gray_frames(clip_path, rules, progress=progress):
        frames += 1
        if prev is not None:
            delta = np.abs(frame.astype(np.int16) - prev.astype(np.int16))
            mask = delta >= pixel_delta
            grid = _blocks_from_mask(mask, block, min_active_px)
            size, centroid = _largest_blob(grid)
            if size > max_blob_blocks:
                max_blob_blocks = size
            if size >= blob_floor_blocks:
                active_frames += 1
                track.append(centroid)
        prev = frame

    net_travel_blocks = _net_displacement(track)

    # 最大振れ幅 (軌跡上の任意2点間の最大距離)。判定には使わず記録だけする。
    # excursion >> net_travel はその場での往復運動の署名で、held/ を回収した後の
    # 閾値較正に効く (どちらか一方だけでは往復と横断を見分けられない)。
    max_excursion_blocks = 0.0
    for i in range(len(track)):
        for j in range(i + 1, len(track)):
            d = math.dist(track[i], track[j])
            if d > max_excursion_blocks:
                max_excursion_blocks = d

    return {
        "frames_analyzed": frames,
        "active_seconds": round(active_frames / fps, 2),
        "max_blob_pct": round(max_blob_blocks * 100.0 / total_blocks, 3),
        "net_travel_pct": round(net_travel_blocks * 100.0 / grid_w, 2),
        "max_excursion_pct": round(max_excursion_blocks * 100.0 / grid_w, 2),
        "max_blob_blocks": max_blob_blocks,
        "total_blocks": total_blocks,
        "track_points": len(track),
    }


def _net_displacement(track: list[tuple[float, float]]) -> float:
    """軌跡の「正味の移動」= 前半1/4の平均位置から後半1/4の平均位置までの距離。

    docs/transparent-gate.md の「動物は横切る・植生はその場で揺れる」を素直に
    測る指標。往復運動は始点と終点がほぼ同じ位置に戻るため伸びない。
    (任意2点間の最大距離では、その場で大きく揺れる藪が横断と同じ値を出してしまう。
     実測: 大きく揺れる箱 excursion 10.0% に対し net 2.5%、横断する箱は 46.9%。)
    端点1点だけを使うと取りこぼしフレームの影響を受けるので四分位平均をとる。
    """
    if len(track) < 2:
        return 0.0
    k = max(1, len(track) // 4)
    head = (sum(p[0] for p in track[:k]) / k, sum(p[1] for p in track[:k]) / k)
    tail = (sum(p[0] for p in track[-k:]) / k, sum(p[1] for p in track[-k:]) / k)
    return math.dist(head, tail)


def blob_floor(rules: dict, total_blocks: int) -> int:
    """「実質的な動体」とみなす最小ブロック数 (最低1ブロック)。"""
    return max(1, int(round(total_blocks * rules["blob_floor_pct"] / 100.0)))


def decide(features: dict, rules: dict) -> tuple[str, list[dict]]:
    """特徴量とルールから判定を返す。各ルールの評価を全て記録する。

    判定表 (rules ファイルの閾値を参照):
      1. 変化したブロックが1つも無い (max_blob_blocks == 0)        → none (無変化)
      2. 動物条件を全て満たす (面積帯・持続・正味移動)              → wildlife
      3. 動体はあるが正味移動が微小 (< veg_travel_max_pct)
         かつ面積が動物帯に届かない                                → none (植生の揺れ)
      4. それ以外                                                  → uncertain (送信)

    none を出す口は 1 と 3 だけで、1 は「何も変化していない」という積極的事実、
    3 は「その場で揺れる小さいもの」という積極的事実に限る。閾値未満の弱い動体は
    none ではなく uncertain (送信) に落ちる — 偽陰性をデータに焼き付けないため。
    """
    evals = []

    def check(name: str, value, threshold, passed: bool) -> bool:
        evals.append({"rule": name, "value": value, "threshold": threshold, "pass": bool(passed)})
        return passed

    # 1. 差分ブロックが皆無 = 無変化。ここだけが「証拠が無いことを根拠にした none」で、
    #    弱いが実在する動体 (遠い/小さい動物) は下の枝で uncertain に落ちる。
    any_motion = check(
        "any_motion", features["max_blob_blocks"], 1, features["max_blob_blocks"] >= 1,
    )
    if not any_motion:
        return DECISION_NONE, evals

    substantial = check(
        "substantial_motion", features["max_blob_pct"], rules["blob_floor_pct"],
        features["max_blob_pct"] >= rules["blob_floor_pct"],
    )
    size_ok = check(
        "blob_in_animal_band",
        features["max_blob_pct"], [rules["blob_min_pct"], rules["blob_max_pct"]],
        rules["blob_min_pct"] <= features["max_blob_pct"] <= rules["blob_max_pct"],
    )
    duration_ok = check(
        "sustained_motion", features["active_seconds"], rules["min_active_seconds"],
        features["active_seconds"] >= rules["min_active_seconds"],
    )
    travel_ok = check(
        "net_travel", features["net_travel_pct"], rules["min_travel_pct"],
        features["net_travel_pct"] >= rules["min_travel_pct"],
    )
    if substantial and size_ok and duration_ok and travel_ok:
        return DECISION_WILDLIFE, evals

    stationary = check(
        "vegetation_like_sway", features["net_travel_pct"], rules["veg_travel_max_pct"],
        features["net_travel_pct"] < rules["veg_travel_max_pct"],
    )
    undersized = features["max_blob_pct"] < rules["blob_min_pct"]
    if stationary and undersized:
        return DECISION_NONE, evals

    return DECISION_UNCERTAIN, evals


def screen_clip(clip_path: str, rules: dict, progress=None) -> dict:
    """1本のクリップを判定し、judgment レコード (dict) を返す。"""
    started = time.time()
    record = {
        "clip": os.path.basename(clip_path),
        "screener": SCREENER_VERSION,
        "rules_version": rules["version"],
        "screened_at": datetime.now().astimezone().isoformat(),
    }
    try:
        record["clip_bytes"] = os.path.getsize(clip_path)
        features = extract_features(clip_path, rules, progress=progress)
        decision, evals = decide(features, rules)
        if features["frames_analyzed"] < 2:
            # デコードが空振り (壊れたクリップ等) — 判定不能として送信に倒す
            decision, evals = DECISION_ERROR, [
                {"rule": "decode", "value": features["frames_analyzed"],
                 "threshold": 2, "pass": False}]
        record.update(features=features, rule_evaluations=evals, decision=decision)
    except Exception as exc:  # 解析失敗は送信に倒す (偽陰性を作らない)
        record.update(features=None, rule_evaluations=[], decision=DECISION_ERROR,
                      error=str(exc)[:300])
    record["screen_ms"] = int((time.time() - started) * 1000)
    return record


def judgments_dir(videos_dir: str) -> Path:
    return Path(videos_dir) / "judgments"


def held_dir(videos_dir: str) -> Path:
    return Path(videos_dir) / "held"


def write_judgment(videos_dir: str, record: dict) -> Path:
    """judgment.json を videos/judgments/ に永続化 (temp+rename)。"""
    target_dir = judgments_dir(videos_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    name = Path(record["clip"]).stem + ".judgment.json"
    path = target_dir / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return path


def screen_and_route(log, videos_dir: str, clip_path: str,
                     rules: dict, progress=None) -> str:
    """判定して routing する。戻り値: "send" | "hold"。

    - wildlife / uncertain / error → "send" (クリップはその場に残し従来の送信経路へ)
    - none → videos/held/ へ移動して "hold" (送信しない・自動削除からも保護される)
    - どの経路でも judgment.json は必ず書く。移動やJSON書き込みの失敗は "send" に倒す。
    """
    record = screen_clip(clip_path, rules, progress=progress)
    try:
        write_judgment(videos_dir, record)
    except OSError as exc:
        log.warning("Judgment write failed for %s: %s -- sending anyway", clip_path, exc)
        record["decision"] = DECISION_ERROR

    features = record.get("features") or {}
    log.info(
        "Screen[%s] %s: decision=%s blob=%.2f%% travel=%.1f%% active=%.1fs (%dms)",
        record["rules_version"], record["clip"], record["decision"],
        features.get("max_blob_pct", -1), features.get("net_travel_pct", -1),
        features.get("active_seconds", -1), record["screen_ms"],
    )

    if record["decision"] != DECISION_NONE:
        return "send"

    try:
        target_dir = held_dir(videos_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / Path(clip_path).name
        serial = 1
        while target.exists():
            target = target_dir / f"{Path(clip_path).stem}_{serial:02d}{Path(clip_path).suffix}"
            serial += 1
        shutil.move(clip_path, str(target))
        log.info("Held (no wildlife): %s", target)
        return "hold"
    except OSError as exc:
        log.warning("Could not move clip to held/: %s -- sending instead", exc)
        return "send"


if __name__ == "__main__":
    # 手元検証用 CLI: python3 motion_screen.py <clip.mp4> [rules.json]
    import sys

    clip = sys.argv[1]
    rules = load_rules(sys.argv[2] if len(sys.argv) > 2 else None)
    result = screen_clip(clip, rules)
    print(json.dumps(result, ensure_ascii=False, indent=2))
