# Multi-Node Template

## 目的

子機を増やすときに、各ノードへ何を配るかを固定化するためのテンプレートです。

- 子機: PIR, カメラ, armed 状態取得, 親機への転送
- 親機: 受信, upload, 監視Webとの接続

## 親機共通

親機は 1 台に集約します。

```env
WILDLIFE_NODE_ROLE=parent
WILDLIFE_LINK_TRANSPORT=tcp
WILDLIFE_PARENT_BIND_HOST=0.0.0.0
WILDLIFE_LINK_PORT=8765
WILDLIFE_API_URL=https://wildlife-cam-api.your-project.workers.dev
WILDLIFE_DEVICE_TOKEN=YOUR_PARENT_DEVICE_TOKEN
LOG_LEVEL=INFO
```

## 子機テンプレート

子機ごとに `TRAP_ID` を変えます。
将来的にトークンを分けるなら `WILDLIFE_DEVICE_TOKEN` も子機ごとに分けてください。

```env
WILDLIFE_NODE_ROLE=child
TRAP_ID=YMK-001
WILDLIFE_LINK_TRANSPORT=tcp
WILDLIFE_PARENT_HOST=192.168.68.65
WILDLIFE_LINK_PORT=8765
WILDLIFE_API_URL=https://wildlife-cam-api.your-project.workers.dev
WILDLIFE_DEVICE_TOKEN=YOUR_CHILD_DEVICE_TOKEN
LOG_LEVEL=INFO
```

## 命名規則

- `TRAP_ID`: `SITE-NNN`
- 例:
  - `YMK-001`
  - `YMK-002`
  - `YMK-003`

## 配置メモ

- `Pi 5`: `parent_main.py`
- `Pi Zero 2 W`: `child_main.py`
- 親機停止中でも子機は動くが、転送先がないので録画後転送で失敗する
- armed/disarmed の判定は子機が直接 API から取得する
