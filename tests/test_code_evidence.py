import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from code_evidence import assert_article_code


class CodeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.doc = {"blocks": [{"type": "code", "code": "if x < 2:\n    go()\n\n    done()"}]}

    def test_preserves_entities_indentation_and_highlighting(self):
        assert_article_code(self.doc, '<pre><code><span>if</span> x &lt; 2:\n    go()\n\n    done()</code></pre>')

    def test_rejects_flattened_code(self):
        with self.assertRaises(AssertionError):
            assert_article_code(self.doc, '<pre><code>if x &lt; 2: go() done()</code></pre>')

    def test_rejects_code_only_in_paragraph_or_template(self):
        text = 'if x &lt; 2:\n    go()\n\n    done()'
        for html in [f'<p><code>{text}</code></p>', f'<template><pre><code>{text}</code></pre></template>']:
            with self.assertRaises(AssertionError):
                assert_article_code(self.doc, html)

    def test_each_duplicate_example_must_be_present(self):
        doc = {"blocks": [{"type": "code", "code": "x"}, {"type": "code", "code": "x"}]}
        with self.assertRaises(AssertionError):
            assert_article_code(doc, '<pre><code>x</code></pre>')

    def test_article_without_code_needs_no_code_markup(self):
        assert_article_code({"blocks": []}, '<p>Ordinary article.</p>')


if __name__ == "__main__":
    unittest.main()
