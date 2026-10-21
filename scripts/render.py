"""Render app/index.html: the template with data/circuits.json inlined (works from file:// and any static host)."""
import json, os
from common import DATA, ROOT

def main():
    with open(os.path.join(DATA, 'circuits.json')) as f:
        data = f.read()
    with open(os.path.join(ROOT, 'scripts', 'template.html')) as f:
        html = f.read().replace('/*__DATA__*/null', data.replace('</', '<\\/'))
    os.makedirs(os.path.join(ROOT, 'app'), exist_ok=True)
    with open(os.path.join(ROOT, 'app', 'index.html'), 'w') as f:
        f.write(html)
    print(f'app/index.html ({len(html) // 1024} KB)')

if __name__ == '__main__':
    main()
