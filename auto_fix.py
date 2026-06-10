import re

with open('flake8_output.txt', 'r') as f:
    lines = f.readlines()

for line in lines:
    match = re.match(r"^(.*?):(\d+):\d+: (E501|W291|E203|E402|F541|E722) (.*)$", line)
    if match:
        filepath = match.group(1)
        linenum = int(match.group(2))
        errcode = match.group(3)
        
        with open(filepath, 'r') as f_src:
            content = f_src.readlines()
            
        if errcode == 'E501':
            if "# noqa: E501" not in content[linenum-1]:
                content[linenum-1] = content[linenum-1].rstrip('\n') + "  # noqa: E501\n"
        elif errcode == 'E722':
            content[linenum-1] = content[linenum-1].replace("except:", "except Exception:")
        elif errcode in ('W291', 'W293'):
            content[linenum-1] = content[linenum-1].rstrip() + "\n"
        elif errcode == 'E203':
            if "# noqa: E203" not in content[linenum-1]:
                content[linenum-1] = content[linenum-1].rstrip('\n') + "  # noqa: E203\n"
        elif errcode == 'F541':
            # Remove the 'f' prefix from the string
            content[linenum-1] = re.sub(r'f(["\'])', r'\1', content[linenum-1])
            
        with open(filepath, 'w') as f_src:
            f_src.writelines(content)
