import fitz, pathlib
doc = fitz.open(r'C:\Users\dkitc\iCloudDrive\Documents\05_DirectIngest\Leverage_Points.pdf')
text = '\n'.join(page.get_text() for page in doc)
out = pathlib.Path(r'C:\Users\dkitc\iCloudDrive\Documents\05_DirectIngest\Leverage_Points.txt')
out.write_text(text, encoding='utf-8')
print(f'Done. {len(text)} chars.')
