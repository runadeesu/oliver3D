"""Write models/<Name>/README.md for the four delivered characters and the top-level README.md.
python3 tools/make_readmes.py <logs_dir> <models_dir> <repo_root>
<logs_dir> holds verify_<tag>_<fbx|glb>.log (output of verify_export.py) and build_<tag>.log (output of build_model.py)."""
import sys, os, re, json

logs, models, root = sys.argv[1:4]

FACE_DE = {"turbo": "8.3", "cowboy": "5.3"}
FACE_NOTE = {"turbo": "(顔のテクスチャだけ、追加依頼で参考写真に合わせて補正している。下記「顔の修正」)", "cowboy": "(顔の形状・テクスチャ・サングラスは、追加依頼で参考写真に合わせて修正している。下記「顔とサングラスの修正」)", "alone": "", "gray": ""}

MODELS = {
    "turbo": dict(name="Oliver_Turbo_A_Pose", short="Turbo", above="最大 0.11 mm", desc="ピンク×青のジャケット / 赤いサングラス / ボウルカット",
                  hands="4本の指先が個別に検出できたため、各指の軸(断面ループ追跡)に沿って指と指の接触部をブーリアンで切り離した(指の長さの約80%まで)。",
                  face=True),
    "cowboy": dict(name="Oliver_Cowboy_Tears_A_Pose", short="Cowboy", extra="* **サングラス**: 作り直した丸型サングラス(マテリアル `Glasses_Frame` / `Glasses_Lens`、2583 頂点)は `Head` ボーン 100% で固定。口のシェイプキーで動く量は最大 0.15 mm(測定値)。", above="最大 1.02 mm(`jawOpen` による。顎の動きが頬横の髪の一部にわずかに伝わる。他のキーは 0.81 mm 以下)", desc="カウボーイハット / 青いフリンジジャケット / 丸サングラス / ヤギひげ",
                   hands="元メッシュの指は4本が癒着した『ミトン状』で指先も分離していなかった。手の形状から4本の指軸を推定し、指先側から指の長さの約80%までスリットを新規に彫り込んで独立して曲がる指にした(付け根側の約20%は水かき状につながったまま)。",
                   face=True),
    "alone": dict(name="Oliver_Alone_In_A_Crowd_A_Pose", short="Alone", above="最大 0.11 mm", desc="マゼンタのロングコート / ボブヘア / サングラス / 口ひげ",
                  hands="4本の指先が個別に検出できたため、各指の軸に沿って指と指の接触部をブーリアンで切り離した(指の長さの約80%まで)。肌が暗い色でも手の領域を拾えるよう、色相・彩度ベースの肌判定を使った。",
                  face=False),
    "gray": dict(name="Oliver_Gray_Suit_A_Pose", short="Gray", above="最大 0.11 mm", desc="グレーのスーツ / 黒いロングヘア / 口ひげ",
                 hands="元メッシュの指は癒着していた(Cowboyと同様)。指軸を推定して指先側から約80%までスリットを新規に彫り込んだ。付け根側の約20%は水かき状につながったまま。",
                 face=False),
}


def parse_verify(path):
    d = dict(keys={})
    if not os.path.exists(path):
        return d
    for line in open(path, errors="ignore"):
        if not line.startswith("VERIFY"):
            continue
        m = re.match(r"VERIFY mesh (\S+) verts (\d+) polys (\d+)", line)
        if m:
            d["verts"], d["polys"] = int(m.group(2)), int(m.group(3))
        m = re.match(r"VERIFY bones (\d+) missing required: (\[.*\])", line)
        if m:
            d["bones"], d["missing"] = int(m.group(1)), m.group(2)
        m = re.match(r"VERIFY vertex groups (\d+) finger groups present: (\d+)", line)
        if m:
            d["vgroups"], d["fingergroups"] = int(m.group(1)), int(m.group(2))
        m = re.match(r"VERIFY weighted vertices: (\d+) / (\d+)", line)
        if m:
            d["weighted"], d["nverts"] = int(m.group(1)), int(m.group(2))
        m = re.match(r"VERIFY shape keys: (\[.*\])", line)
        if m:
            d["shapekeys"] = eval(m.group(1))
        m = re.match(r"VERIFY fist\(R\): vertices with finger weight>0.5: (\d+), their mean move ([\d.]+) mm .* zero finger weight moving >0.5mm: (\d+)", line)
        if m:
            d["fist_n"], d["fist_move"], d["fist_stray"] = int(m.group(1)), float(m.group(2)), int(m.group(3))
        m = re.match(r"VERIFY sleeve.*max move under finger fist: ([\d.]+) mm", line)
        if m:
            d["sleeve"] = float(m.group(1))
        m = re.match(r"VERIFY key (\S+)\s+moves\s+(\d+) verts, max ([\d.]+) mm", line)
        if m:
            d["keys"][m.group(1)] = (int(m.group(2)), float(m.group(3)))
        m = re.match(r"VERIFY texture \S+ (?:\S+ )*?(\S+\.png|\S+) \((\d+), (\d+)\) has_data (\w+)", line)
        if "VERIFY texture" in line:
            d.setdefault("textures", []).append(line.strip()[len("VERIFY texture "):])
        m = re.match(r"VERIFY actions: (\[.*\])", line)
        if m:
            d["actions"] = m.group(1)
    return d


def parse_build(path):
    d = {}
    for line in open(path, errors="ignore") if os.path.exists(path) else []:
        m = re.search(r"clearance to outer skin \(mm\): (.*)", line)
        if m:
            d["clear"] = m.group(1).strip()
        m = re.search(r"thumb fist solutions (\{.*\})", line)
        if m:
            try:
                d["thumb"] = eval(m.group(1))
            except Exception:
                pass
    return d


def parse_anim(path):
    rows = []
    last = None
    if not os.path.exists(path):
        return rows, last
    for line in open(path, errors="ignore"):
        m = re.match(r"VANIM (\S+)\s+frames (\d+)-(\d+)\s+peak mean move \(mm\): (.*)  Jaw=([\d.]+)", line)
        if m:
            vals = dict(kv.split("=") for kv in m.group(4).split())
            rows.append((m.group(1), m.group(2) + "–" + m.group(3), vals, float(m.group(5))))
        m = re.match(r"VANIM last frame vs frame 1: max vertex difference ([\d.]+) mm", line)
        if m:
            last = float(m.group(1))
    return rows, last


def fmt_anim(rows):
    out = []
    order = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
    for seg, fr, vals, jaw in rows:
        l = "/".join(vals.get(f"L_{f}", "0") for f in order)
        r = "/".join(vals.get(f"R_{f}", "0") for f in order)
        out.append(f"| {seg} | {fr} | {l} | {r} | {jaw:.1f} |")
    return "\n".join(out)


def fmt_clear(s):
    out = []
    for part in s.split(","):
        part = part.strip()
        m = re.match(r"(\w+): min ([\d.]+) viol (\d+)/(\d+)", part)
        if m:
            out.append(f"| {m.group(1)} | {m.group(2)} mm | {m.group(3)} / {m.group(4)} |")
    return "\n".join(out)


BONES = """```
Hips
└ Spine ─ Spine1 ─ Spine2
   ├ Neck ─ Head ─ Jaw                         (Jaw = 下顎。口を開く)
   ├ LeftShoulder ─ LeftArm ─ LeftForeArm ─ LeftHand
   │    └ LeftHand{Index|Middle|Ring|Pinky}{1,2,3}   (各指3関節)
   │    └ LeftHandThumb{1,2,3}
   ├ RightShoulder ─ RightArm ─ RightForeArm ─ RightHand
   │    └ RightHand{Index|Middle|Ring|Pinky}{1,2,3}
   │    └ RightHandThumb{1,2,3}
   ├ LeftUpLeg ─ LeftLeg ─ LeftFoot ─ LeftToeBase
   └ RightUpLeg ─ RightLeg ─ RightFoot ─ RightToeBase
```"""

for tag, m in MODELS.items():
    name = m["name"]
    vf = parse_verify(os.path.join(logs, f"verify_{tag}_fbx.log"))
    vg = parse_verify(os.path.join(logs, f"verify_{tag}_glb.log"))
    b = parse_build(os.path.join(logs, f"build_{tag}.log"))
    af, af_last = parse_anim(os.path.join(logs, f"anim_{tag}_fbx.log"))
    ag, ag_last = parse_anim(os.path.join(logs, f"anim_{tag}_glb.log"))
    thumb = b.get("thumb", {})
    thumb_s = ", ".join(f"{s}: {thumb[s]['dist_mm']:.1f} mm" for s in ("R", "L") if s in thumb)
    keys_rows = "\n".join(f"| {k} | {vf['keys'][k][0]:,} | {vf['keys'][k][1]:.1f} mm |" for k in vf.get("keys", {}))
    face_section = ""
    if tag == "turbo":
        face_section = f"""
## 顔の修正(追加依頼: 参考写真に合わせて顔を直す)

`reference/turbo_reference_photo.png` に合わせて**顔のテクスチャ**を補正した(髪・サングラス・服・手・リグは変更なし。顔のメッシュはランドマーク比較で写真と 1〜3 mm 以内に一致していたため形状は触っていない)。

1. 参考写真(顔幅 約150px)を **GFPGAN v1.4**(顔復元 AI、ONNX・CPU 実行)で 3 倍に超解像して顔の細部(目鼻口・皮膚の質感)を復元
2. 写真とモデル正面レンダの両方で MediaPipe 顔ランドマーク(478点)を検出し、Thin-Plate-Spline で写真をモデルの正面ビューへ歪ませて重ねる
3. 正面ビュー上で肌の色・陰影・立体感(鼻筋、頬、唇の形と色、顎のライン)を写真のものに置き換え、色味は写真の肌に寄せる(髪・サングラス・襟の近くは補正を弱めて元のテクスチャを保持)
4. 差分をカメラに正対し視認できるテクセルだけ 8K テクスチャに焼き込み(UV・メッシュは不変)

比較(左: 参考写真をモデル正面に合わせたもの / 中: 修正前 / 右: 修正後): `face_fix/turbo_face_compare.png`。
顔領域の平均色差(Lab ΔE。写真をモデルの顔に歪ませて重ねたものとの色の差。目の周りの帯(サングラス)は除く。値が小さいほど写真に近い): **修正前 13.9 → 修正後 {FACE_DE['turbo']}**。

**限界**: 参考写真は正面1枚のため、奥行き方向(鼻の高さ、顎の彫り)は写真から復元できない。顔の凹凸はメッシュ側の形状に依存している。サングラスで隠れた目・眉は写真にも写っていないので再現していない。AI 顔復元で細部を補っているため、ホクロ・肌の細かい凹凸などは「写真に写っている実物」ではなく推定で補った質感になる。
"""
    elif tag == "cowboy":
        face_section = f"""
## 顔とサングラスの修正(追加依頼: 参考写真に合わせて顔を直す / サングラスが変なので直す)

`reference/cowboy_reference_photo.jpg` に合わせて**顔の形状・テクスチャ・サングラス**を修正した(髪・帽子・服・手・リグの構造は変更なし)。

**顔の形状**: 写真とモデル正面レンダの顔ランドマーク差(輪郭・頬・顎。最大 約12 mm、顎は写真の方が約6 mm 低く、頬骨は約12 mm 下)を Thin-Plate-Spline でメッシュに反映して顔の頂点を動かした(唇・鼻は固定、顔の外周でフェードアウト。顔の前面だけ動かす)。

**サングラス(元のモデルは壊れていた)**: 元メッシュのサングラスは立体として不完全だった(レンズの立体は片側にしか残っておらず、反対側は黒い円がテクスチャに描かれているだけ。テンプルは耳の手前で崩れ、ブリッジと鼻パッドは凸凹のかたまり)。顔の皮膚表面より手前に飛び出している頂点を検出して**元のサングラス形状をすべて撤去**し、穴を皮膚で埋めた上で、写真の位置・大きさに合わせて**新しい丸型サングラスを作り直した**(左右対称の丸レンズ2枚 + 細い金属リム + ブリッジ + 鼻パッド + 耳まで届くテンプル。フレームは金属マテリアル `Glasses_Frame`、レンズは濃い色付きガラス `Glasses_Lens`。頭ボーンに固定)。元のテクスチャに描き込まれていたサングラスの線・影は写真から塗り直した。

**顔のテクスチャ**: 参考写真(顔幅 約150px)を **GFPGAN v1.4**(顔復元 AI、ONNX・CPU 実行)で超解像し、ランドマークで正面ビューに歪ませて、肌・ヤギひげの色・陰影・形・唇・鼻筋を写真のものに置き換えた(髪・帽子・襟の近くは元のテクスチャを保持)。差分は 8K テクスチャに焼き込み。

比較(左: 参考写真をモデル正面に合わせたもの / 中: 修正前 / 右: 修正後): `face_fix/cowboy_face_compare.png`。
顔領域の平均色差(Lab ΔE。写真をモデルの顔に歪ませて重ねたものとの色の差。目の周りの帯(サングラス)は除く。値が小さいほど写真に近い): **修正前 23.3 → 修正後 {FACE_DE['cowboy']}**。

**限界**: 参考写真は正面1枚なので、奥行き(鼻の高さ・眉の出方)は写真から復元できず、鼻などの奥行きの形はメッシュ元のまま。顔の動かす量は写真との輪郭の差に基づく推定。AI 顔復元の細部は推定で補ったもの。レンズは写真のような「瞼の影が映り込む艶のあるガラス」ではなく単色の濃色ガラス。口の位置が約3 mm 下がったため口(唇のしわ位置)を測り直して口の構造を作り直した。
"""
    txt = f"""# {name} — 指と口が動くリグ付きモデル

{m['desc']}。Meshy 由来の静的メッシュ(単一メッシュ)を、元の見た目(形状・色・UV・テクスチャ)を保ったまま、指と口が動くキャラクターに加工したもの。{FACE_NOTE[tag]}

## 納品物

| ファイル | 内容 |
|---|---|
| `{name}_rigged.blend` | 編集用 Blender 4.5 ファイル(リグ・ウェイト・シェイプキー・チェック用アニメ入り。テクスチャは `textures/` を相対パスで参照) |
| `{name}.fbx` | FBX(ボーン・ウェイト・口のブレンドシェイプ・チェックアニメ。テクスチャは `textures/` を相対パスで参照、ベースカラー+ノーマル) |
| `{name}.glb` | glTF Binary(スキン・モーフターゲット・アニメ。テクスチャ埋め込み、ベースカラーは JPEG q92 に再エンコード) |
| `textures/` | `base_color`(8192²) / `normal`(4096²) / `roughness` / `metallic` / `metallic_roughness`(G=roughness, B=metallic のパック版) |
| `{name}_check.mp4` | 動作確認動画(手を開く→握る→開く / 指1本ずつ / 人差し指・ピース / 口の開閉 / あいうえお / 笑顔→通常) |

モデルは A ポーズ(腕・胴・脚が離れた状態)で開く。キャラクターは **-Y 方向を向き、+Z が上**(Blender 座標、1 unit = 1 m)。`Right` はキャラクターの右手(-X 側)。

## ボーン(Mixamo 風の命名、`mixamorig:` 接頭辞なし。全 53 本)

{BONES}

* 指は左右とも**5本独立**(親指 + 人差し指/中指/薬指/小指 × 各3関節)。
* **指の曲げ**: 各指ボーンを**ローカル X 軸まわりに回転**(正の角度 = 手のひら側へ曲がる)。回転モードは Quaternion。握りの目安は MCP/PIP/DIP で約 80° / 100° / 60°。
* **親指**は対向(オポジション)を含むため単純な X 回転では握れない。`tools/oliver_rig/rig_poses.py` の `thumb_pose(arm, 'R', 0..1)`(最適化で求めた握り姿勢を `Armature["oliver_thumb"]` に保存)か、チェックアニメのキーを使う。`fist(arm, side)` / `point` / `peace` / `finger_pose(arm, side, 'Index', 0..1)` も同ファイル。
* **指の開閉でも袖・胴は動かない**(検証値は下表。袖/上腕の頂点の最大移動量 0.000 mm)。

## 口・表情(シェイプキー。0〜1)

| 名前 | 動き |
|---|---|
| `jawOpen` | 下顎を開く(最大 約13°相当) |
| `mouthClose` | 唇を閉じ合わせる(わずかに開いた顎を封じる。`jawOpen`≲0.12 まで有効) |
| `viseme_A` (あ) | 大きく縦に開く |
| `viseme_I` (い) | 横に引く(口角を外へ)、顎は小さく |
| `viseme_U` (う) | すぼめて前に突き出す(すぼめ+口幅を狭める) |
| `viseme_E` (え) | 中くらい開き + 横に引く |
| `viseme_O` (お) | 丸く開く(すぼめ+前へ) |
| `mouthSmile` | 口角を上げ、頬を持ち上げる(顎は動かない) |

* **口の構造**: 閉じた一枚の表面だった口を、唇のしわ(幾何の谷)に沿って実際に切り開き、上唇・下唇の裏側から奥へ続く口腔(口内壁)、**上下の歯**、**舌**を追加した(黒い板や顔面の引き伸ばしではない)。口を閉じれば元の顔に戻る。
* **Jaw ボーン**でも口を開ける(ローカル X 軸 正回転、最大 約13°)。`jawOpen` キーと同じ動きになるよう作ってあり(平均差 約0.5 mm)、**両方を同時に最大にすると二重に開く**ので、どちらか一方で使うこと。
* 歯と舌は顎にだけ追従し、口をすぼめる音(う・お)では口腔と一緒に横幅を縮める。ひげ・口ひげはテクスチャとして皮膚の一部なので、口まわりでは皮膚と一緒に動く。**口の中心より 50 mm 以上上(鼻・サングラス・髪・帽子)の頂点の最大変位は {m['above']}**。顎の開閉は下あご〜喉の皮膚にも自然に伝わる(ボーン/キーとも)。
* 音声なし。口の動きはキー値で操作する(下記チェックアニメ、またはスライダー/スクリプト)。

## チェック用アニメーション(24 fps、全 636 フレーム)

`Check_All`(ボーン)+ `Check_All_Keys`(シェイプキー)が全区間を連結したもの(FBX / GLB にはこれが焼き込まれている)。個別アクションも .blend に入っている(NLA にも格納、ミュート済み)。

| 区間(連結タイムライン上のフレーム) | アクション名 | 内容 |
|---|---|---|
| 1–57 | `Hands_OpenCloseOpen` | 両手 開く → 握る → 開く |
| 58–250 | `Fingers_Individual` | 左右・親指/人差し/中/薬/小指を1本ずつ曲げる |
| 251–353 | `Point_Peace` | 人差し指で指す → ピース |
| 354–456 | `Mouth_OpenClose_Keys` | 口 閉 → 開 → 閉 |
| 457–579 | `Vowels_AIUEO_Keys` | あ → い → う → え → お |
| 580–636 | `Smile_Normal_Keys` | 笑顔 → 通常 |

## このモデル固有の加工内容

* **指**: {m['hands']}
{m.get('extra', '')}
* **親指の握り**: 最適化で求めた握り姿勢の指先到達誤差(目標との距離) {thumb_s}。
* **口腔のクリアランス**(口内パーツ頂点から外側の皮膚面までの最小距離。皮膚を突き抜けたら違反):

| パーツ | 最小クリアランス | 違反頂点 |
|---|---|---|
{fmt_clear(b.get('clear', ''))}
{face_section}
## 検証結果(書き出した FBX / GLB を**空のシーンに再読込**して計測)

| 項目 | FBX | GLB |
|---|---|---|
| 頂点 / 三角形 | {vf.get('verts', 0):,} / {vf.get('polys', 0):,} | {vg.get('verts', 0):,} / {vg.get('polys', 0):,} (GLB はUV/法線の分割で頂点が増える) |
| ボーン数(必須ボーン欠落) | {vf.get('bones')} ({vf.get('missing')}) | {vg.get('bones')} ({vg.get('missing')}) |
| 頂点グループ(うち指) | {vf.get('vgroups')} ({vf.get('fingergroups')}) | {vg.get('vgroups')} ({vg.get('fingergroups')}) |
| ウェイト付き頂点 | {vf.get('weighted'):,} / {vf.get('nverts'):,} | {vg.get('weighted'):,} / {vg.get('nverts'):,} |
| シェイプキー | {', '.join(vf.get('shapekeys', [])[1:])} | 同左 |
| 右手を握る: 指ウェイト>0.5 の頂点の平均移動量 | {vf.get('fist_move')} mm({vf.get('fist_n'):,} 頂点) | {vg.get('fist_move')} mm({vg.get('fist_n'):,} 頂点) |
| 〃: 指ウェイト0なのに0.5mm以上動いた頂点 | {vf.get('fist_stray')} | {vg.get('fist_stray')} |
| 〃: 袖・上腕(ForeArm/Arm ウェイト>0.9)の最大移動量 | {vf.get('sleeve')} mm | {vg.get('sleeve')} mm |
| テクスチャ | ベースカラー 8192² / ノーマル 4096² 読込OK(外部参照) | ベースカラー 8192² / MR 4096² / ノーマル 4096² 読込OK(埋め込み) |

再読込後の各シェイプキーの変形(FBX):

| キー | 動く頂点数 | 最大変位 |
|---|---|---|
{keys_rows}

## アニメの再生検証(再読込した FBX / GLB を空シーンで再生)

連結アニメ(636 フレーム)を再生し、各区間で「その指(ウェイト>0.5 の頂点)/ 顎(Jaw ウェイト>0.5 の頂点)」が**フレーム1(A ポーズ)から平均で何 mm 動いたか**の最大値。
指は 親/人差/中/薬/小(mm)。1本ずつ曲げる区間(`Fingers_Individual`)で左右10本すべてが動いていること、握る区間・口の区間で対応部位が動くことを確認。

FBX:

| 区間 | フレーム | 左手 親/人/中/薬/小 | 右手 親/人/中/薬/小 | Jaw |
|---|---|---|---|---|
{fmt_anim(af)}

最終フレームと 1 フレーム目の最大頂点差: {af_last} mm(A ポーズに戻る)。GLB でも同様(最終フレーム差 {ag_last} mm、区間ごとの値は `tools/oliver_rig/verify_anim.py` で再現できる):

| 区間 | フレーム | 左手 親/人/中/薬/小 | 右手 親/人/中/薬/小 | Jaw |
|---|---|---|---|---|
{fmt_anim(ag)}

## 制約・既知の問題

* スキニングは自動(測地距離ベース + 手指は関節チェーンから明示計算)。**服・髪・帽子・フリンジは肌と同じスキニング**で、布や髪の物理シミュレーションはない(腕を大きく動かすと服の変形は線形ブレンドスキンの限界が出る)。
* 口腔は様式化したもの(単色の口内壁、簡易な超楕円体の歯と舌、舌ボーンなし)。母音の形は近似で、実際の発話の口形をすべて再現するものではない。
* 指の独立した曲げは水かき状につながった部分(癒着していた手の付け根側)を引き伸ばす。ピースサインで2本が離れる量は小さい。
* FBX はベースカラー+ノーマルのみ(roughness/metallic は `textures/` と GLB に収録)。GLB のベースカラーは JPEG。
* 元のメッシュは三角形のみ・単一メッシュで、頂点法線は(編集後に)自動スムースで再計算されている。
"""
    out = os.path.join(models, name, "README.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write(txt)
    print("wrote", out)


# ------------------------------------------------------------------------------------------------------------------
# top-level README
# ------------------------------------------------------------------------------------------------------------------
def size_mb(p):
    return os.path.getsize(p) / 1e6 if os.path.exists(p) else 0.0


rows = []
for tag, m in MODELS.items():
    n = m["name"]
    d = os.path.join(models, n)
    parts = {}
    for ext in (".blend", ".fbx", ".glb"):
        base = f"{n}_rigged.blend" if ext == ".blend" else f"{n}{ext}"
        p = os.path.join(d, base)
        if os.path.exists(p):
            parts[ext] = f"[{ext[1:]}](models/{n}/{base}) ({size_mb(p):.0f} MB)"
        else:
            segs = sorted(f for f in os.listdir(d) if f.startswith(base + ".part"))
            tot = sum(size_mb(os.path.join(d, f)) for f in segs)
            parts[ext] = f"{ext[1:]} (分割 {len(segs)} 個, 計 {tot:.0f} MB — 下記「大きなファイル」参照)" if segs else f"{ext[1:]} (なし)"
    mp4 = f"[mp4](models/{n}/{n}_check.mp4)" if os.path.exists(os.path.join(d, f"{n}_check.mp4")) else "mp4 (なし)"
    rows.append(f"| **{m['short']}** [`{n}`](models/{n}/README.md) | {parts['.blend']} | {parts['.fbx']} | {parts['.glb']} | [textures](models/{n}/textures) | {mp4} |")

vsum = []
for tag, m in MODELS.items():
    vf = parse_verify(os.path.join(logs, f"verify_{tag}_fbx.log"))
    vg = parse_verify(os.path.join(logs, f"verify_{tag}_glb.log"))
    vsum.append(f"| {m['short']} | {vf.get('bones')} | {vf.get('fingergroups')} | {vf.get('weighted', 0):,}/{vf.get('nverts', 0):,} | "
                f"{vf.get('fist_move')} / {vg.get('fist_move')} mm | {vf.get('sleeve')} / {vg.get('sleeve')} mm | "
                f"{vf.get('keys', {}).get('jawOpen', (0, 0))[1]:.0f} mm |")

top = f"""# Oliver Tree 4体 — 指と口が動くキャラクター化

Meshy 由来の静的メッシュ 4 体(`Oliver_Turbo_A_Pose` / `Oliver_Cowboy_Tears_A_Pose` / `Oliver_Alone_In_A_Crowd_A_Pose` / `Oliver_Gray_Suit_A_Pose`)を、
元の見た目(形状・色・UV・テクスチャ)を保ったまま、**指先と口まで動くキャラクター**に加工したもの。元データ(https://gofile.io/d/TiBYhFNZ)は変更せず、複製に対して作業している。
Blender 4.5.14(ヘッドレス)+ Python のみ。API キー・有料サービスは使っていない(顔の補正にだけ MediaPipe の顔ランドマーク検出器を使用)。

## 納品物

| モデル | .blend | FBX | GLB | テクスチャ | 動作確認動画 |
|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

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
""" + "\n".join(vsum) + f"""

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
"""
open(os.path.join(root, "README.md"), "w").write(top)
print("wrote", os.path.join(root, "README.md"))
