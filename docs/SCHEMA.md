# Database Schema — Discovery (Phase 0)

_Generated 2026-10-28T10:34:06. Read-only introspection; no data was modified._

**Tables found:** 11


## `olist.customers`  —  99,441 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| customer_id | CHAR(32) | N | dimension | 99441 distinct |
| customer_unique_id | CHAR(32) | N | dimension | 96096 distinct |
| zip_code_prefix | CHAR(5) | N | dimension | 14994 distinct |
| city | VARCHAR(64) | N | dimension | 4119 distinct |
| state | CHAR(2) | N | dimension | 27 distinct: AC, AL, AM, AP, BA, CE, DF, ES, GO, MA, MG, MS |

### Indexes

- `customers_unique_id_idx`: customer_unique_id
- `customers_zip_idx`: zip_code_prefix

### Sample rows

| customer_id | customer_unique_id | zip_code_prefix | city | state |
|---|---|---|---|---|
| 00012a2ce6f8dcda20d059ce98491703 | 248ffe10d632bebe4f7267f1f44844c9 | 06273 | osasco | SP |
| 000161a058600d5901f007fab4c27140 | b0015e09bb4b6e47c52844fab5fb6638 | 35550 | itapecerica | MG |
| 0001fd6190edaaf884bcaf3d49edf079 | 94b11d37cd61cb2994a194d11f89682b | 29830 | nova venecia | ES |
| 0002414f95344307404f0ace7a26f1d5 | 4893ad4ea28b2c5b3ddf4e82e79db9e6 | 39664 | mendonca | MG |
| 000379cdec625522490c315e70c7a9fb | 0b83f73b19c2019e182fd552c048a22c | 04841 | sao paulo | SP |

## `olist.geolocation_points`  —  720,496 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| point_id | INTEGER | N | dimension |  |
| zip_code_prefix | CHAR(5) | N | dimension | 19015 distinct |
| latitude | DECIMAL | N | measure |  |
| longitude | DECIMAL | N | measure |  |
| city | VARCHAR(64) | N | dimension | 5966 distinct |
| state | CHAR(2) | N | dimension | 27 distinct: AC, AL, AM, AP, BA, CE, DF, ES, GO, MA, MG, MS |
| in_brazil | BOOLEAN | N | dimension | 2 distinct: False, True |

### Indexes

- `geo_points_zip_idx`: zip_code_prefix

### Sample rows

| point_id | zip_code_prefix | latitude | longitude | city | state | in_brazil |
|---|---|---|---|---|---|---|
| 1 | 01001 | -23.551426655288804 | -46.63407394670785 | sao paulo | SP | True |
| 2 | 01001 | -23.551336655288804 | -46.63402699777831 | sao paulo | SP | True |
| 3 | 01001 | -23.55064182209015 | -46.634409790322515 | sao paulo | SP | True |
| 4 | 01001 | -23.550497706907514 | -46.63433817805407 | sao paulo | SP | True |
| 5 | 01001 | -23.550263371631395 | -46.63419639384839 | sao paulo | SP | True |

## `olist.geolocations`  —  19,177 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| zip_code_prefix | CHAR(5) | N | dimension | 19177 distinct |
| latitude | DECIMAL(9, 6) | Y | measure |  |
| longitude | DECIMAL(9, 6) | Y | measure |  |
| city | VARCHAR(64) | N | dimension | 5815 distinct |
| state | CHAR(2) | N | dimension | 27 distinct: AC, AL, AM, AP, BA, CE, DF, ES, GO, MA, MG, MS |
| point_count | INTEGER | N | measure |  |

### Sample rows

| zip_code_prefix | latitude | longitude | city | state | point_count |
|---|---|---|---|---|---|
| 01001 | -23.550107 | -46.634027 | sao paulo | SP | 10 |
| 01002 | -23.548228 | -46.635247 | sao paulo | SP | 6 |
| 01003 | -23.548976 | -46.635318 | sao paulo | SP | 10 |
| 01004 | -23.549550 | -46.634771 | sao paulo | SP | 14 |
| 01005 | -23.549690 | -46.636532 | sao paulo | SP | 11 |

## `olist.order_items`  —  112,650 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| order_id | CHAR(32) | N | dimension | 98666 distinct |
| order_item_id | INTEGER | N | dimension |  |
| product_id | CHAR(32) | N | dimension | 32951 distinct |
| seller_id | CHAR(32) | N | dimension | 3095 distinct |
| shipping_limit_at | TIMESTAMP | N | dimension | range: 2016-09-19 00:15:34 → 2020-04-09 22:35:08 |
| price | DECIMAL(10, 2) | N | measure |  |
| freight_value | DECIMAL(10, 2) | N | measure |  |

### Indexes

- `order_items_product_idx`: product_id
- `order_items_seller_idx`: seller_id

### Sample rows

| order_id | order_item_id | product_id | seller_id | shipping_limit_at | price | freight_value |
|---|---|---|---|---|---|---|
| 00010242fe8c5a6d1ba2dd792cb16214 | 1 | 4244733e06e7ecb4970a6e2683c13e61 | 48436dade18ac8b2bce089ec2a041202 | 2017-09-19 09:45:35 | 58.90 | 13.29 |
| 00018f77f2f0320c557190d7a144bdd3 | 1 | e5f2d52b802189ee658865ca93d83a8f | dd7ddc04e1b6c2c614352b383efe2d36 | 2017-05-03 11:05:13 | 239.90 | 19.93 |
| 000229ec398224ef6ca0657da4fc703e | 1 | c777355d18b72b67abbeef9df44fd0fd | 5b51032eddd242adc84c38acab88f23d | 2018-01-18 14:48:30 | 199.00 | 17.87 |
| 00024acbcdf0a6daa1e931b038114c75 | 1 | 7634da152a4610f1595efa32f14722fc | 9d7a1d34a5052409006425275ba1c2b4 | 2018-08-15 10:10:18 | 12.99 | 12.79 |
| 00042b26cf59d7ce69dfabb4e55b4fd9 | 1 | ac6c3623068f30de03045865e4e10089 | df560393f3a51e74553ab94004ba5c87 | 2017-02-13 13:57:51 | 199.90 | 18.14 |

## `olist.order_payments`  —  103,886 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| order_id | CHAR(32) | N | dimension | 99440 distinct |
| payment_sequential | INTEGER | N | dimension |  |
| payment_type | VARCHAR(16) | N | dimension | 5 distinct: boleto, credit_card, debit_card, not_defined, voucher |
| installments | INTEGER | N | measure |  |
| payment_value | DECIMAL(10, 2) | N | measure |  |

### Sample rows

| order_id | payment_sequential | payment_type | installments | payment_value |
|---|---|---|---|---|
| 00010242fe8c5a6d1ba2dd792cb16214 | 1 | credit_card | 2 | 72.19 |
| 00018f77f2f0320c557190d7a144bdd3 | 1 | credit_card | 3 | 259.83 |
| 000229ec398224ef6ca0657da4fc703e | 1 | credit_card | 5 | 216.87 |
| 00024acbcdf0a6daa1e931b038114c75 | 1 | credit_card | 2 | 25.78 |
| 00042b26cf59d7ce69dfabb4e55b4fd9 | 1 | credit_card | 3 | 218.04 |

## `olist.order_reviews`  —  99,224 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| order_id | CHAR(32) | N | dimension | 98673 distinct |
| review_id | CHAR(32) | N | dimension | 98410 distinct |

### Indexes

- `order_reviews_review_idx`: review_id

### Sample rows

| order_id | review_id |
|---|---|
| 00010242fe8c5a6d1ba2dd792cb16214 | 97ca439bc427b48bc1cd7177abe71365 |
| 00018f77f2f0320c557190d7a144bdd3 | 7b07bacd811c4117b742569b04ce3580 |
| 000229ec398224ef6ca0657da4fc703e | 0c5b33dea94867d1ac402749e5438e8b |
| 00024acbcdf0a6daa1e931b038114c75 | f4028d019cb58564807486a6aaf33817 |
| 00042b26cf59d7ce69dfabb4e55b4fd9 | 940144190dcba6351888cafa43f3a3a5 |

## `olist.orders`  —  99,441 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| order_id | CHAR(32) | N | dimension | 99441 distinct |
| customer_id | CHAR(32) | N | dimension | 99441 distinct |
| order_status | VARCHAR(16) | N | dimension | 8 distinct: approved, canceled, created, delivered, invoiced, processing, shipped, unavailable |
| purchased_at | TIMESTAMP | N | dimension | range: 2016-09-04 21:15:19 → 2018-10-17 17:30:18 |
| approved_at | TIMESTAMP | Y | dimension | range: 2016-09-15 12:16:38 → 2018-09-03 17:40:06 |
| delivered_carrier_at | TIMESTAMP | Y | dimension | range: 2016-10-08 10:34:01 → 2018-09-11 19:48:28 |
| delivered_customer_at | TIMESTAMP | Y | dimension | range: 2016-10-11 13:46:32 → 2018-10-17 13:22:46 |
| estimated_delivery_date | DATE | N | dimension | range: 2016-09-30 → 2018-11-12 |

### Indexes

- `orders_customer_id_key` (unique): customer_id
- `orders_purchased_at_idx`: purchased_at
- `orders_status_idx`: order_status

### Sample rows

| order_id | customer_id | order_status | purchased_at | approved_at | delivered_carrier_at | delivered_customer_at | estimated_delivery_date |
|---|---|---|---|---|---|---|---|
| 00010242fe8c5a6d1ba2dd792cb16214 | 3ce436f183e68e07877b285a838db11a | delivered | 2017-09-13 08:59:02 | 2017-09-13 09:45:35 | 2017-09-19 18:34:16 | 2017-09-20 23:43:48 | 2017-09-29 |
| 00018f77f2f0320c557190d7a144bdd3 | f6dd3ec061db4e3987629fe6b26e5cce | delivered | 2017-04-26 10:53:06 | 2017-04-26 11:05:13 | 2017-05-04 14:35:00 | 2017-05-12 16:04:24 | 2017-05-15 |
| 000229ec398224ef6ca0657da4fc703e | 6489ae5e4333f3693df5ad4372dab6d3 | delivered | 2018-01-14 14:33:31 | 2018-01-14 14:48:30 | 2018-01-16 12:36:48 | 2018-01-22 13:19:16 | 2018-02-05 |
| 00024acbcdf0a6daa1e931b038114c75 | d4eb9395c8c0431ee92fce09860c5a06 | delivered | 2018-08-08 10:00:35 | 2018-08-08 10:10:18 | 2018-08-10 13:28:00 | 2018-08-14 13:32:39 | 2018-08-20 |
| 00042b26cf59d7ce69dfabb4e55b4fd9 | 58dbd0b2d70206bf40e62cd34e84d795 | delivered | 2017-02-04 13:57:51 | 2017-02-04 14:10:13 | 2017-02-16 09:46:09 | 2017-03-01 16:42:31 | 2017-03-17 |

## `olist.product_categories`  —  73 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| category_id | INTEGER | N | dimension |  |
| category_name_pt | VARCHAR(64) | N | dimension | 73 distinct |
| category_name_en | VARCHAR(64) | N | dimension | 73 distinct |

### Indexes

- `product_categories_category_name_pt_key` (unique): category_name_pt

### Sample rows

| category_id | category_name_pt | category_name_en |
|---|---|---|
| 1 | agro_industria_e_comercio | agro_industry_and_commerce |
| 2 | alimentos | food |
| 3 | alimentos_bebidas | food_drink |
| 4 | artes | art |
| 5 | artes_e_artesanato | arts_and_craftmanship |

## `olist.products`  —  32,951 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| product_id | CHAR(32) | N | dimension | 32951 distinct |
| category_id | INTEGER | Y | dimension |  |
| name_length | INTEGER | Y | measure |  |
| description_length | INTEGER | Y | measure |  |
| photos_qty | INTEGER | Y | measure |  |
| weight_g | INTEGER | Y | measure |  |
| length_cm | INTEGER | Y | measure |  |
| height_cm | INTEGER | Y | measure |  |
| width_cm | INTEGER | Y | measure |  |

### Indexes

- `products_category_idx`: category_id

### Sample rows

| product_id | category_id | name_length | description_length | photos_qty | weight_g | length_cm | height_cm | width_cm |
|---|---|---|---|---|---|---|---|---|
| 00066f42aeeb9f3007548bb9d3f33c38 | 63 | 53 | 596 | 6 | 300 | 20 | 16 | 16 |
| 00088930e925c41fd95ebfe695fd2655 | 9 | 56 | 752 | 4 | 1225 | 55 | 10 | 26 |
| 0009406fd7479715e4bef61dd91f2462 | 14 | 50 | 266 | 2 | 300 | 45 | 15 | 35 |
| 000b8f95fcb9e0096488278317764d19 | 73 | 25 | 364 | 3 | 550 | 19 | 24 | 12 |
| 000d9be29b5207b54e86aa1b1ac54872 | 67 | 48 | 613 | 4 | 250 | 22 | 11 | 15 |

## `olist.reviews`  —  98,410 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| review_id | CHAR(32) | N | dimension | 98410 distinct |
| score | INTEGER | N | measure |  |
| comment_title | VARCHAR | Y | dimension | 4178 distinct |
| comment_message | VARCHAR | Y | dimension | 35616 distinct |
| created_date | DATE | N | dimension | range: 2016-10-02 → 2018-08-31 |
| answered_at | TIMESTAMP | N | dimension | range: 2016-10-07 18:32:28 → 2018-10-29 12:27:35 |

### Sample rows

| review_id | score | comment_title | comment_message | created_date | answered_at |
|---|---|---|---|---|---|
| 0001239bc1de2e33cb583967c2ca4c67 | 5 | NULL | NULL | 2018-03-20 | 2018-03-20 18:36:04 |
| 0001cc6860aeaf5b9017fe4131a52e62 | 5 | NULL | NULL | 2018-06-22 | 2018-06-26 13:51:29 |
| 00020c7512a52e92212f12d3e37513c0 | 5 | Entrega rápida! | A entrega foi super rápida e o pendente é lindo! Igual a ... | 2018-04-25 | 2018-04-26 14:55:36 |
| 00032b0141443497c898b3093690af51 | 5 | NULL | NULL | 2017-05-30 | 2017-06-01 23:28:55 |
| 00034d88989f9a4c393bdcaec301537f | 5 | NULL | NULL | 2017-08-12 | 2017-08-13 19:56:53 |

## `olist.sellers`  —  3,095 rows

### Columns

| column | type | null | role | notes |
|---|---|---|---|---|
| seller_id | CHAR(32) | N | dimension | 3095 distinct |
| zip_code_prefix | CHAR(5) | N | dimension | 2246 distinct |
| city | VARCHAR(64) | N | dimension | 583 distinct |
| state | CHAR(2) | N | dimension | 23 distinct: AC, AM, BA, CE, DF, ES, GO, MA, MG, MS, MT, PA |

### Indexes

- `sellers_zip_idx`: zip_code_prefix

### Sample rows

| seller_id | zip_code_prefix | city | state |
|---|---|---|---|
| 0015a82c2db000af6aaaf3ae2ecb0532 | 09080 | santo andre | SP |
| 001cca7ae9ae17fb1caed9dfb1094831 | 29156 | cariacica | ES |
| 001e6ad469a905060d959994f1b41e4f | 24754 | sao goncalo | RJ |
| 002100f778ceb8431b7a1020ff7ab48f | 14405 | franca | SP |
| 003554e2dce176b5555353e4f3555ac8 | 74565 | goiania | GO |

## Dimensions vs. measures (heuristic)

- **olist.customers** — measures: —; dimensions: customer_id, customer_unique_id, zip_code_prefix, city, state
- **olist.geolocation_points** — measures: latitude, longitude; dimensions: point_id, zip_code_prefix, city, state, in_brazil
- **olist.geolocations** — measures: latitude, longitude, point_count; dimensions: zip_code_prefix, city, state
- **olist.order_items** — measures: price, freight_value; dimensions: order_id, order_item_id, product_id, seller_id, shipping_limit_at
- **olist.order_payments** — measures: installments, payment_value; dimensions: order_id, payment_sequential, payment_type
- **olist.order_reviews** — measures: —; dimensions: order_id, review_id
- **olist.orders** — measures: —; dimensions: order_id, customer_id, order_status, purchased_at, approved_at, delivered_carrier_at, delivered_customer_at, estimated_delivery_date
- **olist.product_categories** — measures: —; dimensions: category_id, category_name_pt, category_name_en
- **olist.products** — measures: name_length, description_length, photos_qty, weight_g, length_cm, height_cm, width_cm; dimensions: product_id, category_id
- **olist.reviews** — measures: score; dimensions: review_id, comment_title, comment_message, created_date, answered_at
- **olist.sellers** — measures: —; dimensions: seller_id, zip_code_prefix, city, state
