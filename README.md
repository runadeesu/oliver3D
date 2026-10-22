# Oliver Tree 4体 — 指と口が動くキャラクター化

Meshy 由来の静的メッシュ 4 体(`Oliver_Turbo_A_Pose` / `Oliver_Cowboy_Tears_A_Pose` / `Oliver_Alone_In_A_Crowd_A_Pose` / `Oliver_Gray_Suit_A_Pose`)を、
元の見た目(形状・色・UV・テクスチャ)を保ったまま、**指先と口まで動くキャラクター**に加工したもの。元データ(https://gofile.io/d/TiBYhFNZ)は変更せず、複製に対して作業している。
Blender 4.5.14(ヘッドレス)+ Python のみ。API キー・有料サービスは使っていない(顔の補正にだけ MediaPipe の顔ランドマーク検出器を使用)。

## 納品物

| モデル | .blend | FBX | GLB | テクスチャ | 動作確認動画 |
|---|---|---|---|---|---|
| **Turbo** [`Oliver_Turbo_A_Pose`](models/Oliver_Turbo_A_Pose/README.md) | [blend](models/Oliver_Turbo_A_Pose/Oliver_Turbo_A_Pose_rigged.blend) (73 MB) | [fbx](models/Oliver_Turbo_A_Pose/Oliver_Turbo_A_Pose.fbx) (32 MB) | [glb](models/Oliver_Turbo_A_Pose/Oliver_Turbo_A_Pose.glb) (53 MB) | [textures](models/Oliver_Turbo_A_Pose/textures) | [mp4](models/Oliver_Turbo_A_Pose/Oliver_Turbo_A_Pose_check.mp4) |
| **Cowboy** [`Oliver_Cowboy_Tears_A_Pose`](models/Oliver_Cowboy_Tears_A_Pose/README.md) | [blend](models/Oliver_Cowboy_Tears_A_Pose/Oliver_Cowboy_Tears_A_Pose_rigged.blend) (87 MB) | [fbx](models/Oliver_Cowboy_Tears_A_Pose/Oliver_Cowboy_Tears_A_Pose.fbx) (38 MB) | [glb](models/Oliver_Cowboy_Tears_A_Pose/Oliver_Cowboy_Tears_A_Pose.glb) (60 MB) | [textures](models/Oliver_Cowboy_Tears_A_Pose/textures) | [mp4](models/Oliver_Cowboy_Tears_A_Pose/Oliver_Cowboy_Tears_A_Pose_check.mp4) |
| **Alone** [`Oliver_Alone_In_A_Crowd_A_Pose`](models/Oliver_Alone_In_A_Crowd_A_Pose/README.md) | [blend](models/Oliver_Alone_In_A_Crowd_A_Pose/Oliver_Alone_In_A_Crowd_A_Pose_rigged.blend) (52 MB) | [fbx](models/Oliver_Alone_In_A_Crowd_A_Pose/Oliver_Alone_In_A_Crowd_A_Pose.fbx) (24 MB) | [glb](models/Oliver_Alone_In_A_Crowd_A_Pose/Oliver_Alone_In_A_Crowd_A_Pose.glb) (42 MB) | [textures](models/Oliver_Alone_In_A_Crowd_A_Pose/textures) | [mp4](models/Oliver_Alone_In_A_Crowd_A_Pose/Oliver_Alone_In_A_Crowd_A_Pose_check.mp4) |
| **Gray** [`Oliver_Gray_Suit_A_Pose`](models/Oliver_Gray_Suit_A_Pose/README.md) | blend (分割 2 個, 計 135 MB — 下記「大きなファイル」参照) | [fbx](models/Oliver_Gray_Suit_A_Pose/Oliver_Gray_Suit_A_Pose.fbx) (59 MB) | [glb](models/Oliver_Gray_Suit_A_Pose/Oliver_Gray_Suit_A_Pose.glb) (94 MB) | [textures](models/Oliver_Gray_Suit_A_Pose/textures) | [mp4](models/Oliver_Gray_Suit_A_Pose/Oliver_Gray_Suit_A_Pose_check.mp4) |

各モデルのフォルダに `README.md`(ボーン名・表情名・操作方法・検証値・制約)がある。モデルはどれも A ポーズで開く。

## やったこと

1. **形状の確認・修正** — 4体とも単一の三角形メッシュ(29〜75万頂点)で、指は癒着し、口は閉じた一枚の表面だった。
   * **指**: 手の領域を色(肌)+測地距離で切り出し、指先・指軸を推定して、**独立して曲げられるように指と指を切り離した**(ブーリアン。関節部分の頂点も確保)。Turbo / Alone は元から指先が分かれていたので接触部を切断、Cowboy / Gray は癒着した「ミトン状」だったため指軸を推定して指先側から約80%の長さまでスリットを新規に彫った。
   * **口**: 唇のしわ(幾何の谷)に沿って表面を切り開き、**実際の唇の開口 + 口腔(口内壁)+ 上下の歯 + 舌**を追加した(顔の引き伸ばしや黒い板ではない)。口を閉じれば元の顔に戻る。
2. **全身 + 手指のリグ** — Mixamo 風の命名で 53 ボーン(全身 + 左右各手 **5本の指 × 3関節** + Jaw)。ウェイトは測地距離ベースの自動スキニング + 手指は関節チェーンから明示計算(親指の対向、指を動かしても袖・胴は動かない)。A ポーズ。
3. **口と表情** — シェイプキー `jawOpen` / `mouthClose` / `viseme_A` `viseme_I` `viseme_U` `viseme_E` `viseme_O` / `mouthSmile`(+ Jaw ボーン)。歯・舌が皮膚を突き抜けないことをクリアランスで確認。音声なし。
4. **動作確認** — 手を開く→握る→開く / 指を1本ずつ(左右)/ 人差し指・ピース / 口の 閉→開→閉 / あ→い→う→え→お / 笑顔→通常 を 24 fps・636 フレームのアニメにし、実際に再生・レンダリングして MP4 にした。
5. **書き出しと再読込検証** — .blend / FBX / GLB を書き出し、FBX と GLB は**空のシーンに再読込して**ボーン・ウェイト・シェイプキー・テクスチャ・アニメが残っていること、指・口が実際にメッシュを変形させることを数値で確認した。

## 検証サマリ(書き出した FBX / GLB を空シーンに再読込して計測)

| モデル | ボーン数 | 指の頂点グループ | ウェイト付き頂点 | 右手を握った時の指頂点の平均移動量 (FBX / GLB) | 同・袖/上腕の最大移動量 (FBX / GLB) | `jawOpen` 最大変位 |
|---|---|---|---|---|---|---|
| Turbo | 53 | 30 | 398,645/398,645 | 54.1 / 52.2 mm | 0.0 / 0.0 mm | 33 mm |
| Cowboy | 53 | 30 | 480,909/480,909 | 46.7 / 47.9 mm | 0.0 / 0.0 mm | 31 mm |
| Alone | 53 | 30 | 288,967/288,967 | 59.9 / 58.1 mm | 0.0 / 0.0 mm | 32 mm |
| Gray | 53 | 30 | 754,483/754,483 | 54.7 / 54.3 mm | 0.0 / 0.0 mm | 30 mm |

詳細(キーごとの変位、テクスチャ、口腔クリアランス等)は各モデルの README。再生ベースの検証(再読込後にアニメを再生して 左右10本の指と顎が実際に動くか): 各モデルの README「アニメの再生検証」。

## 顔の修正(追加依頼: Turbo と Cowboy を参考写真に合わせて直す / Cowboy のサングラス)

追加依頼に対し、`reference/` の参考写真(Turbo / Cowboy)に合わせて顔を修正した。詳細・前後比較画像は
[Turbo](models/Oliver_Turbo_A_Pose/README.md#顔の修正追加依頼-参考写真に合わせて顔を直す) / [Cowboy](models/Oliver_Cowboy_Tears_A_Pose/README.md#顔とサングラスの修正追加依頼-参考写真に合わせて顔を直す--サングラスが変なので直す) の README。

* **共通**: 参考写真を **GFPGAN v1.4(顔復元 AI)** で超解像 → MediaPipe 顔ランドマーク(478点)で写真をモデルの正面に歪ませて重ね、肌・唇・鼻筋・陰影・ひげを写真に置き換え、8K テクスチャに焼き込み。顔の色差(Lab ΔE、写真との差)は Turbo 13.9→8.3、Cowboy 23.3→5.3。
* **Turbo**: 顔の輪郭はもともと写真に 1〜3 mm で一致していたため**テクスチャのみ**。
* **Cowboy**: 顔のランドマーク差(最大約12 mm)に合わせて**顔の形状も修正**。元の**サングラスは壊れていた**(片側レンズ欠け、テンプルとブリッジが崩れた塊)ため、元の形状を撤去して**丸型サングラスを作り直した**(左右対称の丸レンズ + 細い金属リム + ブリッジ + 鼻パッド + 耳までのテンプル)。口の位置が下がったため口の構造も作り直し。

**正直な限界**: 参考写真は正面1枚で、顔の奥行き(鼻の高さ・眉の出方)は写真から復元できない。GFPGAN による細部は推定で補ったもの。「写真と完全に同じ顔」にはなっておらず、**顔の見た目は大きく写真に近づいたが、完全一致ではない**。Cowboy のレンズは単色の濃色ガラス(写真の艶のあるレンズの映り込みは再現していない)。

## できていないこと・制約(正直な報告)

* **Cowboy / Gray の指は付け根側 約20% が水かき状につながったまま**(元メッシュで癒着していたため、全長を切り離すと指の根元に穴が開く)。個別に曲げると付け根が引き伸ばされ、ピースサインでも2本が大きく離れない。Turbo / Alone は指が独立しており、この制約は小さい。
* 口腔は様式化(単色の口内壁、簡易な歯・舌、舌ボーンなし)。母音の形(あいうえお)は近似。`viseme_U`/`viseme_O` の口の幅変化に合わせて歯・舌を横に縮めているが、実際の発話の全口形を再現するものではない。Alone は唇のしわ沿いに小さな暗い点状のテクスチャ乱れが残る。Gray は口腔の下壁の頂点 3 つが外皮まで 1.06 mm(ほぼ接触)。
* 服・髪・帽子・フリンジは肌と同じ自動スキニングで、物理シミュレーションはない。腕を大きく動かすと線形ブレンドスキンの限界(袖口のつぶれ等)が出る。
* FBX にはベースカラー+ノーマルのみ(roughness/metallic は `textures/` と GLB に収録)。GLB のベースカラーは JPEG(q92)に再エンコードされている。
* 動画は Blender Workbench(スタジオ照明)で 640×720 + 2K テクスチャで描画したもの(納品テクスチャは 8K のまま)。
* 検証は Blender 4.5 での再読込のみ。Unity / Unreal / 他の DCC での読み込み・見え方は未確認。

## 大きなファイル

GitHub の 1 ファイル 100 MB 制限のため、超えるファイルは 90 MiB ごとに分割してある(`*.part-aa`, `*.part-ab`, …)。結合:

```bash
cat Oliver_Gray_Suit_A_Pose_rigged.blend.part-* > Oliver_Gray_Suit_A_Pose_rigged.blend
sha256sum -c Oliver_Gray_Suit_A_Pose_rigged.blend.sha256
```

## 作り方(再現)

`tools/` に全スクリプトがある(Blender 4.5.14 ヘッドレス + numpy/scipy)。環境: `source tools/setup_env.sh <作業ディレクトリ>`。主な段階:

| 段階 | スクリプト |
|---|---|
| 取り込み・正規化・テクスチャ取り出し | `oliver_rig/import_fbx.py`, `normalize_raw.py`, `extract_tex.py`, `prep_arrays.py`, `prep_textures.py` |
| (Turbo / Cowboy)顔の補正 | `run_face_fix.sh`, `oliver_rig/face_restore.py`(GFPGAN), `face_render.py`, `face_landmarks.py`, `face_surgery.py`(Cowboy: 顔の形状・サングラス作り直し), `face_texture.py` |
| 1. 指の分離 | `oliver_rig/build_hands.py` (`hands_seg.py`, `hands_digits.py`, `hands_carve.py`) |
| 口の位置の計測 | `oliver_rig/mouth_measure.py` → `configs/<tag>.json` |
| 2./3. 口・骨格・ウェイト・シェイプキー | `oliver_rig/build_model.py` (`mouth_*.py`, `skeleton.py`, `skin_weights.py`, `hand_weights.py`) |
| アニメ・書き出し | `oliver_rig/build_anim_export.py`, `anim.py` |
| 検証 | `oliver_rig/verify_export.py`, `verify_anim.py`, `test_poses.py`, `test_body.py`, `debug_stuck.py` |
| 動画 | `render_videos.sh`, `oliver_rig/render_video.py`, `encode_video.sh` |
| README 生成 | `make_readmes.py` |

元データの md5: Alone `1a358a11…` / Cowboy `eaf6eba5…` / Gray `0066f040…`(FBX)、Turbo `e4260379…`(zip)。
