import sys

filename = sys.argv[1]

with open(filename, 'r') as file:
    source = file.read()
try:
    compile(source, filename, 'exec')
    print(f"Syntax OK in {filename}")
    sys.exit(0)
except SyntaxError as e:
    print(f"Syntax Error in {filename}: {e}")
    sys.exit(1)