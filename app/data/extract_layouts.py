"""Extrait les empreintes officielles (polygones, en pouces) des layouts du Event Companion.
Usage: python extract_layouts.py companion.pdf out.json
Repère: origine = coin haut-gauche du plateau tel que dessiné sur la page (attaquant en haut), 44x60."""
import sys, re, json, pdfplumber

def board_box(p):
    # le plateau est l'image la plus grande qui n'est pas le fond de page
    imgs = [i for i in p.images if i['width'] > 300 and i['width'] < 400 and i['height'] > 400]
    if not imgs: return None
    i = imgs[0]
    return i['x0'], i['top'], i['width'], i['height']

def grey(o):
    return o.get('fill') and str(o.get('non_stroking_color'))[:22] == '(0.0, 0.0, 0.0, 0.2)'

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
        shapes = []
        for o in p.curves + p.rects:
            if not grey(o): continue
            pts = o.get('pts') or []
            poly = [[round((x - bx) / s, 2), round((y - by) / s, 2)] for x, y in pts]
            shapes.append({'bbox': [round((o['x0'] - bx) / s, 2), round((o['top'] - by) / s, 2),
                                    round(o['width'] / s, 2), round(o['height'] / s, 2)], 'poly': poly})
        out.append({'page': n, 'layout': m.group(1), 'head': head, 'scale_pt_per_in': round(s, 3), 'footprints': shapes})
    return out

if __name__ == '__main__':
    data = extract(sys.argv[1])
    json.dump(data, open(sys.argv[2], 'w'), ensure_ascii=False)
    print(len(data), 'layouts')
