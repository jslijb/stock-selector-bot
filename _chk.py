import ast
files = [
    'D:/Python/agent_a_sk/src/data/daily_basic_local.py',
    'D:/Python/agent_a_sk/src/data/schema.py',
    'D:/Python/agent_a_sk/src/scheduler.py',
]
for f in files:
    with open(f, 'r', encoding='utf-8') as fh:
        ast.parse(fh.read())
    print(f'OK: {f}')
