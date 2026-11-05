import json,glob,sys
for p in sorted(glob.glob(f'templates/{sys.argv[1]}@*.json')):
    t=json.load(open(p)); print('##',t['formular_id'],t['wer_fuellt_aus'])
    for x in t['felder']:
        print(f"{x['page']} {x['typ'][:5]:5} {str(x['acro_name'] or x['feld_id'])[:28]:28} | {str(x['label_wörtlich'])[:50]:50} | {x['semantik']} {x['wer']} {'M' if x['michi_fuellt'] else ''}", (' opts:'+','.join(f"{o['wert']}={str(o.get('label'))[:12]}" for o in x['optionen'])) if x.get('optionen') and x['typ']!='auswahl' else '')
