# JACKET CAM（VTuberサイト）

`OT_OliverTree_jacket.blend` / `OT_montbell_jacket.blend` から作った、ブラウザだけで動くVTuber風サイトです。

- ジャケット切替：Oliver Tree（ウインドブレーカー）／mont-bell
- カメラで顔・口・目・眉・首・腕・手と指をトラッキング（MediaPipe、端末内で処理）
- blendのOTリグの式をそのまま移植：表情プリセット（ex_*）、顔コントロール（fc_*）、あご、リップシンク（あいうえお）、指（hand_L/R_*）、視線とまぶたの追従、首の補正、ジャケット肩のドレープ、ねじれ自動分散
- 髪：blendのHair（4.5万本）から間引いたストランドを描画。Hair Dynamics の設定（1100本のガイド、周波数2.6Hz、減衰0.8、最大オフセット）で揺れます
- 背景：プリセット（blendのHDRIから作った街の写真など）＋自分の写真をアップロード
- マイクで口パク、写真保存、録画

## 構成

```
index.html          画面とUI
js/main.js          シーン、UI、録画
js/rig.js           OTリグ（ドライバーとコンストレイント）の移植
js/drive.js         トラッキング結果 → リグのコントロール
js/hair.js          ストランドの髪と揺れ
js/tracking.js      カメラとMediaPipe
js/lipsync.js       マイクの母音推定
assets/             avatar.glb（両ジャケット入り）, rig.json, hair.bin
vendor/, models/    three.js r170, MediaPipe tasks-vision 0.10.35 とモデル
```

カメラは https（または localhost）でのみ動きます。非公式のファンメイドです。
