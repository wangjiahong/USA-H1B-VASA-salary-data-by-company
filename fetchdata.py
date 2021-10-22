url = "https://h1bdata.info/index.php?em=Facebook+Inc&job=Data+Scientist&city=&year=2021"

import requests

r = requests.get(url)
# print(r.text.split("tbody")[1].split("'/tbody")[0])


import pandas as pd
html_tables = pd.read_html(r.text)
df = html_tables[0]
df.T
print(df)