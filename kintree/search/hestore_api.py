import base64
import collections
import hashlib
import hmac
import os
import urllib.parse
import urllib.request
import json

# from ..common.tools import download
from ..config import config_interface, settings

def get_default_search_keys():
    return [
        'Symbol',
        'Description',
        '',  # Revision
        'Category',
        'SKU',
        '',
        'OriginalSymbol',
        'ProductInformationPage',
        'Datasheet',
        'Photo',
    ]
def check_environment() -> bool:
    HESTORE_API_TOKEN = os.environ.get('HESTORE_API_TOKEN', None)
    HESTORE_API_SECRET = os.environ.get('HESTORE_API_SECRET', None)

    if not HESTORE_API_TOKEN or not HESTORE_API_SECRET:
        return False

    return True


def setup_environment(force=False) -> bool:
    if not check_environment() or force:
        hestore_api_settings = config_interface.load_file(settings.CONFIG_HESTORE_API)
        os.environ['HESTORE_API_TOKEN'] = hestore_api_settings.get('HESTORE_API_TOKEN', None)
        os.environ['HESTORE_API_SECRET'] = hestore_api_settings.get('HESTORE_API_SECRET', None)

    return check_environment()


def hestore_api_request(endpoint, hestore_api_settings, params, api_host='https://api.hestore.hu/api/rest', format='json', **kwargs):
    HESTORE_API_TOKEN = hestore_api_settings.get('HESTORE_API_TOKEN', None)
    HESTORE_API_SECRET = hestore_api_settings.get('HESTORE_API_SECRET', None)

    if not HESTORE_API_TOKEN and not HESTORE_API_SECRET:
        HESTORE_API_TOKEN = os.environ.get('HESTORE_API_TOKEN', None)
        HESTORE_API_SECRET = os.environ.get('HESTORE_API_SECRET', None)
    if not HESTORE_API_TOKEN and not HESTORE_API_SECRET:
        from ..common.tools import cprint
        cprint('[INFO]\tWarning: Value not found for HESTORE_API_TOKEN and/or HESTORE_API_SECRET', silent=False)
        return None
    params = collections.OrderedDict(sorted(params.items()))
    params['token'] = HESTORE_API_TOKEN

    url = api_host + endpoint + '.' + format
    encoded_params = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    signature_base = 'POST' + '&' + urllib.parse.quote(url, '') + '&' + urllib.parse.quote(encoded_params, '')
    hmac_value = hmac.new(
        HESTORE_API_SECRET.encode(),
        signature_base.encode(),
        hashlib.sha1
    ).digest()
    api_signature = base64.encodebytes(hmac_value).rstrip()
    params['signature'] = api_signature

    data = urllib.parse.urlencode(params).encode()
    return urllib.request.Request(url, data, method='POST')


def hestore_api_query(request: urllib.request.Request) -> dict:
    response = None
    try:
        data = urllib.request.urlopen(request).read().decode('utf8')
    except urllib.error.HTTPError:
        data = None
    if data:
        response = json.loads(data)
    return response


def fetch_part_info(part_number: str) -> dict:
    def search_product(response, key, id):
        found = False
        index = 0
        for product in response['data']:
            if product[key] == id:
                found = True
                break
            index = index + 1
        return found, index

    hestore_api_settings = config_interface.load_file(settings.CONFIG_HESTORE_API)
    params = {'query': part_number}

    response = hestore_api_query(hestore_api_request('/prod/search', hestore_api_settings, params))

    if response is None or response['status'] != 'OK':
        return {}

    found, index = search_product(response, 'name', part_number)

    if not found:
        return {}

    part_info = {}
    sku_full = response['data'][index]['sku']
    part_info['SKU'] = sku_full
    part_info['OriginalSymbol'] = part_number
    sku = response['data'][index]['sku'].replace('.', '')
    part_info['Symbol'] = response['data'][index]['name']
    part_info['Description'] = response['data'][index]['description']
    part_info['ProductInformationPage'] = "https://www.hestore.hu/prod_" + sku + ".html"

    # query the prices
    params = {'skus[0]': sku}
    response = hestore_api_query(hestore_api_request('/prod/pricestock', hestore_api_settings, params))
    # check if accidentally no data returned
    if response is None or response['status'] != 'OK':
        return part_info

    found, index = search_product(response, 'sku', sku_full)

    if not found:
        part_info['currency'] = 'HUF'
        return part_info

    part_info['pricing'] = {}

    for qty in response['data'][index]['prices']:
        part_info['pricing'][qty] = response['data'][index]['prices'][qty]

    part_info['currency'] = response['data'][index]['currency']

    # Query the files associated to the product
    '''params = {'skus[0]': [sku]}
    response = hestore_api_query(hestore_api_request('/prod/doc', hestore_api_settings, params))
    # check if accidentally no products returned
    if response is None or response['status'] != 'OK':
        return part_info

    found, index = search_product(response, 'sku', sku_full)

    if not found:
        return part_info

    for doc in response['data'][index]['Files']['DocumentList']:
        part_info['Datasheet'] = 'http:' + doc['DocumentUrl']'''
    return part_info


def test_api(check_content=False) -> bool:
    ''' Test method for API '''
    setup_environment()

    test_success = True
    expected = {
        'Description': "Di\u00f3da, kapcsol\u00f3, 75V, 150mA, egyetlen di\u00f3da, SMD, Tokoz\u00e1s: 0603",
        'Symbol': 'CL05C330JB5NNNC',
        'ProductInformationPage': 'https://www.hestore.hu/prod_10032777.html',
        'Datasheet': 'http://www.hestore.eu/Document/7da762c1dbaf553c64ad9c40d3603826/mlcc_samsung.pdf',
        'Photo': '\/\/www.hestore.hu\/images\/comp\/normal\/NDE0OC0wNjAzNjAz.jpg',
    }

    test_part = fetch_part_info('1N4148-0603')

    # Check for response
    if not test_part:
        test_success = False

    if not check_content:
        return test_success

    # Check content of response
    if test_success:
        for key, value in expected.items():
            if test_part[key] != value:
                print(f'{test_part[key]} != {value}')
                test_success = False
                break

    return test_success
