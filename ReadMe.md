# python version: 3.12.3

# db schema
table_name = products
columns = id, product_name, category, SKU, stock, price, status, created_at, updated_at

# api documentation

product(POST):
endpoint: product/
request: product_name, category, SKU, stock, price
response: success: True, message: product added successfully, data: {}

product(GET):
endpoint: product/{id}
request: id(from endpoint)
response: product_name, category, SKU, stock, price, created_at, updated_at, success: True

product(GET):
endpoint: product/
request: nothing
response: list of dict data of all products with success: True, data: {}, total, page, limit(pagination)

