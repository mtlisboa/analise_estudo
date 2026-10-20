from collections import Counter
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .variants import assign_student_variants, make_variants


class PhysicalDistributionTests(SimpleTestCase):
    def members(self, count):
        return [SimpleNamespace(user_id=i, classroom_id=1 if i % 2 else 2,
            user=SimpleNamespace(username=f'aluno-{i}', get_full_name=lambda i=i: f'Aluno {i:02}'))
            for i in range(count, 0, -1)]

    def test_ten_and_eleven_students_follow_global_alphabetical_cycle(self):
        for count, expected in [(10, {'A': 4, 'B': 3, 'C': 3}), (11, {'A': 4, 'B': 4, 'C': 3})]:
            with self.subTest(count=count):
                members = self.members(count)
                assigned = assign_student_variants(members)
                self.assertEqual(Counter(assigned.values()), expected)
                for member in members:
                    self.assertEqual(assigned[member.classroom_id, member.user_id],
                                     'ABC'[(member.user_id - 1) % 3])
                self.assertEqual(assigned, assign_student_variants(reversed(members)))

    def test_accents_do_not_put_alvaro_after_bruno(self):
        members = [
            SimpleNamespace(user_id=1, classroom_id=1,
                user=SimpleNamespace(username='bruno', get_full_name=lambda: 'Bruno')),
            SimpleNamespace(user_id=2, classroom_id=1,
                user=SimpleNamespace(username='alvaro', get_full_name=lambda: 'Álvaro')),
        ]
        self.assertEqual(assign_student_variants(members), {(1, 2): 'A', (1, 1): 'B'})

    def test_versions_have_distinct_patterns_and_verification_keys(self):
        questions = [{'id': 1, 'type': 'multiple_choice',
            'options': ['Correta', 'Errada 1', 'Errada 2'], 'correct': 'A'}]
        variants = make_variants(questions, 'distribution-test', True, True)
        self.assertEqual(len({tuple(q['correct'] for q in rows) for rows in variants.values()}), 3)
        self.assertEqual(len({tuple(tuple(q['options']) for q in rows) for rows in variants.values()}), 3)
        for rows in variants.values():
            self.assertEqual(rows[0]['options']['ABCDE'.index(rows[0]['correct'])], 'Correta')
        self.assertEqual(variants, make_variants(questions, 'distribution-test', True, True))

    def test_impossible_distinct_keys_are_rejected(self):
        with self.assertRaises(ValidationError):
            make_variants([{'id': 1, 'type': 'multiple_choice',
                'options': ['Correta', 'Errada'], 'correct': 'A'}], 'too-small', True, True)
