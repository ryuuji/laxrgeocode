# シンプルな形状の判定用領域を作る
# - 海岸線や離島などはひとつの領域（凸包）にまとめる
# - 判定用領域は市町村の領域を含んでいるが300mm程度バッファをとった上で、ポリゴンの単純化をすることでデータ量を圧縮する
# - この処理により境界領域の300m程度は、両方の市町村を候補に挙げる
# - 小さい飛地などは両方の市町村を候補に挙げる
# - 政令指定都市の区は市町村に集約する

import click
import orjson
from shapely.geometry import shape, mapping, MultiPoint, MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

# 政令指定都市の区を市の代表コードに集約するためのテーブル
REDUCE_MAPPING = {
    "01101": "01100",
    "01102": "01100",
    "01103": "01100",
    "01104": "01100",
    "01105": "01100",
    "01106": "01100",
    "01107": "01100",
    "01108": "01100",
    "01109": "01100",
    "01110": "01100",
    "04101": "04100",
    "04102": "04100",
    "04103": "04100",
    "04104": "04100",
    "04105": "04100",
    "11101": "11100",
    "11102": "11100",
    "11103": "11100",
    "11104": "11100",
    "11105": "11100",
    "11106": "11100",
    "11107": "11100",
    "11108": "11100",
    "11109": "11100",
    "11110": "11100",
    "12101": "12100",
    "12102": "12100",
    "12103": "12100",
    "12104": "12100",
    "12105": "12100",
    "12106": "12100",
    "14101": "14100",
    "14102": "14100",
    "14103": "14100",
    "14104": "14100",
    "14105": "14100",
    "14106": "14100",
    "14107": "14100",
    "14108": "14100",
    "14109": "14100",
    "14110": "14100",
    "14111": "14100",
    "14112": "14100",
    "14113": "14100",
    "14114": "14100",
    "14115": "14100",
    "14116": "14100",
    "14117": "14100",
    "14118": "14100",
    "14131": "14130",
    "14132": "14130",
    "14133": "14130",
    "14134": "14130",
    "14135": "14130",
    "14136": "14130",
    "14137": "14130",
    "14151": "14150",
    "14152": "14150",
    "14153": "14150",
    "15101": "15100",
    "15102": "15100",
    "15103": "15100",
    "15104": "15100",
    "15105": "15100",
    "15106": "15100",
    "15107": "15100",
    "15108": "15100",
    "22101": "22100",
    "22102": "22100",
    "22103": "22100",
    "22131": "22130",
    "22132": "22130",
    "22133": "22130",
    "22134": "22130",
    "22135": "22130",
    "22136": "22130",
    "22137": "22130",
    "23101": "23100",
    "23102": "23100",
    "23103": "23100",
    "23104": "23100",
    "23105": "23100",
    "23106": "23100",
    "23107": "23100",
    "23108": "23100",
    "23109": "23100",
    "23110": "23100",
    "23111": "23100",
    "23112": "23100",
    "23113": "23100",
    "23114": "23100",
    "23115": "23100",
    "23116": "23100",
    "26101": "26100",
    "26102": "26100",
    "26103": "26100",
    "26104": "26100",
    "26105": "26100",
    "26106": "26100",
    "26107": "26100",
    "26108": "26100",
    "26109": "26100",
    "26110": "26100",
    "26111": "26100",
    "27101": "27100",
    "27102": "27100",
    "27103": "27100",
    "27104": "27100",
    "27105": "27100",
    "27106": "27100",
    "27107": "27100",
    "27108": "27100",
    "27109": "27100",
    "27110": "27100",
    "27111": "27100",
    "27112": "27100",
    "27113": "27100",
    "27114": "27100",
    "27115": "27100",
    "27116": "27100",
    "27117": "27100",
    "27118": "27100",
    "27119": "27100",
    "27120": "27100",
    "27121": "27100",
    "27122": "27100",
    "27123": "27100",
    "27124": "27100",
    "27125": "27100",
    "27126": "27100",
    "27127": "27100",
    "27128": "27100",
    "27141": "27140",
    "27142": "27140",
    "27143": "27140",
    "27144": "27140",
    "27145": "27140",
    "27146": "27140",
    "27147": "27140",
    "28101": "28100",
    "28102": "28100",
    "28103": "28100",
    "28104": "28100",
    "28105": "28100",
    "28106": "28100",
    "28107": "28100",
    "28108": "28100",
    "28109": "28100",
    "28110": "28100",
    "28111": "28100",
    "33101": "33100",
    "33102": "33100",
    "33103": "33100",
    "33104": "33100",
    "34101": "34100",
    "34102": "34100",
    "34103": "34100",
    "34104": "34100",
    "34105": "34100",
    "34106": "34100",
    "34107": "34100",
    "34108": "34100",
    "40101": "40100",
    "40102": "40100",
    "40103": "40100",
    "40104": "40100",
    "40105": "40100",
    "40106": "40100",
    "40107": "40100",
    "40108": "40100",
    "40109": "40100",
    "40131": "40130",
    "40132": "40130",
    "40133": "40130",
    "40134": "40130",
    "40135": "40130",
    "40136": "40130",
    "40137": "40130",
    "43101": "43100",
    "43102": "43100",
    "43103": "43100",
    "43104": "43100",
    "43105": "43100",
}


def load_n03(filename: str) -> dict:
    click.secho(f"国土数値情報行政区域データを読み込んでいます...")
    with open(filename, 'rb') as f:
        geojson = orjson.loads(f.read())
    click.secho(f"識別子:{geojson['name']}", fg='green')
    if not geojson['name'].startswith('N03-'):
        raise ValueError()
    click.secho(f"データ件数:{len(geojson['features'])}", fg='green')
    return geojson


def rewrite_geojson(geojson: dict):
    click.secho(f"政令指定都市の区を市に集約しています...")
    for item in geojson['features']:
        if item['properties'].get('N03_004').endswith('区') and item['properties'].get('N03_003') is not None:
            if item['properties']['N03_007'] in REDUCE_MAPPING:
                item['properties']['N03_007'] = REDUCE_MAPPING[item['properties']['N03_007']]
                item['properties']['N03_004'] = item['properties']['N03_003']
                item['properties']['N03_003'] = None
            else:
                raise ValueError()


def aggregate_by_city(geojson: dict) -> dict[str, list[dict]]:
    click.secho(f"ポリゴンを行政単位に集約しています...")
    city_index = {}
    for item in geojson['features']:
        if item['properties']['N03_004'] == '所属未定地':
            continue
        city_id = item['properties']['N03_007']
        if city_id not in city_index:
            city_index[city_id] = []
        city_index[city_id].append(item)
    click.secho(f"データ件数:{len(city_index)}", fg='green')
    return city_index


def build_r_index(geojson) -> (STRtree, dict[int, str]):
    click.secho(f"データ処理用の空間インデックスをビルドしています...")
    filtered = []
    tree_to_city = {}
    for item in geojson['features']:
        if item['properties']['N03_004'] == '所属未定地':
            continue
        p = shape(item['geometry'])
        filtered.append(p)
        tree_to_city[id(p)] = item['properties']['N03_007']
    return (STRtree(
        filtered
    ), tree_to_city)


def validate_aggregated(aggregated: dict[str, list[dict]]):
    with open('20190501.json', 'rb') as f:
        citydata = orjson.loads(f.read())
    validate = set()
    for x in citydata['table']:
        if x['city'] != '':
            validate.add(x['code'][0:5])
    click.secho(f"市町村コードの網羅率を検証しています...{len(aggregated)}/{len(validate)}")

    # 北方領土を除く地域のコードが揃っていることを確認
    diff_set = validate.symmetric_difference(set(aggregated.keys())) - {'01697', '01696', '01699', '01700', '01698',
                                                                        '01695'}

    if len(diff_set) != 0:
        raise ValueError()


@click.command()
@click.option('--input_geojson', type=click.Path(exists=True), default='N03-21_210101.geojson',
              help='国土数値情報行政区域データのGEOJSONファイル')
@click.option('--output', type=click.Path(), default='laxrgeocode.json', help='出力ファイル名')
def convert(input_geojson, output):
    # 処理データ : N03-20210101_GML
    # https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-v3_0.html
    # データ仕様書 : https://nlftp.mlit.go.jp/ksj/gml/product_spec/KS-PS-N03-v3_0.pdf

    geojson = load_n03(input_geojson)
    rewrite_geojson(geojson)
    aggregated = aggregate_by_city(geojson)
    validate_aggregated(aggregated)
    r_index, tree_to_city = build_r_index(geojson)

    polygons_export = []
    with click.progressbar(list(aggregated.keys()), label='各領域を計算しています...', ) as bar:
        for city_id in bar:

            # 凸包を計算する
            pp = []
            pa = []
            for item in aggregated[city_id]:
                p = shape(item['geometry'])
                pp += list(p.exterior.coords)
                pa.append(p)
            convex_hull = MultiPoint(pp).convex_hull
            true_union = unary_union(pa)

            # バッファをとる
            convex_hull_with_buffer = convex_hull.buffer(0.01).simplify(0.01)

            # 近くの他市町村領域を除外する
            convex_hull_cleared = convex_hull_with_buffer
            for area in r_index.query(convex_hull_with_buffer):
                if tree_to_city[id(area)] != city_id:
                    if area.area < 0.0005:
                        continue
                    convex_hull_cleared = convex_hull_cleared - area.buffer(0.001)

            # 分断されたゴミ領域を取り除く
            if isinstance(convex_hull_cleared, MultiPolygon):
                _tmp = []
                for xx in list(convex_hull_cleared.geoms):
                    if true_union.intersects(xx):
                        _tmp.append(xx)
                convex_hull_cleared = MultiPolygon(_tmp) if len(_tmp) > 1 else _tmp[0]

            # 境界線を単純化する
            convex_hull_cleared = convex_hull_cleared.buffer(0.0028).simplify(0.002)

            # 内部に存在するゴミ領域を除外する
            if isinstance(convex_hull_cleared, MultiPolygon):
                _tmp = []
                for xx in list(convex_hull_cleared.geoms):
                    interiors = []
                    for x in xx.interiors:
                        if x.area > 0.005:
                            interiors.append(x)
                    _tmp.append(Polygon(xx.exterior, interiors))
                convex_hull_cleared = MultiPolygon(_tmp)

            if isinstance(convex_hull_cleared, Polygon) and len(convex_hull_cleared.interiors) > 0:
                interiors = []
                for x in convex_hull_cleared.interiors:
                    if x.area > 0.005:
                        interiors.append(x)
                convex_hull_cleared = Polygon(convex_hull_cleared.exterior, interiors)

            polygons_export.append({'type': 'Feature', 'properties': {
                'id': city_id,
                'pref': aggregated[city_id][0]['properties']['N03_001'],
                'city': aggregated[city_id][0]['properties']['N03_004']
            }, 'geometry': mapping(convex_hull_cleared)})

    geojson['features'] = polygons_export
    geojson['name'] = f"Generated from {geojson['name']}"
    with open(output, 'wb') as fw:
        fw.write(orjson.dumps(geojson))
    click.secho("書き出しが完了しました")


if __name__ == '__main__':
    convert()
