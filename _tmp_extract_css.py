import re
from pathlib import Path

t = Path(r"C:\laragon\bin\python\python-3.10\lib\site-packages\dash\dcc\async-dropdown.js").read_text(encoding="utf-8")
# embedded stylesheet string
for m in re.finditer(r"\.dash-dropdown-value[^\\]{0,300}", t):
    print(m.group(0).replace("\\n", "\n")[:300])
    print("---")
