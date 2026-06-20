#!/usr/bin/env python3
"""
build_spa.py — 从本地源数据组装江西中考综合练习 SPA

源数据:
  rj8b: gen_question_bank_v2.py → rj8b_qdata.json + rj8b_cloze.json (可重新生成)
  jx:   jx_qdata.json (从 HTML checkpoint 提取)
  wy8a: wy8a_qdata.json (从 HTML checkpoint 提取)
  wy8b: wy8b_qdata.json (从 HTML checkpoint 提取)

解析嵌入:
  rj8b SC:    答案匹配 (rj8b_U*_grammar_explanations.json + rj8b_U*_vocab_logic_explanations.json)
  rj8b CLOZE: id匹配  (rj8b_cloze_explanations.json)

用法:
  python3 gen_question_bank_v2.py   # 重新生成 rj8b QDATA（可选，跳过则用已有文件）
  python3 build_spa.py              # 组装 SPA
"""
import json, os, re, sys, hashlib
from datetime import datetime

DIR = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(DIR)
HTML_PATH = os.path.join(DIR, '江西中考_综合练习.html')
CHECKPOINT_DIR = os.path.join(DIR, 'checkpoints')

# ================================================================
# 1. Load HTML template
# ================================================================
def load_html_template():
    with open(HTML_PATH) as f:
        html = f.read()
    var_start = html.find('var ALL_DATA = ')
    if var_start == -1:
        sys.exit("ALL_DATA not found in HTML")
    json_start = var_start + len('var ALL_DATA = ')
    depth = 0; json_end = -1
    for i in range(json_start, len(html)):
        if html[i] == '{': depth += 1
        elif html[i] == '}':
            depth -= 1
            if depth == 0: json_end = i + 1; break
    if json_end == -1:
        sys.exit("Cannot find end of ALL_DATA")
    return html, json_start, json_end

# ================================================================
# 2. Load source data
# ================================================================
def load_json(name):
    path = os.path.join(DIR, name)
    if not os.path.exists(path):
        print(f"  [SKIP] {name} not found")
        return None
    with open(path) as f:
        return json.load(f)

def load_rj8b():
    """Load freshly generated rj8b QDATA (from gen_question_bank_v2.py)."""
    qdata = load_json('rj8b_qdata.json')
    cloze = load_json('rj8b_cloze.json')
    if not qdata:
        sys.exit("rj8b_qdata.json not found. Run gen_question_bank_v2.py first.")
    # Build ALL_DATA compatible structure
    sc = {}
    for uid in qdata:
        unit_data = qdata[uid]
        sc[uid] = {
            'id': unit_data.get('id', uid),
            'n': unit_data.get('n', ''),
            'd': unit_data.get('d', ''),
            'dd': unit_data.get('dd', ''),
            'ps': 35,
            'q': unit_data['q'],
        }
    return {'sc': sc, 'cloze': cloze or []}

# ================================================================
# 3. Explanation matching (same proven approach as rebuild_spa.py)
# ================================================================
def extract_answer(exp_text):
    m = re.search(r'判定答案为\s*([^\n。]+)', exp_text)
    if m:
        ans = m.group(1).strip().rstrip('。；，,;')
        ans = re.sub(r'\s*【.*', '', ans).strip()
        return ans
    return None

def strip_option_prefix(opt):
    return re.sub(r'^[A-D][.、．]\s*', '', opt).strip()

def build_answer_to_exp_map():
    answer_to_exp = {}
    keyword_to_exp = {}

    for fname in sorted(os.listdir(DIR)):
        if not fname.endswith('_explanations.json') or 'cloze' in fname:
            continue
        if not fname.startswith('rj8b_'):
            continue
        with open(os.path.join(DIR, fname)) as f:
            data = json.load(f)
        for key, val in data.items():
            if not isinstance(val, dict):
                continue
            for qidx_str, exp_text in val.items():
                ans = extract_answer(exp_text)
                if ans and len(ans) < 50:
                    ans_lower = ans.lower().strip()
                    if ans_lower not in answer_to_exp:
                        answer_to_exp[ans_lower] = exp_text
                # keyword from 【考点定位】
                first_line = exp_text.split('\n')[0]
                m = re.search(r'——(\S+)', first_line)
                if m:
                    kw = re.sub(r'[（(].*', '', m.group(1)).strip().lower()
                    if kw and len(kw) > 1 and kw not in keyword_to_exp:
                        keyword_to_exp[kw] = exp_text

    print(f"  Explanation index: {len(answer_to_exp)} answer→exp, {len(keyword_to_exp)} keyword→exp")
    return answer_to_exp, keyword_to_exp

def match_question(q, answer_to_exp, keyword_to_exp):
    correct_idx = ord(q['a']) - 65
    if 0 <= correct_idx < len(q['o']):
        correct_opt = strip_option_prefix(q['o'][correct_idx]).lower().strip()
        if correct_opt in answer_to_exp:
            return answer_to_exp[correct_opt]

    stem_lower = q['s'].lower()
    for kw, exp in keyword_to_exp.items():
        if len(kw) > 2 and kw in stem_lower:
            return exp
    return None

def load_rj8b_direct_index():
    """Build direct index from rj8b explanation files: {unit_key: {qidx: exp_text}}."""
    rj8b_exp = {}
    for fname in sorted(os.listdir(DIR)):
        if not fname.startswith('rj8b_') or not fname.endswith('_explanations.json'):
            continue
        if 'cloze' in fname:
            continue
        with open(os.path.join(DIR, fname)) as f:
            data = json.load(f)
        for unit_key, val in data.items():
            if not isinstance(val, dict):
                continue
            # Normalize unit key: rj8b_U1_vocab -> rj8b_U1, rj8b_U1_logic -> rj8b_U1
            base_unit = re.sub(r'_(vocab|logic)$', '', unit_key)
            if base_unit not in rj8b_exp:
                rj8b_exp[base_unit] = {}
            for qidx_str, exp_text in val.items():
                rj8b_exp[base_unit][int(qidx_str)] = exp_text
    total = sum(len(v) for v in rj8b_exp.values())
    print(f"  rj8b direct index: {len(rj8b_exp)} units, {total} explanations")
    return rj8b_exp

def embed_rj8b_explanations(rj8b_data, answer_to_exp, keyword_to_exp):
    """Embed 4-part explanations into rj8b SC questions via direct index + answer matching."""
    rj8b_exp = load_rj8b_direct_index()
    updated = 0
    no_match = 0
    for uk in rj8b_data['sc']:
        unit_exp = rj8b_exp.get(uk, {})
        for i, q in enumerate(rj8b_data['sc'][uk]['q']):
            exp = None
            # Try direct index match first
            if i in unit_exp:
                exp = unit_exp[i]
            else:
                # Fall back to answer/keyword matching
                exp = match_question(q, answer_to_exp, keyword_to_exp)
            if exp:
                q['e'] = exp
                updated += 1
            else:
                no_match += 1
    print(f"  rj8b SC: {updated}/{updated + no_match} matched ({no_match} unmatched)")

def load_jx_explanations():
    """Load all jx_*_explanations.json into {unit_key: {qidx: exp_text}}."""
    jx_exp = {}
    for fname in sorted(os.listdir(DIR)):
        if not fname.startswith('jx_') or not fname.endswith('_explanations.json'):
            continue
        with open(os.path.join(DIR, fname)) as f:
            data = json.load(f)
        for unit_key, val in data.items():
            if isinstance(val, dict):
                if unit_key not in jx_exp:
                    jx_exp[unit_key] = {}
                for qidx_str, exp_text in val.items():
                    jx_exp[unit_key][int(qidx_str)] = exp_text
    total = sum(len(v) for v in jx_exp.values())
    print(f"  jx explanations loaded: {len(jx_exp)} units, {total} explanations")
    return jx_exp

def embed_jx_explanations(jx_data, jx_exp):
    """Embed 4-part explanations into jx SC questions via direct index matching."""
    updated = 0
    no_match = 0
    for uk in jx_data['sc']:
        unit_exp = jx_exp.get(uk, {})
        for i, q in enumerate(jx_data['sc'][uk]['q']):
            if i in unit_exp:
                q['e'] = unit_exp[i]
                updated += 1
            else:
                no_match += 1
    print(f"  jx SC: {updated}/{updated + no_match} matched ({no_match} unmatched)")

def embed_rj8b_cloze_explanations(rj8b_data):
    """Embed 4-part explanations into rj8b cloze passages."""
    cloze_exp = load_json('rj8b_cloze_explanations.json')
    if not cloze_exp:
        print("  rj8b cloze: no explanations file")
        return

    updated = 0
    for passage in rj8b_data['cloze']:
        pid = passage['id']
        if pid in cloze_exp:
            exp_list = cloze_exp[pid]
            passage['explain'] = exp_list
            updated += len(exp_list)
    print(f"  rj8b cloze: {updated} explanations embedded")

def embed_jx_cloze_explanations(jx_data):
    """Embed 4-part explanations into jx cloze passages."""
    cloze_exp = load_json('jx_cloze_explanations.json')
    if not cloze_exp:
        print("  jx cloze: no explanations file")
        return

    updated = 0
    for passage in jx_data['cloze']:
        pid = passage['id']
        if pid in cloze_exp:
            exp_list = cloze_exp[pid]
            passage['explain'] = exp_list
            updated += len(exp_list)
    print(f"  jx cloze: {updated} explanations embedded")

def load_wy_explanations(prefix):
    """Load all {prefix}_*_explanations.json into {unit_key: {qidx: exp_text}}."""
    wy_exp = {}
    for fname in sorted(os.listdir(DIR)):
        if not fname.startswith(f'{prefix}_') or not fname.endswith('_explanations.json'):
            continue
        if 'cloze' in fname:
            continue
        with open(os.path.join(DIR, fname)) as f:
            data = json.load(f)
        for unit_key, val in data.items():
            if isinstance(val, dict):
                if unit_key not in wy_exp:
                    wy_exp[unit_key] = {}
                for qidx_str, exp_text in val.items():
                    wy_exp[unit_key][int(qidx_str)] = exp_text
    total = sum(len(v) for v in wy_exp.values())
    print(f"  {prefix} SC explanations loaded: {len(wy_exp)} units, {total} explanations")
    return wy_exp

def embed_wy_sc_explanations(wy_data, wy_exp, label):
    """Embed 4-part explanations into wy SC questions via direct index matching."""
    updated = 0
    no_match = 0
    for uk in wy_data['sc']:
        unit_exp = wy_exp.get(uk, {})
        for i, q in enumerate(wy_data['sc'][uk]['q']):
            if i in unit_exp:
                q['e'] = unit_exp[i]
                updated += 1
            else:
                no_match += 1
    print(f"  {label} SC: {updated}/{updated + no_match} matched ({no_match} unmatched)")

def embed_wy_cloze_explanations(wy_data, prefix, label):
    """Embed 4-part explanations into wy cloze passages."""
    cloze_exp = load_json(f'{prefix}_cloze_explanations.json')
    if not cloze_exp:
        print(f"  {label} cloze: no explanations file")
        return

    updated = 0
    for passage in wy_data['cloze']:
        pid = passage['id']
        if pid in cloze_exp:
            exp_list = cloze_exp[pid]
            passage['explain'] = exp_list
            updated += len(exp_list)
    print(f"  {label} cloze: {updated} explanations embedded")

# ================================================================
# 4. Save checkpoint
# ================================================================
def save_checkpoint(html):
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(CHECKPOINT_DIR, f'江西中考_综合练习_{ts}.html')
    with open(path, 'w') as f:
        f.write(html)
    print(f"Checkpoint: {path}")
    return path

def build_access_map():
    """Read access_codes.txt, return {sha256_hex: label} dict."""
    path = os.path.join(DIR, 'access_codes.txt')
    if not os.path.exists(path):
        print("  [WARN] access_codes.txt not found, gate will have no valid codes")
        return {}
    access_map = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                label, code = parts
            else:
                label = code = parts[0]
            hash_hex = hashlib.sha256(code.encode('utf-8')).hexdigest()
            access_map[hash_hex] = label
    return access_map

DATA_OUTPUT_DIR = os.path.join(DIR, 'data')

# ================================================================
# 5. Main
# ================================================================
def main():
    print("=" * 50)
    print("build_spa.py — SPA Builder")
    print("=" * 50)

    # Load template
    print("\n[1/6] Loading HTML template...")
    html, json_start, json_end = load_html_template()
    print(f"  HTML: {len(html):,} bytes")

    # Load source data for all 4 versions
    print("\n[2/6] Loading source data...")
    all_data = {}

    # rj8b: fresh from gen_question_bank_v2.py
    print("  rj8b: from gen_question_bank_v2.py output")
    all_data['rj8b'] = load_rj8b()
    rj8b_sc = sum(len(all_data['rj8b']['sc'][uk]['q']) for uk in all_data['rj8b']['sc'])
    rj8b_cloze = len(all_data['rj8b']['cloze'])
    print(f"    {len(all_data['rj8b']['sc'])} SC units ({rj8b_sc} qs), {rj8b_cloze} cloze")

    # jx/wy8a/wy8b: from extracted JSON (checkpoint snapshots, distinct from gen_* output)
    for ver, fname in [('jx', 'jx_data.json'), ('wy8a', 'wy8a_data.json'), ('wy8b', 'wy8b_data.json')]:
        data = load_json(fname)
        if data:
            all_data[ver] = data
            sc_count = sum(len(data['sc'][uk]['q']) for uk in data['sc']) if 'sc' in data else 0
            cloze_count = len(data.get('cloze', []))
            print(f"  {ver}: {sc_count} SC qs, {cloze_count} cloze")
        else:
            print(f"  {ver}: MISSING — skipping")

    # Embed explanations
    print("\n[3/6] Embedding explanations...")
    answer_to_exp, keyword_to_exp = build_answer_to_exp_map()
    embed_rj8b_explanations(all_data['rj8b'], answer_to_exp, keyword_to_exp)
    embed_rj8b_cloze_explanations(all_data['rj8b'])

    jx_exp = load_jx_explanations()
    if jx_exp:
        embed_jx_explanations(all_data['jx'], jx_exp)

    embed_jx_cloze_explanations(all_data['jx'])

    # wy8a/wy8b explanations
    for prefix, label in [('wy8a', 'wy8a'), ('wy8b', 'wy8b')]:
        if prefix in all_data:
            wy_exp = load_wy_explanations(prefix)
            if wy_exp:
                embed_wy_sc_explanations(all_data[prefix], wy_exp, label)
            embed_wy_cloze_explanations(all_data[prefix], prefix, label)

    # Count total explanations
    total_4part = 0
    for ver in all_data:
        v = all_data[ver]
        if 'sc' in v:
            for uk in v['sc']:
                total_4part += sum(1 for q in v['sc'][uk]['q']
                                  if '【考点定位】' in q.get('e', '') and '【解题路径】' in q.get('e', ''))
        if 'cloze' in v:
            for p in v['cloze']:
                total_4part += sum(1 for e in p.get('explain', [])
                                  if '【考点定位】' in e and '【解题路径】' in e)
    print(f"  Total 4-part explanations: {total_4part}")

    # Generate access map
    print("\n[4/6] Generating access code hashes...")
    access_map = build_access_map()
    if access_map:
        print(f"  {len(access_map)} access code(s) hashed")
        for h, label in access_map.items():
            print(f"    {label}: {h[:12]}...")
    else:
        print("  No access codes configured")

    # Inject ACCESS_MAP into HTML
    # Pattern: // ACCESS_MAP_INJECTION_POINT\nvar ACCESS_MAP = {...};
    # Replace the ACCESS_MAP line while keeping the marker comment
    access_json = json.dumps(access_map, ensure_ascii=False, separators=(',', ':'))
    injection = f'// ACCESS_MAP_INJECTION_POINT\nvar ACCESS_MAP = {access_json};'
    html = re.sub(
        r'// ACCESS_MAP_INJECTION_POINT\nvar ACCESS_MAP = \{[^}]*\};',
        injection,
        html
    )
    print(f"  ACCESS_MAP injected into HTML")

    # Write per-version data files
    print("\n[5/6] Writing data files...")
    os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)
    for ver in ['rj8b', 'jx', 'wy8a', 'wy8b']:
        if ver in all_data:
            path = os.path.join(DATA_OUTPUT_DIR, f'{ver}.json')
            with open(path, 'w') as f:
                json.dump(all_data[ver], f, ensure_ascii=False, separators=(',', ':'))
            size = os.path.getsize(path)
            print(f"  data/{ver}.json: {size:,} bytes")

    # Save checkpoint of current version before overwrite
    print("\n[6/6] Saving HTML...")
    with open(HTML_PATH) as f:
        current = f.read()
    if current != html:
        save_checkpoint(current)
    else:
        print("  No changes from current version, skipping checkpoint")

    with open(HTML_PATH, 'w') as f:
        f.write(html)
    print(f"Output: {len(html):,} bytes → {HTML_PATH}")
    print("Done.")

if __name__ == '__main__':
    main()
