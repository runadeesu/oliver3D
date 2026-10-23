# Oliver Tree 4体 — 指と口が動くキャラクター化

Meshy 由来の静的メッシュ 4 体(`Oliver_Turbo_A_Pose` / `Oliver_Cowboy_Tears_A_Pose` / `Oliver_Alone_In_A_Crowd_A_Pose` / `Oliver_Gray_Suit_A_Pose`)を、
元の見た目(形状・色・UV・テクスチャ)を保ったまま、**指先と口まで動くキャラクター**に加工したもの。Alone / Gray の元データは https://gofile.io/d/TiBYhFNZ 、
**Turbo / Cowboy は作り直された版**(https://gofile.io/d/tVUQudhH の `Turbo.fbx` / `Cowboy.fbx`)を使っている。元データは変更せず、複製に対して作業している。
Blender 4.5.14(ヘッドレス)+ Python のみ。API キー・有料サービスは使っていない。

## 納品物

| モデル | .blend | FBX | GLB | テクスチャ | 動作確認動画 |
|---|---|---|---|---|---|
| **Turbo** [`Oliver_Turbo_A_Pose`](models/Oliver_Turbo_A_Pose/README.md) | blend (分割 3 個, 計 214 MB — 下記「大きなファイル」参照) | [fbx](models/Oliver_Turbo_A_Pose/Oliver_Turbo_A_Pose.fbx) (47 MB) | glb (分割 2 個, 計 103 MB — 下記「大きなファイル」参照) | [textures](models/Oliver_Turbo_A_Pose/textures) | [mp4](models/Oliver_Turbo_A_Pose/Oliver_Turbo_A_Pose_check.mp4) |
| **Cowboy** [`Oliver_Cowboy_Tears_A_Pose`](models/Oliver_Cowboy_Tears_A_Pose/README.md) | [blend](models/Oliver_Cowboy_Tears_A_Pose/Oliver_Cowboy_Tears_A_Pose_rigged.blend) (59 MB) | [fbx](models/Oliver_Cowboy_Tears_A_Pose/Oliver_Cowboy_Tears_A_Pose.fbx) (17 MB) | [glb](models/Oliver_Cowboy_Tears_A_Pose/Oliver_Cowboy_Tears_A_Pose.glb) (43 MB) | [textures](models/Oliver_Cowboy_Tears_A_Pose/textures) | [mp4](models/Oliver_Cowboy_Tears_A_Pose/Oliver_Cowboy_Tears_A_Pose_check.mp4) |
| **Alone** [`Oliver_Alone_In_A_Crowd_A_Pose`](models/Oliver_Alone_In_A_Crowd_A_Pose/README.md) | blend (分割 2 個, 計 116 MB — 下記「大きなファイル」参照) | [fbx](models/Oliver_Alone_In_A_Crowd_A_Pose/Oliver_Alone_In_A_Crowd_A_Pose.fbx) (27 MB) | [glb](models/Oliver_Alone_In_A_Crowd_A_Pose/Oliver_Alone_In_A_Crowd_A_Pose.glb) (65 MB) | [textures](models/Oliver_Alone_In_A_Crowd_A_Pose/textures) | [mp4](models/Oliver_Alone_In_A_Crowd_A_Pose/Oliver_Alone_In_A_Crowd_A_Pose_check.mp4) |
| **Gray** [`Oliver_Gray_Suit_A_Pose`](models/Oliver_Gray_Suit_A_Pose/README.md) | blend (分割 4 個, 計 294 MB — 下記「大きなファイル」参照) | [fbx](models/Oliver_Gray_Suit_A_Pose/Oliver_Gray_Suit_A_Pose.fbx) (65 MB) | glb (分割 2 個, 計 153 MB — 下記「大きなファイル」参照) | [textures](models/Oliver_Gray_Suit_A_Pose/textures) | [mp4](models/Oliver_Gray_Suit_A_Pose/Oliver_Gray_Suit_A_Pose_check.mp4) |

各モデルのフォルダに `README.md`(ボーン名・表情名・操作方法・検証値・制約)がある。モデルはどれも A ポーズで開く。

## やったこと

1. **形状の確認・修正** — 4体とも単一の三角形メッシュ(14〜75 万頂点)で、指は癒着(または互いに接した状態)し、口は閉じた一枚の表面だった。
   * **指**: 手の領域を色(肌)+測地距離で切り出し、指先・指軸を推定して、**独立して曲げられるように指と指を切り離した**(ブーリアン。関節部分の頂点も確保)。Alone は元から指先が分かれていたので接触部を切断、Turbo / Cowboy(作り直し版)/ Gray は癒着していたため、指軸を推定して指先側から約80%の長さまでスリットを新規に彫った(Cowboy は元メッシュが粗いので手と口まわりだけを局所的に細分化してから)。
   * **口**: 唇のしわ(幾何の谷)に沿って表面を切り開き、**実際の唇の開口 + 口腔(口内壁)+ 上下の歯 + 舌**を追加した(顔の引き伸ばしや黒い板ではない)。口を閉じれば元の顔に戻る。
2. **全身 + 手指のリグ** — Mixamo 風の命名で 53 ボーン(全身 + 左右各手 **5本の指 × 3関節** + Jaw)。ウェイトは**メッシュ表面のヒート拡散**(表面の内側にある骨だけを候補にして拡散するので、腕を上げても胴の服が引っ張られない)+ 手指は関節チェーンから明示計算(親指の対向、指を動かしても袖・胴は動かない)。肩の関節は肩の付け根に置いた(Turbo / Cowboy は元ファイルの Meshy の肩・肘の位置を使用)。A ポーズ。
3. **口と表情** — 基本のシェイプキー `jawOpen` / `mouthClose` / `viseme_A` `viseme_I` `viseme_U` `viseme_E` `viseme_O` / `mouthSmile`(+ Jaw ボーン)に加えて、片側の笑顔・への字・口角を引く・すぼめ・口の横ずらし・唇の片側・顎の前後左右・頬のふくらみ・舌の 20 個の細かいキー(合計 28 個)。**開口は長方形でなく楕円形**で、口を開くと上唇もわずかに上がる。歯・舌が皮膚を突き抜けないことをクリアランスで確認。
4. **動作確認** — 手を開く→握る→開く / 指を1本ずつ(左右)/ 人差し指・ピース / 口の 閉→開→閉 / あ→い→う→え→お / 笑顔→通常 を 24 fps・1,074 フレームのアニメにし、さらに**細かい表情の確認区間**と、**日本語の発話(こんにちは、オリバーです。よろしくね。)+呼吸・体重移動・うなずき・お辞儀・手のジェスチャーの区間**を付けた。指は人差し指から小指へ、付け根から指先へ時間差で曲がり、補間は Bezier で加速・減速する。実際に再生・レンダリングして MP4 にした。
5. **書き出しと再読込検証** — .blend / FBX / GLB を書き出し、FBX と GLB は**空のシーンに再読込して**ボーン・ウェイト・シェイプキー・テクスチャ・アニメが残っていること、指・口が実際にメッシュを変形させることを数値で確認した。

## 検証サマリ(書き出した FBX / GLB を空シーンに再読込して計測)

| モデル | ボーン数 | 指の頂点グループ | ウェイト付き頂点 | 右手を握った時の指頂点の平均移動量 (FBX / GLB) | 同・袖/上腕の最大移動量 (FBX / GLB) | `jawOpen` 最大変位 |
|---|---|---|---|---|---|---|
| Turbo | 53 | 30 | 532,309/532,309 | 53.5 / 57.1 mm | 0.0 / 0.0 mm | 33 mm |
| Cowboy | 53 | 30 | 144,282/144,282 | 52.4 / 53.6 mm | 0.0 / 0.0 mm | 35 mm |
| Alone | 53 | 30 | 289,067/289,067 | 61.6 / 58.1 mm | 0.0 / 0.0 mm | 32 mm |
| Gray | 53 | 30 | 754,583/754,583 | 52.6 / 54.3 mm | 0.0 / 0.0 mm | 30 mm |

詳細(キーごとの変位、テクスチャ、口腔クリアランス等)は各モデルの README。再生ベースの検証(再読込後にアニメを再生して 左右10本の指と顎が実際に動くか): 各モデルの README「アニメの再生検証」。

## Turbo / Cowboy について(作り直し版)

* ユーザーが作り直した `Turbo.fbx` / `Cowboy.fbx`(https://gofile.io/d/tVUQudhH)を使った。ファイルに付いていた Meshy の自動リグ(24 ボーン、指・顎なし)とそのアニメは使わず、メッシュだけを取り出して下記のリグを作り直した。UV の継ぎ目で分かれていた頂点は溶接して一枚の面にしている。
* 以前の版で行っていた**顔の補正(参考写真に合わせた顔の修正・サングラスの作り直し)は、作り直し版では行っていない**(顔・髪・服・サングラス・帽子は元データのまま)。以前の版の補正画像・参考写真・補正ツールはリポジトリから削除した。
* 元データのテクスチャには**サングラスの色と肌の色が混ざっている部分がある**。依頼により**修正していない**(元データのまま)。
* 元データに roughness / metallic のマップは無いので、材質は roughness 0.6 / metallic 0 の固定値(ベースカラー+ノーマルのみ)。

## 体の変形テスト(腕・脚)

「腕や脚を大きく動かすと服が崩れる」という指摘に対し、ウェイトの作り方を作り直した(旧: 骨の近くの頂点を測地距離で割り当て → 新: 表面のヒート拡散。肩の関節も肩の付け根に下げた)。腕を前に 60 / 90 / 120°・横に 55°・真上に 125°・後ろに 40°、肘を 90° 曲げる、脚を前に 45 / 80°・横に 30°、膝を曲げる、背骨を前に曲げる・ひねる、首を回す、の各姿勢を 4 体ぶん描画し、目で確認した(`tools/oliver_rig/test_strain.py` で再現できる。エッジの伸びも計測する)。

* 旧版では、腕を横や前に上げるとジャケットの胴まで袖と一緒に引っ張られて「翼」や「ケープ」のようになっていた(胴の側面・胸のウェイトに腕の骨が漏れていた)。新版では胴はほぼ元のまま、袖だけが肩から動く。
* 完全ではない: Alone の大きなコートは腕を真上に上げると肩まわりのコートが一緒に持ち上がる(ポンチョ状)。Gray の長い髪は頭を大きく回すと伸びる。ごく小さなトゲ(コートの襟の裏に 1 か所)が見えることがある。エッジの伸びの統計では、ごく短い辺(0.5〜1 mm の薄い三角形)が大きな倍率で伸びる場所が残っている(見た目では目立たない)。

## できていないこと・制約(正直な報告)

* **Turbo / Cowboy / Gray の指は付け根側 約20% が水かき状につながったまま**(元メッシュで癒着していたため、全長を切り離すと指の根元に穴が開く)。個別に曲げると付け根が引き伸ばされ、ピースサインでも2本が大きく離れない。切り口の面は単色の肌色で、指を1本だけ曲げると平らな「ひれ」状に見えることがある(特に Cowboy)。Alone は指が独立しており、この制約は小さい。
* 口腔は様式化(単色の口内壁、簡易な歯・舌、舌ボーンなし)。母音の形(あいうえお)は近似。`viseme_U`/`viseme_O` の口の幅変化に合わせて歯・舌を横に縮めているが、実際の発話の全口形を再現するものではない。Alone は唇のしわ沿いに小さな暗い点状のテクスチャ乱れが残る。Gray は口腔の下壁の頂点 3 つが外皮まで 1.06 mm(ほぼ接触)。
* 服・髪・帽子・フリンジは肌と同じ自動スキニングで、物理シミュレーションはない。腕を前・横・上に上げる、脚を上げる、膝を曲げる、背骨・首をひねる、といった大きな姿勢で確認して直したが(下記「体の変形テスト」)、ゆったりした服は線形ブレンドスキンの限界(真上に上げたときの肩のたるみ、髪の伸び)が残る。
* Turbo / Cowboy は roughness / metallic マップが無く、FBX / GLB / .blend ともベースカラー+ノーマルのみ。Alone / Gray の FBX もベースカラー+ノーマルのみ(roughness/metallic は `textures/` と GLB に収録)。GLB のベースカラーは JPEG(q92)に再エンコードされている。
* 口を強く閉じるキー `mouthClose` では、唇の合わせ目にごく小さな(1 mm 以下の)ギザつきが出ることがある(キー 0 の通常の口は元の顔のまま)。
* 追加の細かい表情キー(20 個)は単純な変位場で作った近似で、複数を同時に最大にすると唇や歯が重なることがある。発話デモは音声のない見本(音節表から口形を作成)で、人の実際の動きの細かさ(まばたき・目の動き等)は再現していない。
* シェイプキーが 28 個(全頂点分)あるため、.blend / GLB のファイルサイズは大きい(Turbo の .blend 約 213 MB、Gray の .blend 約 293 MB)。
* 動画は Blender Workbench(スタジオ照明)で、2048² に縮小したテクスチャを使って 1280×720 で描画したもの(納品テクスチャは元の解像度のまま)。
* 検証は Blender 4.5 での再読込のみ。Unity / Unreal / 他の DCC での読み込み・見え方は未確認。

## 大きなファイル

GitHub の 1 ファイル 100 MB 制限のため、超えるファイルは 90 MiB ごとに分割してある(`*.part-00`, `*.part-01`, …)。結合と検証(各モデルのフォルダで):

```bash
cat <ファイル名>.part-* > <ファイル名>
sha256sum -c <ファイル名>.sha256
```

分割してあるファイル:

* `models/Oliver_Turbo_A_Pose/Oliver_Turbo_A_Pose.glb`(2 分割)
* `models/Oliver_Turbo_A_Pose/Oliver_Turbo_A_Pose_rigged.blend`(3 分割)
* `models/Oliver_Alone_In_A_Crowd_A_Pose/Oliver_Alone_In_A_Crowd_A_Pose_rigged.blend`(2 分割)
* `models/Oliver_Gray_Suit_A_Pose/Oliver_Gray_Suit_A_Pose.glb`(2 分割)
* `models/Oliver_Gray_Suit_A_Pose/Oliver_Gray_Suit_A_Pose_rigged.blend`(4 分割)

## 作り方(再現)

`tools/` に全スクリプトがある(Blender 4.5.14 ヘッドレス + numpy/scipy)。環境: `source tools/setup_env.sh <作業ディレクトリ>`。主な段階:

| 段階 | スクリプト |
|---|---|
| 取り込み・正規化・テクスチャ取り出し | `oliver_rig/import_fbx.py`, `normalize_raw.py`, `extract_tex.py`, `prep_arrays.py`, `prep_textures.py` |
| (Turbo / Cowboy 作り直し版)Meshy リグ付き FBX の取り込み・溶接 | `oliver_rig/prep_rigged_fbx.py` |
| (Cowboy)手・口まわりの局所細分化 | `oliver_rig/refine_regions.py` |
| 1. 指の分離 | `oliver_rig/build_hands.py` (`hands_seg.py`, `hands_digits.py`, `hands_carve.py`) |
| 口の位置の計測 | `oliver_rig/mouth_measure.py` → `configs/<tag>.json` |
| シェイプキーの到達範囲(鼻・髪などが動かないこと) | `oliver_rig/key_reach.py` |
| 2./3. 口・骨格・ウェイト・シェイプキー | `oliver_rig/build_model.py` (`mouth_*.py`, `skeleton.py`, `skin_weights.py`, `hand_weights.py`) |
| アニメ・書き出し | `oliver_rig/build_anim_export.py`, `anim.py` |
| 検証 | `oliver_rig/verify_export.py`, `verify_anim.py`, `test_poses.py`, `test_body.py`, `test_strain.py`(体の姿勢テスト), `view_body_weights.py` / `view_skeleton.py`(ウェイト・骨の可視化), `debug_stuck.py` |
| 動画 | `render_videos.sh`, `oliver_rig/render_video.py`, `encode_video.sh` |
| README 生成 | `make_readmes.py` |

元データの md5: Alone `1a358a11…` / Gray `0066f040…`(FBX)、作り直し版 Turbo.fbx `7c02511b…` / Cowboy.fbx `0e3d7b1a…`。
