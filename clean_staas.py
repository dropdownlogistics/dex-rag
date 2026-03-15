import re

with open(r'C:\Users\dkitc\Downloads\DDL_Ingest\EugeneWei_StaaS_2019.txt', encoding='utf-8') as f:
    html = f.read()

clean = re.sub(r'<[^>]+>', '', html)
clean = re.sub(r'\n{3,}', '\n\n', clean)
clean = clean.strip()

with open(r'C:\Users\dkitc\Downloads\DDL_Ingest\EugeneWei_StaaS_clean.txt', 'w', encoding='utf-8') as f:
    f.write(clean)

print('Done:', len(clean), 'chars')