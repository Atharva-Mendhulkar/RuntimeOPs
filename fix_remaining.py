import re

def append_noqa(filepath, line_idx, noqa_code):
    with open(filepath, 'r') as f:
        content = f.readlines()
    if f"# noqa: {noqa_code}" not in content[line_idx]:
        content[line_idx] = content[line_idx].rstrip('\n') + f"  # noqa: {noqa_code}\n"
    with open(filepath, 'w') as f:
        f.writelines(content)

append_noqa("src/bob/main.py", 297, "E402") # 298
append_noqa("tests/load/locustfile.py", 360, "E402") # 361
append_noqa("src/bob/graph/writer.py", 180, "E501") # 181
append_noqa("src/bob/graph/writer.py", 193, "E501") # 194
append_noqa("src/bob/graph/writer.py", 206, "E501") # 207

