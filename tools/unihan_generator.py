import json
import re

mapping = {}
pattern = re.compile(r"^U\+([0-9A-F]+)\s+kCantonese\s+(.*)$")

with open("data/Unihan/Unihan_Readings.txt", encoding="utf-8") as f:
    for line in f:
        m = pattern.match(line)
        if m:
            codepoint = chr(int(m.group(1), 16))
            jyuts = [j.strip() for j in m.group(2).split()]
            mapping[codepoint] = jyuts

with open("data/Unihan/unihan_cantonese_chars.json", "w", encoding="utf-8") as out:
    json.dump(mapping, out, ensure_ascii=False, indent=2)