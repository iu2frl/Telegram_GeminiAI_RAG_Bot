import unittest

from modules.helpers import sanitize_telegram_html


class TelegramHtmlTests(unittest.TestCase):
    def test_supported_tags_and_text_are_preserved(self):
        source = '<b>Answer</b> <i>carefully</i> <a href="https://example.com">source</a>'

        self.assertEqual(
            sanitize_telegram_html(source),
            '<b>Answer</b> <i>carefully</i> <a href="https://example.com">source</a>',
        )

    def test_literal_html_characters_are_escaped(self):
        source = "Use x < y and a > b; keep & intact."

        self.assertEqual(
            sanitize_telegram_html(source),
            "Use x &lt; y and a &gt; b; keep &amp; intact.",
        )

    def test_code_content_is_not_interpreted_as_html(self):
        source = '<pre><code>&lt;tag&gt; &amp; value</code></pre>'

        self.assertEqual(
            sanitize_telegram_html(source),
            '<pre><code>&lt;tag&gt; &amp; value</code></pre>',
        )

    def test_unsupported_tags_are_removed_without_losing_text(self):
        source = '<h1>Title</h1><br><u>Details</u>'

        self.assertEqual(
            sanitize_telegram_html(source),
            'Title<u>Details</u>',
        )

    def test_unsafe_link_attributes_are_removed(self):
        source = '<a href="javascript:alert(1)">click</a>'

        self.assertEqual(sanitize_telegram_html(source), '<a>click</a>')

    def test_nested_formatting_is_preserved(self):
        source = '<b>Important <i>detail</i></b>'

        self.assertEqual(
            sanitize_telegram_html(source),
            '<b>Important <i>detail</i></b>',
        )

    def test_supported_aliases_are_normalized(self):
        source = '<strong>bold</strong> <em>italic</em> <del>removed</del>'

        self.assertEqual(
            sanitize_telegram_html(source),
            '<b>bold</b> <i>italic</i> <s>removed</s>',
        )

    def test_link_attributes_other_than_safe_href_are_removed(self):
        source = '<a class="source" target="_blank" href="https://example.com/?q=&quot;x&quot;">source</a>'

        self.assertEqual(
            sanitize_telegram_html(source),
            '<a href="https://example.com/?q=&quot;x&quot;">source</a>',
        )

    def test_common_entities_are_not_double_escaped(self):
        source = '&lt;quoted&gt; &amp; &#39;value&#39;'

        self.assertEqual(
            sanitize_telegram_html(source),
            '&lt;quoted&gt; &amp; &#39;value&#39;',
        )

    def test_unclosed_tags_are_closed(self):
        source = '<b>unfinished response'

        self.assertEqual(sanitize_telegram_html(source), '<b>unfinished response</b>')


if __name__ == "__main__":
    unittest.main()
