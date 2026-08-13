import unittest
from types import SimpleNamespace

from DatasetConverter.tokenizer_pipeline import TokenizedChunks
from DatasetConverter.tokenizer_pipeline import split_tokenized_context


class FakeEncoding:
    def __init__(self, tokens, spans):
        self._tokens = tokens
        self._spans = spans

    def tokens(self):
        return list(self._tokens)

    def token_to_chars(self, index):
        start, end = self._spans[index]
        return SimpleNamespace(start=start, end=end)


class FakeTokenizer:
    def __init__(self):
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        if text == "abcdef":
            return FakeEncoding(
                ["<s>", "ab", "cd", "ef", "</s>"],
                [None, (0, 2), (2, 4), (4, 6), None],
            )
        return FakeEncoding(["<s>", text, "</s>"], [None, (0, len(text)), None])


class TokenizerPipelineTests(unittest.TestCase):
    def test_splits_on_token_spans_without_boundary_overlap(self):
        result = split_tokenized_context(
            "abcdef", FakeTokenizer(), maximum_tokens=5
        )

        self.assertEqual(
            result,
            TokenizedChunks(chunks=("abcd", "ef"), retokenized=()),
        )

    def test_retokenizes_each_chunk_only_when_requested(self):
        tokenizer = FakeTokenizer()
        result = split_tokenized_context(
            "abcdef", tokenizer, maximum_tokens=5, retokenize=True
        )

        self.assertEqual(
            result.retokenized,
            (("<s>", "abcd", "</s>"), ("<s>", "ef", "</s>")),
        )
        self.assertEqual(tokenizer.calls, ["abcdef", "abcd", "ef"])

    def test_uses_existing_encoding_without_tokenizing_context_twice(self):
        tokenizer = FakeTokenizer()
        encoding = tokenizer("abcdef")

        result = split_tokenized_context(
            "abcdef",
            tokenizer,
            maximum_tokens=5,
            encoding=encoding,
        )

        self.assertEqual(result.chunks, ("abcd", "ef"))
        self.assertEqual(tokenizer.calls, ["abcdef"])

    def test_returns_empty_chunks_when_encoding_has_only_special_tokens(self):
        tokenizer = lambda text: FakeEncoding(["<s>", "</s>"], [None, None])

        self.assertEqual(
            split_tokenized_context("", tokenizer, maximum_tokens=5),
            TokenizedChunks(chunks=(), retokenized=()),
        )

    def test_rejects_budget_without_room_for_content_tokens(self):
        with self.assertRaisesRegex(
            ValueError, "maximum_tokens must be greater than reserved_tokens"
        ):
            split_tokenized_context("text", FakeTokenizer(), maximum_tokens=3)


if __name__ == "__main__":
    unittest.main()
