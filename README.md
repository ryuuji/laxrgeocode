# laxrgeocode
Lax "City Level" Reverse Geocoding In Japan

このリポジトリは、zennに投稿した [「Pythonによる市町村・逆ジオコーディングの実装」](https://zenn.dev/articles/cf1f8d7c57aee8) のソースコードと処理済のデータセットです。

# コマンドライン
```bash
poetry install
poetry run python build.py
poetry run python search.py
```


# コンセプト

カーリルの内部APIのリプレイスにともない、これまで外部のAPIに頼っていた逆ジオコーディングを独自で実装しました。事前調査ではgeoloniaが開発している [open-reverse-geocoder](https://github.com/geolonia/open-reverse-geocoder) がもっとも理想に近いものでしたが、今回はPythonで実装された既存のマイクロサービス内に組み込む必要があったため、独自に実装することにしました。

- **"ゆるい"判定** 
（境界領域などでは候補となる複数の市町村を返す）
- 経緯度から市町村を返すシンプルな逆ジオコーディング
- マイクロサービスに同梱しやすい軽量なデータと、高速な動作

# データの事前処理

市町村の境界線を得るためのオープンデータとして、[国土数値情報行政区域データ](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-v3_0.html) を利用できます。このデータはGeoJSON形式で680MBと巨大なファイルです。これは海岸線の形状なども含む高精度なポリゴンデータとなっているためです。データを圧縮するために**シンプルな形状の判定用領域を事前に計算**することにしました。
![高知県土佐清水市周辺](https://storage.googleapis.com/zenn-user-upload/1c6b60b1e99d-20211230.png)

1. GeoJSONを読み込む
```python
from shapely.geometry import shape, mapping, MultiPoint, MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

with open("N03-21_210101.geojson", 'rb') as f:
    geojson = orjson.loads(f.read())
```

2. ポリゴンを市町村単位に集約する。
あわせて、今後の処理で邪魔になる所属未定地を除外する。
```python
aggregated = {}
for item in geojson['features']:
　　　　if item['properties']['N03_004'] == '所属未定地':
  　　　  continue
　　　　city_id = item['properties']['N03_007']
　　　　if city_id not in city_index:
  　　　  aggregated[city_id] = []
　　　　aggregated[city_id].append(item)
```

3. 市町村ごとに海岸線や離島などはひとつの領域（凸包）にまとめます
```python
for city_id in aggregated:
    pp = []
    for item in aggregated[city_id]:
        p = shape(item['geometry'])
        pp += list(p.exterior.coords)
    convex_hull = MultiPoint(pp).convex_hull
```
この処理で以下のように、海岸線や離島などがひとつの領域に集約されて、GeoJSONのサイズは2.8MBにまで減少しました。ただし、重複領域（濃い部分）が広い範囲で発生していることがわかります。
![](https://storage.googleapis.com/zenn-user-upload/69cd726c0c18-20211230.png)

4. 海岸線向けのバッファと簡略化
逆に判定領域は海岸線のギリギリとなっており、誤差を吸収するためにもう少し広くとってもよさそうです。バッファした上でさらにデータを圧縮するため簡略化してみます。バッファを先に処理しているのは、簡略化によって位置が変動した場合でも、実際の領域を削る可能性を減らすためです。GeoJSONのサイズは800KBまで減少しました。ひとつ前のステップとの違いは以下（緑色の部分）のようになります。
```python
    convex_hull_with_buffer = convex_hull.buffer(0.01).simplify(0.01)
```
![](https://storage.googleapis.com/zenn-user-upload/320c9571565e-20211230.png)

5. 近隣市町村の領域を除外する
これまでに作成した領域は、隣接する市町村と広い領域で重複してしまっています。これを取り除くため、あらためて近隣市町村の領域を除外します。効率化のため事前に空間インデックスを構築していますが、こちらはソースコードを参照してください。
```python
    convex_hull_cleared = convex_hull_with_buffer
    for area in r_index.query(convex_hull_with_buffer):
        if tree_to_city[id(area)] != city_id:
            if area.area < 0.0005:
                continue
            convex_hull_cleared = convex_hull_cleared - area.buffer(0.001)
```
この処理により以下のように適切な領域を得ることができます。しかしGeoJSONのサイズは321MBに戻りました。これは、市町村境界が簡略化前のデータに戻ったためです。
![](https://storage.googleapis.com/zenn-user-upload/7e3d11505566-20211230.png)

6. 市町村境界線向けのバッファと簡略化
あらためて市町村境界向けのバッファと簡略化を実行します。この際のパラメータで重複領域の大きさを確定できます。少し境界線上をオーバーラップさせることで境界近くでは、両方の市町村を候補として挙げることができるようになります。
```python
    convex_hull_cleared = convex_hull_cleared.buffer(0.0028).simplify(0.002)
```
![](https://storage.googleapis.com/zenn-user-upload/66303efe8d0c-20211230.png)
実際には断片化した領域の削除を行った上で、**最終的なGeoJSONは4MB**となりました。

# 逆ジオコーディングの実装

```python:laxrgeocode.py
from shapely.geometry import shape, Point
from shapely.strtree import STRtree


class LaxReverseGeocoder:
    def __init__(self, geojson: dict):
        """
        経緯度から市町村を返す「逆ジオコーディング」の実装
        :param geojson: 空間インデックスするデータ
        """
        self.tree_to_properties = {}
        geoms = []
        for item in geojson['features']:
            p = shape(item['geometry'])
            self.tree_to_properties[id(p)] = item['properties']
            geoms.append(p)
        self.r_tree = STRtree(geoms)

    def search(self, lat: float, lon: float) -> list[dict]:
        """
        経緯度から市町村を照会する
        :param lat: 緯度
        :param lon: 経度
        :return: 市町村のリスト（GeoJSONのpropertiesのリスト）
        """
        p = Point((lon, lat))
        r = []
        for item in self.r_tree.query(p):
            if item.contains(p):
                r.append(self.tree_to_properties[id(item)].copy())
        return r
```

```python:search.py
from laxrgeocode import LaxReverseGeocoder
import json

with open('laxrgeocode.json', 'rb') as f: # 事前処理したデータを読み込む
    geojson = json.loads(f.read())
geocoder = LaxReverseGeocoder(geojson)
x = geocoder.search(35.47798, 139.71567)
print(x)
```

```json:処理結果
[{'id': '14100', 'pref': '神奈川県', 'city': '横浜市'}, {'id': '14130', 'pref': '神奈川県', 'city': '川崎市'}]
```
このコードでは、クラス作成時に空間インデックスを作成します。MacMini（M1）では、インデックス生成に80ms、逆ジオコーディングは1ms以下で実行することができました。

# 参考プロジェクト
[open-reverse-geocoder](https://github.com/geolonia/open-reverse-geocoder) 
ベクトルタイルによるクライアントサイドでの逆ジオコーディング実装

[japan-topography](https://github.com/smartnews-smri/japan-topography)
市区町村・選挙区 地形データ（簡略化・整理した国土数値情報）