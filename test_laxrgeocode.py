from laxrgeocode import LaxReverseGeocoder
import json


def test_data():
    with open('laxrgeocode.json', 'rb') as f:
        geojson = json.loads(f.read())

    geocoder = LaxReverseGeocoder(geojson)
    assert geocoder
    assert geocoder.search(35.63307, 139.74229)[0]['city'] == '港区'
    x = geocoder.search(35.47798, 139.71567)
    assert len(x) == 2
