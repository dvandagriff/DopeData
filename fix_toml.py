with open("pyproject.toml") as f:
    content = f.read()

content = content.replace('requires-python = >=3.10', 'requires-python = ">=3.10"')

with open("pyproject.toml", "w") as f:
    f.write(content)

print("Fixed!")