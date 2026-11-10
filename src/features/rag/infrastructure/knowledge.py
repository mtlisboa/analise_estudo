import re
import unicodedata
from pathlib import Path


def documentation(query):
    path = Path(__file__).resolve().parents[1] / 'knowledge/manual.md'
    sections = path.read_text(encoding='utf-8').split('\n## ')
    def words(value):
        value = ''.join(c for c in unicodedata.normalize('NFD', value.lower()) if not unicodedata.combining(c))
        return {w[:-1] if w.endswith('s') else w for w in re.findall(r'\w{3,}', value)}
    terms = words(query) - {'como', 'para', 'uma', 'que', 'por', 'com', 'meu', 'minha', 'isso', 'qual', 'quero', 'devo', 'fazer'}
    scored = []
    for section in sections:
        title = section.splitlines()[0].lstrip('# ')
        score = 4 * len(terms & words(title)) + len(terms & words(section))
        if score:
            scored.append((score, title, section))
    scored.sort(key=lambda row: row[0], reverse=True)
    minimum = max(1, scored[0][0] / 2) if scored else 1
    return [{'source': 'Manual Lumini — ' + title, 'text': section[:900]}
            for score, title, section in scored[:2] if score >= minimum]




class FileKnowledge:
    def search(self, query):
        return documentation(query)
