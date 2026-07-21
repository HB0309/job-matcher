import json

_VALID_JSON_ESCAPES = set('"\\\/bfnrtu')


def _fix_json_escapes(s: str) -> str:
    out: list[str] = []
    in_string = False
    i = 0
    while i < len(s):
        c = s[i]
        if not in_string:
            out.append(c)
            if c == '"':
                in_string = True
        elif c == '\\':
            nc = s[i + 1] if i + 1 < len(s) else ''
            if nc in _VALID_JSON_ESCAPES:
                out.append(c)
                out.append(nc)
                i += 2
                continue
            else:
                out.append('\\')
                out.append('\\')
        elif c == '"':
            in_string = False
            out.append(c)
        else:
            out.append(c)
        i += 1
    return ''.join(out)


cases = [
    ('single backslash (invalid)',  '{"k": "\\item bullet"}'),
    ('double backslash (valid)',     '{"k": "\\\\item bullet"}'),
    ('triple backslash',             '{"k": "\\\\\\item bullet"}'),
    ('\\% percent',                  '{"k": "98\\% accuracy"}'),
    ('valid \\n and \\t',            '{"k": "line\\nand\\ttab"}'),
    ('\\textbf mixed',               '{"k": "see \\textbf{98\\%}"}'),
    ('\\u valid unicode',            '{"k": "\\u0041 is A"}'),
]

for label, s in cases:
    fixed = _fix_json_escapes(s)
    try:
        result = json.loads(s)
        status = "already valid"
    except json.JSONDecodeError:
        try:
            result = json.loads(fixed)
            status = "FIXED"
        except json.JSONDecodeError as e:
            result = None
            status = f"STILL FAILS: {e}"
    print(f"{label:30s} | {status:15s} | value={result!r}")
