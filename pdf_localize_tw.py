#!/usr/bin/env python3
import json
import os
import re
from collections import Counter
from pathlib import Path

import fitz
from opencc import OpenCC

ROOT = Path(__file__).resolve().parent


def load_dotenv(path: Path = ROOT / '.env') -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()
SRC = Path(os.environ['PDF_SOURCE']).expanduser()
DST = Path(os.environ['PDF_OUTPUT']).expanduser()
REGULAR_FONT = os.environ['PDF_REGULAR_FONT']
BOLD_FONT = os.environ.get('PDF_BOLD_FONT', REGULAR_FONT)
ALLOW_OVERWRITE = os.environ.get('PDF_OVERWRITE', 'false').lower() in {'1', 'true', 'yes'}
CJK_RE = re.compile(r'[\u3400-\u9fff]')
CYRILLIC_RE = re.compile(r'[\u0400-\u04ff]')
cc = OpenCC('s2twp')

CUSTOM_TERMS = [
    ('乙太網埠', '乙太網路連接埠'),
    ('以太網埠', '乙太網路連接埠'),
    ('以太網', '乙太網路'),
    ('數字量輸入', '數位輸入'),
    ('數字量', '數位'),
    ('二維碼', 'QR Code'),
    ('檔案資源管理器', '檔案總管'),
    ('文件資源管理器', '檔案總管'),
    ('客戶端', '用戶端'),
    ('端子塊', '端子台'),
    ('通訊端口', '通訊連接埠'),
    ('通訊埠', '通訊連接埠'),
    ('端口', '連接埠'),
    ('除錯', '試運轉'),
    ('調試', '試運轉'),
    ('在線', '線上'),
    ('接口', '介面'),
    ('激活', '啟用'),
    ('存儲', '儲存'),
    ('接入點', '存取點'),
    ('傳感器', '感測器'),
    ('射頻合規聲明', '射頻法規遵循聲明'),
    ('輸入特性', '輸入規格'),
    ('機械特性', '機械規格'),
    ('觸點', '接點'),
    ('部件', '零件'),
    ('幹接點', '乾接點'),
    ('電位接點', '帶電接點'),
    ('比如', '例如'),
    ('注：', '註：'),
    ('運行序列號', '流水序號'),
    ('星期幾', '星期幾'),
]


def localize(text: str) -> str:
    out = cc.convert(text)
    for old, new in CUSTOM_TERMS:
        out = out.replace(old, new)
    out = re.sub(r'乙太網(?!路)', '乙太網路', out)
    out = out.replace(' RJ45 埠', ' RJ45 連接埠')
    out = out.replace('Modbus 埠', 'Modbus 連接埠')
    out = out.replace('埠 -', '連接埠 -')
    out = out.replace('\uf032\uf034 \uf056c', '24 Vdc')
    out = out.replace('Ethernet 電纜', '乙太網路纜線')
    out = out.replace('乙太網路電纜', '乙太網路纜線')
    out = out.replace('乙太網路LED', '乙太網路 LED')
    out = out.replace('外部天線埠', '外接天線連接埠')
    out = out.replace('正常運行', '正常運作')
    out = out.replace('請訪問網站', '請造訪網站')
    out = out.replace('請保管好此說明書以供將來使用。',
                      '請妥善保存本說明書，以供日後參考。')
    out = out.replace('以下載上述', '下載上述')
    out = out.replace('檔案(使用者指南', '文件（使用者指南')
    out = out.replace(')和其他檔案。', '）及其他文件。')
    out = out.replace('對於透過乾接點實現的數位輸入，需要使用 24 Vdc 外部電源。',
                      '使用乾接點作為數位輸入時，需要外接 24 Vdc 電源。')
    out = out.replace('對於透過帶電接點實現的數位輸入，不需要使用 24 Vdc 外部電源。例如，',
                      '使用帶電接點作為數位輸入時，不需要外接 24 Vdc 電源。例如，')
    out = re.sub(r'文件（使用者指南.*?）及其他文件。',
                 '文件（使用者指南）及其他文件。', out)
    if '使用者指南' in out and ('其他文件' in out or '其他檔案' in out):
        out = '文件（使用者指南）及其他文件。'
    # Standalone/common document headings.
    if out.strip() == '特性':
        out = out.replace('特性', '規格')
    return out


def pdf_color(value: int):
    return (((value >> 16) & 255) / 255.0,
            ((value >> 8) & 255) / 255.0,
            (value & 255) / 255.0)


def dominant_background(pix, rect, scale=2.0):
    x0 = max(0, int(rect.x0 * scale))
    y0 = max(0, int(rect.y0 * scale))
    x1 = min(pix.width, max(x0 + 1, int(rect.x1 * scale)))
    y1 = min(pix.height, max(y0 + 1, int(rect.y1 * scale)))
    samples = []
    stride = max(1, int(scale))
    n = pix.n
    data = pix.samples
    for y in range(y0, y1, stride):
        row = y * pix.stride
        for x in range(x0, x1, stride):
            i = row + x * n
            samples.append(tuple(data[i:i+3]))
    if not samples:
        return (1.0, 1.0, 1.0)
    # Quantize slightly so anti-aliased pixels do not dominate.
    q = [tuple((v // 8) * 8 for v in rgb) for rgb in samples]
    rgb = Counter(q).most_common(1)[0][0]
    if min(rgb) >= 224:
        return (1.0, 1.0, 1.0)
    return tuple(v / 255.0 for v in rgb)


def is_bold(span):
    return bool(span.get('flags', 0) & 16) or 'Bold' in span.get('font', '')


if DST.exists() and not ALLOW_OVERWRITE:
    raise SystemExit(f'Output already exists: {DST}. Set PDF_OVERWRITE=true to replace it.')
if DST.exists():
    DST.unlink()

doc = fitz.open(SRC)
regular = fitz.Font(fontfile=REGULAR_FONT)
bold = fitz.Font(fontfile=BOLD_FONT)
report = []

for page_no, page in enumerate(doc, start=1):
    original_pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    replacements = []
    data = page.get_text('dict')

    for block in data.get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            spans = line.get('spans', [])
            if not spans:
                continue
            full = ''.join(s.get('text', '') for s in spans)
            if not CJK_RE.search(full):
                continue

            # Preserve the existing Taiwan legal notice on page 17 verbatim.
            if page_no == 17 and not ('射频合规声明' in full or '注：仅适用于' in full):
                continue

            multilingual_header = bool(CYRILLIC_RE.search(full)) or full.count('/') >= 3

            if multilingual_header:
                # Only replace Chinese spans in multilingual headings.
                for s in spans:
                    old = s.get('text', '')
                    if not CJK_RE.search(old):
                        continue
                    new = localize(old)
                    if new == old:
                        continue
                    replacements.append({
                        'old': old, 'new': new,
                        'rect': fitz.Rect(s['bbox']),
                        'origin': fitz.Point(s['origin']),
                        'size': float(s['size']),
                        'bold': is_bold(s),
                        'color': pdf_color(int(s['color'])),
                    })
            else:
                # Rebuild from the first Chinese span to the line end. This keeps
                # bullets/prefixes in place while preventing gaps when a Chinese
                # sentence contains URLs, model names, units, or English terms.
                first = next(i for i, s in enumerate(spans)
                             if CJK_RE.search(s.get('text', '')))
                selected = spans[first:]
                old = ''.join(s.get('text', '') for s in selected)
                new = localize(old)
                if new == old:
                    continue
                first_span = selected[0]
                rect = fitz.Rect(
                    min(s['bbox'][0] for s in selected),
                    min(s['bbox'][1] for s in selected),
                    max(s['bbox'][2] for s in selected),
                    max(s['bbox'][3] for s in selected),
                )
                # The source places a small User Guide link icon below this
                # page-1 line. Cover its descender area when replacing the line.
                if page_no == 1 and '用户指南' in old:
                    rect.y1 += 3.5
                replacements.append({
                    'old': old, 'new': new,
                    'rect': rect,
                    'origin': fitz.Point(first_span['origin']),
                    'size': float(first_span['size']),
                    'bold': is_bold(first_span),
                    'color': pdf_color(int(first_span['color'])),
                })

    if not replacements:
        continue

    # Paint over the exact target regions instead of PDF redaction. Redaction
    # removes an entire neighboring text span when two span boxes merely touch,
    # which caused the missing URLs, model names, units, and field prefixes in
    # the first revision. A visual overlay preserves every adjacent object.
    for item in replacements:
        item['bg'] = dominant_background(original_pix, item['rect'])
        page.draw_rect(item['rect'], color=None, fill=item['bg'], overlay=True)
    if page_no == 1:
        # The source User Guide icon is a separate "U G" text span that
        # slightly exceeds the Chinese line box. Cover it before reinserting.
        page.draw_rect(fitz.Rect(490.5, 519.8, 503.2, 530.2),
                       color=None, fill=(1, 1, 1), overlay=True)

    page.insert_font(fontname='TWRegular', fontfile=REGULAR_FONT)
    page.insert_font(fontname='TWBold', fontfile=BOLD_FONT)
    for item in replacements:
        font = bold if item['bold'] else regular
        fontsize = item['size']
        available = max(1.0, item['rect'].x1 - item['origin'].x)
        width = font.text_length(item['new'], fontsize=fontsize)
        if width > available:
            fontsize = max(item['size'] * 0.72, fontsize * available / width * 0.98)
        page.insert_text(
            item['origin'], item['new'], fontsize=fontsize,
            fontname='TWBold' if item['bold'] else 'TWRegular',
            color=item['color'], overlay=True,
        )
        report.append({
            'page': page_no, 'old': item['old'], 'new': item['new'],
            'font_size': round(fontsize, 2),
            'bbox': [round(v, 2) for v in item['rect']],
        })

doc.save(DST, garbage=4, deflate=True, clean=True)
doc.close()
print(json.dumps({
    'output': str(DST),
    'replacements': len(report),
    'pages_changed': sorted(set(x['page'] for x in report)),
    'examples': [x for x in report if any(k in x['new'] for k in
                 ('乙太網路', '數位輸入', '使用者指南', '檔案總管', '試運轉'))][:20],
}, ensure_ascii=False, indent=2))
