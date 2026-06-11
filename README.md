# gmap_list

Google Places API で「地域 + 業種」を検索し、CSV に出力するツール。

## 必要環境
- Python 3.9+
- requests
- Google Places API キー

## 使い方
1. `export GOOGLE_PLACES_API_KEY=***` を設定するか、同フォルダに `config.py` を置く。
2. `python gmap_list.py --region "東京都渋谷区" --keyword "カフェ"`

## 出力
`gmap_results_{keyword}_{region}_{YYYYMMDD}.csv`
