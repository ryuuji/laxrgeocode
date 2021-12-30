from laxrgeocode import LaxReverseGeocoder
import json

with open('laxrgeocode.json', 'rb') as f:  # 事前処理したデータを読み込む
    geojson = json.loads(f.read())
geocoder = LaxReverseGeocoder(geojson)
x = geocoder.search(35.47798, 139.71567)
print(x)
