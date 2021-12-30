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
