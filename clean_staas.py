import re, html, requests
r = requests.get('https://www.eugenewei.com/blog/2019/2/19/status-as-a-service', timeout=30)
t = r.text
t = re.sub(r'<script[^>]*>.*?</script>', '', t, flags=re.DOTALL)
t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL)
t = re.sub(r'<[^>]+>', '', t)
t = html.unescape(t)
t = re.sub(r'\n{3,}', '\n\n', t)
t = t.strip()
open(r'C:/Users/dkitc/Downloads/DDL_Ingest/EugeneWei_StaaS_clean.txt','w',encoding='utf-8').write(t)
print('Done:', len(t))
print(t[:500])
