"""Write models/<Name>/README.md for the four delivered characters and the top-level README.md.
python3 tools/make_readmes.py <logs_dir> <models_dir> <repo_root> [tag ...]
<logs_dir> holds verify_<tag>_<fbx|glb>.log (output of verify_export.py), anim_<tag>_<fbx|glb>.log (verify_anim.py), build_<tag>.log (build_model.py)
and keyreach_<tag>.log (key_reach.py). Without tags all four model READMEs are written, otherwise only the named ones (the top-level README is always written)."""
import sys, os, re, json

logs, models, root = sys.argv[1:4]
ONLY = sys.argv[4:]
SRC_NEW = "作り直された Meshy FBX(`{f}.fbx`。https://gofile.io/d/tVUQudhH)"

MODELS = {
    "turbo": dict(name="Oliver_Turbo_A_Pose", short="Turbo", remade="Turbo", desc="ピンク×青のジャケット / 赤いサングラス / ボウルカット",
                  hands="4本の指は元メッシュで互いに接していた(癒着した状態)。手の形状から4本の指軸と指先を推定し、指と指の接触部を、指先側から指の長さの約80%までブーリアンで切り離して独立して曲がる指にした(付け根側の約20%は水かき状につながったまま)。切り離しで露出した面は単色の肌色にしてある。",
                  mouth="口の位置は顔の深度の谷(唇のしわ)を測って決めた(口角 x = -25〜+25 mm)。"),
    "cowboy": dict(name="Oliver_Cowboy_Tears_A_Pose", short="Cowboy", remade="Cowboy", desc="カウボーイハット / 青いフリンジジャケット / 丸サングラス / ヤギひげ",
                   hands="元メッシュ(溶接後 約5.1万頂点)は間引かれていて粗く、指と指がほぼ接していた。手と口まわりだけを**局所的に細分化**(辺長 約5 mm → 約1.2 mm。細分化後 約14万頂点)してから、4本の指軸と指先を推定し、指と指の接触部を指先側から指の長さの約80%までブーリアンで切り離した(付け根側の約20%は水かき状につながったまま)。切り離しで露出した面は単色の肌色にしてある。",
                   mouth="口の位置は顔の深度の谷(唇のしわ)を測って決めた(口角 x = -30〜+14 mm)。口まわりも同様に局所細分化している。"),
    "alone": dict(name="Oliver_Alone_In_A_Crowd_A_Pose", short="Alone", desc="マゼンタのロングコート / ボブヘア / サングラス / 口ひげ",
                  hands="4本の指先が個別に検出できたため、各指の軸に沿って指と指の接触部をブーリアンで切り離した(指の長さの約80%まで)。肌が暗い色でも手の領域を拾えるよう、色相・彩度ベースの肌判定を使った。"),
    "gray": dict(name="Oliver_Gray_Suit_A_Pose", short="Gray", desc="グレーのスーツ / 黒いロングヘア / 口ひげ",
                 hands="元メッシュの指は癒着していた(Cowboyと同様)。指軸を推定して指先側から約80%までスリットを新規に彫り込んだ。付け根側の約20%は水かき状につながったまま。"),
}
REMADE = ("turbo", "cowboy")


def tex_summary(v):
    """e.g. 'base_color 4096² / normal 4096²' from the VERIFY texture lines of a re-imported file."""
    out = []
    for line in v.get("textures", []):
        m = re.search(r"(BASE COLOR|NORMAL MAP|METALLIC ROUGHNESS|\S*_(base_color|normal|metallic_roughness)\S*?)\s.*?\((\d+), (\d+)\)", line)
        if m:
            kind = "base_color" if ("BASE" in m.group(1) or "base_color" in m.group(1)) else ("normal" if ("NORMAL" in m.group(1) or "normal" in m.group(1)) else "metallic_roughness")
            out.append(f"{kind} {m.group(3)}²")
    return " / ".join(dict.fromkeys(out)) or "?"


def parse_keyreach(path):
    d = {}
    if os.path.exists(path):
        for line in open(path, errors="ignore"):
            m = re.match(r"KEYREACH max ([\d.]+) mm by (\S+)", line)
            if m:
                d["max"], d["by"] = float(m.group(1)), m.group(2)
            m = re.match(r"KEYREACH Jaw-bone weight above (\d+) mm: max ([\d.]+)", line)
            if m:
                d["jaw_w"] = float(m.group(2))
    return d


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
    if ONLY and tag not in ONLY:
        continue
    name = m["name"]
    vf = parse_verify(os.path.join(logs, f"verify_{tag}_fbx.log"))
    vg = parse_verify(os.path.join(logs, f"verify_{tag}_glb.log"))
    b = parse_build(os.path.join(logs, f"build_{tag}.log"))
    af, af_last = parse_anim(os.path.join(logs, f"anim_{tag}_fbx.log"))
    ag, ag_last = parse_anim(os.path.join(logs, f"anim_{tag}_glb.log"))
    thumb = b.get("thumb", {})
    thumb_s = ", ".join(f"{s}: {thumb[s]['dist_mm']:.1f} mm" for s in ("R", "L") if s in thumb)
    SEG_DESC = {"Hands_OpenCloseOpen": ("`Hands_OpenCloseOpen`", "両手 開く → 握る → 開く"),
                "Fingers_Individual": ("`Fingers_Individual`", "左右・親指/人差し/中/薬/小指を1本ずつ曲げる"),
                "Point_Peace": ("`Point_Peace`", "人差し指で指す → ピース"),
                "Mouth_OpenClose": ("`Mouth_OpenClose_Keys`", "口 閉 → 開 → 閉"),
                "Vowels_AIUEO": ("`Vowels_AIUEO_Keys`", "あ → い → う → え → お"),
                "Smile_Normal": ("`Smile_Normal_Keys`", "笑顔 → 通常"),
                "Expressions": ("`Expressions_Keys`", "細かい表情キー(片側の笑顔・への字・口角を引く・すぼめ・口の横ずらし・唇の片側・顎の前後左右・頬のふくらみ・舌)を順に確認"),
                "Speech_Gestures": ("`Speech_Gestures` + `Speech_Gestures_Keys`", "「こんにちは、オリバーです。よろしくね。」を話す + 呼吸・体重移動・頭の揺れ・うなずき・お辞儀・手のジェスチャー")}
    seg_rows = "\n".join(f"| {fr.replace('–', '–')} | {SEG_DESC[seg][0]} | {SEG_DESC[seg][1]} |" for seg, fr, vals, jaw in af if seg in SEG_DESC)
    total = af[-1][1].split("–")[1] if af else "?"
    keys_rows = "\n".join(f"| {k} | {vf['keys'][k][0]:,} | {vf['keys'][k][1]:.1f} mm |" for k in vf.get("keys", {}))
    remade = tag in REMADE
    kr = parse_keyreach(os.path.join(logs, f"keyreach_{tag}.log"))
    above = m.get("above") or f"最大 {kr.get('max', 0):.2f} mm(`{kr.get('by', '')}` による。顎ボーンのウェイトは 0)"
    if remade:
        intro = (f"{m['desc']}。{SRC_NEW.format(f=m['remade'])}を、元の見た目(形状・色・UV・テクスチャ)を保ったまま、指と口が動くキャラクターに加工したもの。"
                 "元ファイルに付いていた Meshy の自動リグ(24 ボーン、指・顎なし)とそのアニメーションは使わず、下記の 53 ボーンのリグに作り直している。")
        tex_files = "`base_color`(4096²) / `normal`(4096²)(元データに roughness / metallic のマップは無い。マテリアルは roughness 0.6 / metallic 0 の固定値)"
        origin = f"""
## 元データと加工の範囲(作り直し版)

* 元データ: {SRC_NEW.format(f=m['remade'])}。メッシュは UV の継ぎ目で頂点が分かれていたため、同じ位置の頂点を溶接して一枚の連続した面にしてから加工した(形状は変えていない)。元の `.fbx` は変更していない。
* **加工した場所**: 手(指の切り離し)と口まわり(唇の開口・口腔・歯・舌)だけ。顔・髪・服・サングラス・帽子の形状と色は元データのまま。
* **サングラスの色**: 元データのテクスチャでサングラスと肌の色が混ざっている部分があるが、依頼により**修正していない(元のまま)**。
* 顔の作り直し(参考写真に合わせた顔の補正)はこの版では行っていない。
"""
        extra_lim = """* **元データに roughness / metallic マップが無い**ため、材質は固定値(roughness 0.6 / metallic 0)。FBX / GLB / .blend ともベースカラー+ノーマルのみ。GLB のベースカラーは JPEG(q92)に再エンコードされている。
* **口を閉じるキー `mouthClose`**(唇を強く閉じ合わせる)では、唇の合わせ目にごく小さな(1 mm 以下の)ギザつきが出ることがある(ひげのテクスチャで目立つ)。通常の閉じた口は元の顔(キー 0)で、そこには出ない。
* 指を1本だけ曲げると、癒着していた指の間の面(水かき状の部分と切り口)が引き伸ばされ、平らな肌色の「ひれ」状に見えることがある(Cowboy で目立つ)。切り口の面は単色の肌色で、元のテクスチャの質感はない。"""
    else:
        intro = f"{m['desc']}。Meshy 由来の静的メッシュ(単一メッシュ)を、元の見た目(形状・色・UV・テクスチャ)を保ったまま、指と口が動くキャラクターに加工したもの。"
        tex_files = "`base_color`(8192²) / `normal`(4096²) / `roughness` / `metallic` / `metallic_roughness`(G=roughness, B=metallic のパック版)"
        origin = ""
        extra_lim = "* FBX はベースカラー+ノーマルのみ(roughness/metallic は `textures/` と GLB に収録)。GLB のベースカラーは JPEG。"
    tex_row = f"| テクスチャ | {tex_summary(vf)} 読込OK(外部参照) | {tex_summary(vg)} 読込OK(埋め込み) |"
    txt = f"""# {name} — 指と口が動くリグ付きモデル

{intro}

## 納品物

| ファイル | 内容 |
|---|---|
| `{name}_rigged.blend` | 編集用 Blender 4.5 ファイル(リグ・ウェイト・シェイプキー・チェック用アニメ入り。テクスチャは `textures/` を相対パスで参照) |
| `{name}.fbx` | FBX(ボーン・ウェイト・口のブレンドシェイプ・チェックアニメ。テクスチャは `textures/` を相対パスで参照、ベースカラー+ノーマル) |
| `{name}.glb` | glTF Binary(スキン・モーフターゲット・アニメ。テクスチャ埋め込み、ベースカラーは JPEG q92 に再エンコード) |
| `textures/` | {tex_files} |
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
| `mouthSmileLeft` / `mouthSmileRight` | 片側だけ口角を上げる(Left / Right はキャラクター自身の左右。+X が左) |
| `mouthFrownLeft` / `mouthFrownRight` | 片側の口角を下げる(への字) |
| `mouthStretchLeft` / `mouthStretchRight` | 片側の口角を横に引く |
| `mouthPucker` | 顎を動かさずに唇をすぼめて前に出す |
| `mouthFunnel` | 丸く開いて唇を前に突き出す(「お」より前に出る) |
| `mouthLeft` / `mouthRight` | 口全体を横にずらす(歯も一緒に動く) |
| `mouthUpperUpLeft` / `mouthUpperUpRight` | 上唇を片側ずつ持ち上げる |
| `mouthLowerDownLeft` / `mouthLowerDownRight` | 下唇を片側ずつ下げる |
| `jawForward` / `jawLeft` / `jawRight` | 下顎を前 / 左 / 右にずらす |
| `cheekPuff` | 頬をふくらませる |
| `tongueOut` / `tongueUp` | 舌を出す / 舌先を上げる(口を開けているとき、`jawOpen` 0.7 以上で使う) |


キーは足し算で効く(複数を同時に使える)。上のうち最初の 8 個が基本、残り 20 個は細かい表情・発話用の追加キー(名前は ARKit 風)。
* **口の構造**: 閉じた一枚の表面だった口を、唇のしわ(幾何の谷)に沿って実際に切り開き、上唇・下唇の裏側から奥へ続く口腔(口内壁)、**上下の歯**、**舌**を追加した(黒い板や顔面の引き伸ばしではない)。口を閉じれば元の顔に戻る。
* **開口の形**: 口の開きは長方形ではなく**楕円(レンズ)形**になるようにしてある(下唇のふちの顎ウェイトを口の幅方向になめらかに変え、口角はほぼ動かさず、ふちから顎までの皮膚が段階的に伸びる)。口を開くと**上唇もわずかに上がる**(`jawOpen` 最大で約2 mm)。舌は丸みのある先細りの形。
* **Jaw ボーン**でも口を開ける(ローカル X 軸 正回転、最大 約13°)。下顎・下唇の動きは `jawOpen` キーと同じ(同じウェイト)だが、**上唇が上がる分(最大 約2 mm)はキーだけ**にある。**両方を同時に最大にすると二重に開く**ので、どちらか一方で使うこと。
* 歯と舌は顎にだけ追従し、口をすぼめる音(う・お)では口腔と一緒に横幅を縮める。ひげ・口ひげはテクスチャとして皮膚の一部なので、口まわりでは皮膚と一緒に動く。**口の中心より 50 mm 以上上(鼻・サングラス・髪・帽子)の頂点のシェイプキーによる変位は {above}**。顎の開閉は下あご〜喉の皮膚にも自然に伝わる(ボーン/キーとも)。
* 音声なし。口の動きはキー値で操作する(下記チェックアニメ、またはスライダー/スクリプト)。

## チェック用アニメーション(24 fps、全 {total} フレーム)

`Check_All`(ボーン)+ `Check_All_Keys`(シェイプキー)が全区間を連結したもの(FBX / GLB にはこれが焼き込まれている)。個別アクションも .blend に入っている(NLA にも格納、ミュート済み)。

| 区間(連結タイムライン上のフレーム) | アクション名 | 内容 |
|---|---|---|
{seg_rows}

**動きを滑らかに・自然にするための作り**:

* キーフレームは Bezier(自動ハンドル)で補間し、各動作は 5〜12 フレームかけて加速・減速する(線形の機械的な動きではない)。
* **指は一斉に曲がらない**: 人差し指 → 中指 → 薬指 → 小指の順に 1 フレームずつ遅れて曲がり、各指も付け根の関節 → 中間 → 指先の順に 1 フレームずつ遅れる(握る・開くとも)。
* **発話区間**(`Speech_Gestures`): 「こんにちは、オリバーです。よろしくね。」を話す。母音のキー(あ・い・う・え・お)を音節ごとに出し、前後の音節と重ねてガウス平滑化して**唇が次の音を先取りして動く**ようにしてある(調音結合)。バ(b)で唇を閉じ、は(wa)で軽くすぼめ、t / r / n で舌先を上げ、会話らしい控えめな開き(キーの約 9 割)、ゆっくりした笑顔、わずかな振幅のばらつきを加えた。
* 同じ区間に、**呼吸**(胸・肩の微小な上下)、**体重移動**(腰と背骨の揺れ)、**頭のゆっくりした揺れと強勢でのうなずき**、右手の**手のひらを見せるジェスチャー**(あいさつ中)、左手の小さなジェスチャー、「よろしく」でのお辞儀(上体と頭を合わせて約 18° 前に倒す)、**力の抜けた指**(人差し指から小指へ曲がりが増える自然な半握り)を付けてある。
* 音声はない(口の動きは音声の解析ではなく、上の音節表から作った)。

## このモデル固有の加工内容

* **指**: {m['hands']}
{('* **口の位置**: ' + m['mouth']) if m.get('mouth') else ''}
* **親指の握り**: 最適化で求めた握り姿勢の指先到達誤差(目標との距離) {thumb_s}。
* **口腔のクリアランス**(口内パーツ頂点から外側の皮膚面までの最小距離。皮膚を突き抜けたら違反):

| パーツ | 最小クリアランス | 違反頂点 |
|---|---|---|
{fmt_clear(b.get('clear', ''))}
{origin}
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
{tex_row}

再読込後の各シェイプキーの変形(FBX):

| キー | 動く頂点数 | 最大変位 |
|---|---|---|
{keys_rows}

## アニメの再生検証(再読込した FBX / GLB を空シーンで再生)

連結アニメ({total} フレーム)を再生し、各区間で「その指(ウェイト>0.5 の頂点)/ 顎(Jaw ウェイト>0.5 の頂点)」が**フレーム1(A ポーズ)から平均で何 mm 動いたか**の最大値。
指は 親/人差/中/薬/小(mm)。1本ずつ曲げる区間(`Fingers_Individual`)で左右10本すべてが動いていること、握る区間・口の区間で対応部位が動くことを確認。
`Speech_Gestures` 区間の指の値は、腕のジェスチャー・お辞儀・呼吸で**手ごと動いた量**を含む(指を曲げた量ではない)。

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
* 口腔は様式化したもの(単色の口内壁、簡易な超楕円体の歯と舌、舌ボーンなし)。母音の形は近似で、実際の発話の口形をすべて再現するものではない。歯茎は作っていない。
* 追加の細かい表情キー(20 個)は単純な変位場で作った近似。複数を同時に最大にすると唇や歯が重なって見えることがある。`tongueOut` は舌が前に出るだけで、唇・歯との衝突判定はない(口を 0.7 以上開けて使う)。
* 発話デモ(`Speech_Gestures`)は音声のない見本で、日本語の簡単な母音ベースの口形(音節表から作成)。音声の解析で口を動かしているわけではない。呼吸・うなずき・お辞儀・ジェスチャーは小さな手作りの動きで、モーションキャプチャのような実際の人の動きの細かさ(目の動き・まばたき・指先の細かい動き)は再現していない(サングラスで目は見えない)。
* シェイプキーが 28 個(それぞれ全頂点分のデータ)あるため、.blend と GLB のファイルサイズが大きい。
* 指の独立した曲げは水かき状につながった部分(癒着していた手の付け根側)を引き伸ばす。ピースサインで2本が離れる量は小さい。
{extra_lim}
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

vs_all = [parse_verify(os.path.join(logs, f"verify_{t}_fbx.log")).get("verts", 0) for t in MODELS]
vs_txt = f"{min(vs_all) / 1e4:.0f}〜{max(vs_all) / 1e4:.0f} 万頂点"

bigs = []
for tag_, m_ in MODELS.items():
    d_ = os.path.join(models, m_["name"])
    for f_ in sorted(os.listdir(d_)):
        if f_.endswith(".sha256"):
            parts_ = [x for x in os.listdir(d_) if x.startswith(f_[:-7] + ".part-")]
            bigs.append(f"* `models/{m_['name']}/{f_[:-7]}`({len(parts_)} 分割)")
big_files = "\n".join(bigs) if bigs else "(なし)"

top = f"""# Oliver Tree 4体 — 指と口が動くキャラクター化

Meshy 由来の静的メッシュ 4 体(`Oliver_Turbo_A_Pose` / `Oliver_Cowboy_Tears_A_Pose` / `Oliver_Alone_In_A_Crowd_A_Pose` / `Oliver_Gray_Suit_A_Pose`)を、
元の見た目(形状・色・UV・テクスチャ)を保ったまま、**指先と口まで動くキャラクター**に加工したもの。Alone / Gray の元データは https://gofile.io/d/TiBYhFNZ 、
**Turbo / Cowboy は作り直された版**(https://gofile.io/d/tVUQudhH の `Turbo.fbx` / `Cowboy.fbx`)を使っている。元データは変更せず、複製に対して作業している。
Blender 4.5.14(ヘッドレス)+ Python のみ。API キー・有料サービスは使っていない。

## 納品物

| モデル | .blend | FBX | GLB | テクスチャ | 動作確認動画 |
|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

各モデルのフォルダに `README.md`(ボーン名・表情名・操作方法・検証値・制約)がある。モデルはどれも A ポーズで開く。

## やったこと

1. **形状の確認・修正** — 4体とも単一の三角形メッシュ({vs_txt})で、指は癒着(または互いに接した状態)し、口は閉じた一枚の表面だった。
   * **指**: 手の領域を色(肌)+測地距離で切り出し、指先・指軸を推定して、**独立して曲げられるように指と指を切り離した**(ブーリアン。関節部分の頂点も確保)。Alone は元から指先が分かれていたので接触部を切断、Turbo / Cowboy(作り直し版)/ Gray は癒着していたため、指軸を推定して指先側から約80%の長さまでスリットを新規に彫った(Cowboy は元メッシュが粗いので手と口まわりだけを局所的に細分化してから)。
   * **口**: 唇のしわ(幾何の谷)に沿って表面を切り開き、**実際の唇の開口 + 口腔(口内壁)+ 上下の歯 + 舌**を追加した(顔の引き伸ばしや黒い板ではない)。口を閉じれば元の顔に戻る。
2. **全身 + 手指のリグ** — Mixamo 風の命名で 53 ボーン(全身 + 左右各手 **5本の指 × 3関節** + Jaw)。ウェイトは測地距離ベースの自動スキニング + 手指は関節チェーンから明示計算(親指の対向、指を動かしても袖・胴は動かない)。A ポーズ。
3. **口と表情** — 基本のシェイプキー `jawOpen` / `mouthClose` / `viseme_A` `viseme_I` `viseme_U` `viseme_E` `viseme_O` / `mouthSmile`(+ Jaw ボーン)に加えて、片側の笑顔・への字・口角を引く・すぼめ・口の横ずらし・唇の片側・顎の前後左右・頬のふくらみ・舌の 20 個の細かいキー(合計 28 個)。**開口は長方形でなく楕円形**で、口を開くと上唇もわずかに上がる。歯・舌が皮膚を突き抜けないことをクリアランスで確認。
4. **動作確認** — 手を開く→握る→開く / 指を1本ずつ(左右)/ 人差し指・ピース / 口の 閉→開→閉 / あ→い→う→え→お / 笑顔→通常 を 24 fps・1,074 フレームのアニメにし、さらに**細かい表情の確認区間**と、**日本語の発話(こんにちは、オリバーです。よろしくね。)+呼吸・体重移動・うなずき・お辞儀・手のジェスチャーの区間**を付けた。指は人差し指から小指へ、付け根から指先へ時間差で曲がり、補間は Bezier で加速・減速する。実際に再生・レンダリングして MP4 にした。
5. **書き出しと再読込検証** — .blend / FBX / GLB を書き出し、FBX と GLB は**空のシーンに再読込して**ボーン・ウェイト・シェイプキー・テクスチャ・アニメが残っていること、指・口が実際にメッシュを変形させることを数値で確認した。

## 検証サマリ(書き出した FBX / GLB を空シーンに再読込して計測)

| モデル | ボーン数 | 指の頂点グループ | ウェイト付き頂点 | 右手を握った時の指頂点の平均移動量 (FBX / GLB) | 同・袖/上腕の最大移動量 (FBX / GLB) | `jawOpen` 最大変位 |
|---|---|---|---|---|---|---|
""" + "\n".join(vsum) + f"""

詳細(キーごとの変位、テクスチャ、口腔クリアランス等)は各モデルの README。再生ベースの検証(再読込後にアニメを再生して 左右10本の指と顎が実際に動くか): 各モデルの README「アニメの再生検証」。

## Turbo / Cowboy について(作り直し版)

* ユーザーが作り直した `Turbo.fbx` / `Cowboy.fbx`(https://gofile.io/d/tVUQudhH)を使った。ファイルに付いていた Meshy の自動リグ(24 ボーン、指・顎なし)とそのアニメは使わず、メッシュだけを取り出して下記のリグを作り直した。UV の継ぎ目で分かれていた頂点は溶接して一枚の面にしている。
* 以前の版で行っていた**顔の補正(参考写真に合わせた顔の修正・サングラスの作り直し)は、作り直し版では行っていない**(顔・髪・服・サングラス・帽子は元データのまま)。以前の版の補正画像・参考写真・補正ツールはリポジトリから削除した。
* 元データのテクスチャには**サングラスの色と肌の色が混ざっている部分がある**。依頼により**修正していない**(元データのまま)。
* 元データに roughness / metallic のマップは無いので、材質は roughness 0.6 / metallic 0 の固定値(ベースカラー+ノーマルのみ)。

## できていないこと・制約(正直な報告)

* **Turbo / Cowboy / Gray の指は付け根側 約20% が水かき状につながったまま**(元メッシュで癒着していたため、全長を切り離すと指の根元に穴が開く)。個別に曲げると付け根が引き伸ばされ、ピースサインでも2本が大きく離れない。切り口の面は単色の肌色で、指を1本だけ曲げると平らな「ひれ」状に見えることがある(特に Cowboy)。Alone は指が独立しており、この制約は小さい。
* 口腔は様式化(単色の口内壁、簡易な歯・舌、舌ボーンなし)。母音の形(あいうえお)は近似。`viseme_U`/`viseme_O` の口の幅変化に合わせて歯・舌を横に縮めているが、実際の発話の全口形を再現するものではない。Alone は唇のしわ沿いに小さな暗い点状のテクスチャ乱れが残る。Gray は口腔の下壁の頂点 3 つが外皮まで 1.06 mm(ほぼ接触)。
* 服・髪・帽子・フリンジは肌と同じ自動スキニングで、物理シミュレーションはない。腕を大きく動かすと線形ブレンドスキンの限界(袖口のつぶれ等)が出る。
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

{big_files}

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
| 検証 | `oliver_rig/verify_export.py`, `verify_anim.py`, `test_poses.py`, `test_body.py`, `debug_stuck.py` |
| 動画 | `render_videos.sh`, `oliver_rig/render_video.py`, `encode_video.sh` |
| README 生成 | `make_readmes.py` |

元データの md5: Alone `1a358a11…` / Gray `0066f040…`(FBX)、作り直し版 Turbo.fbx `7c02511b…` / Cowboy.fbx `0e3d7b1a…`。
"""
open(os.path.join(root, "README.md"), "w").write(top)
print("wrote", os.path.join(root, "README.md"))
