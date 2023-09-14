from flask import Response


def add_headers(response: Response):
    # response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Allow-Private-Network', 'true')
    response.headers.add('Access-Control-Allow-Headers',
                         'Content-Type, Authorization, Depth, User-Agent, X-File-Size, X-Requested-With, If-Modified-Since, X-File-Name, Cache-Control')
    response.headers.add('Access-Control-Allow-Methods', 'GET, PUT, POST, DELETE, OPTIONS')
    response.headers['Vary'] = "Origin"
    return response