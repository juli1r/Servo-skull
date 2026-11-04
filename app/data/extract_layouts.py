"""Extrait les empreintes officielles (polygones, en pouces) des layouts du Event Companion.
Usage: python extract_layouts.py companion.pdf out.json [ancien.json]
Repère: origine = coin haut-gauche du plateau tel que dessiné sur la page (attaquant en haut), 44x60.
Si [ancien.json] est fourni, les clés 'zones' (par layout) et 'trap' (par empreinte) de l'ancien
fichier sont reportées sur le nouveau (par page puis par bbox le plus proche) : ce script ne sait
pas les recalculer lui-même, seulement ajouter la lettre ('letter': AB/CD/EF/GH)."""
import sys, re, json, math, pdfplumber

LETTERS = ('AB', 'CD', 'EF', 'GH')

def board_box(p):
    # le plateau est l'image la plus grande qui n'est pas le fond de page
    imgs = [i for i in p.images if i['width'] > 300 and i['width'] < 400 and i['height'] > 400]
    if not imgs: return None
    i = imgs[0]
    return i['x0'], i['top'], i['width'], i['height']

def grey(o):
    return o.get('fill') and str(o.get('non_stroking_color'))[:22] == '(0.0, 0.0, 0.0, 0.2)'

def nearest_letter(cx, cy, labels):
    # labels: [(texte, cx, cy), ...] en coordonnées points PDF, mêmes unités que cx/cy
    if not labels: return None
    return min(labels, key=lambda l: (l[1] - cx) ** 2 + (l[2] - cy) ** 2)[0]

def extract(pdf_path):
    out = []
    pdf = pdfplumber.open(pdf_path)
    for n, p in enumerate(pdf.pages, 1):
        t = p.extract_text() or ''
        m = re.search(r'LAYOUT ([ABC])', t)
        if not m: continue
        bb = board_box(p)
        if not bb: continue
        bx, by, bw, bh = bb
        s = bw / 44.0
        lines = [l.strip() for l in t.splitlines() if l.strip()]
        # titres: "<DISPOSITION> VS <DISPOSITION>" + missions
        head = ' | '.join(lines[:14])
        labels = [(w['text'], (w['x0'] + w['x1']) / 2, (w['top'] + w['bottom']) / 2)
                  for w in p.extract_words() if w['text'] in LETTERS]
        shapes = []
        for o in p.curves + p.rects:
            if not grey(o): continue
            pts = o.get('pts') or []
            poly = [[round((x - bx) / s, 2), round((y - by) / s, 2)] for x, y in pts]
            cx, cy = o['x0'] + o['width'] / 2, o['top'] + o['height'] / 2
            shapes.append({'bbox': [round((o['x0'] - bx) / s, 2), round((o['top'] - by) / s, 2),
                                    round(o['width'] / s, 2), round(o['height'] / s, 2)], 'poly': poly,
                           'letter': nearest_letter(cx, cy, labels)})
        out.append({'page': n, 'layout': m.group(1), 'head': head, 'scale_pt_per_in': round(s, 3), 'footprints': shapes})
    return out

def carry_over(data, old_path):
    """Reporte 'zones' (par page) et 'trap' (par empreinte, bbox le plus proche) depuis un ancien
    JSON déjà extrait, que ce script ne sait pas recalculer (logique perdue, non committée)."""
    old = {l['page']: l for l in json.load(open(old_path, encoding='utf-8'))}
    for l in data:
        ol = old.get(l['page'])
        if not ol: continue
        if 'zones' in ol:
            l['zones'] = ol['zones']
        of = ol.get('footprints') or []
        for f in l['footprints']:
            if not of: break
            near = min(of, key=lambda o: math.hypot(o['bbox'][0] - f['bbox'][0], o['bbox'][1] - f['bbox'][1]))
            if near.get('trap') is not None:
                f['trap'] = near['trap']
    return data

if __name__ == '__main__':
    data = extract(sys.argv[1])
    if len(sys.argv) > 3:
        data = carry_over(data, sys.argv[3])
    json.dump(data, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False)
    print(len(data), 'layouts')
