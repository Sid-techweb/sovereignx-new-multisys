import unittest

from app.chat.arithmetic import is_arithmetic_request, extract_arithmetic_expression
from app.tools.calculation_verifier import evaluate_expression


class TestArithmeticExtraction(unittest.TestCase):
    """
    Deterministic-arithmetic detection/normalization -- exists so obvious
    calculation requests route to the existing safe AST evaluator
    (app/tools/calculation_verifier.py) instead of free-text LLM math.
    Verifies both that the right expression is extracted AND that it
    evaluates to the objectively correct numeric result.
    """

    def test_times_phrasing_evaluates_correctly(self):
        expr = extract_arithmetic_expression("What is 10384 times 827?")
        self.assertIsNotNone(expr)
        self.assertEqual(evaluate_expression(expr, {}), 10384 * 827)

    def test_trailing_instruction_does_not_break_extraction(self):
        expr = extract_arithmetic_expression("What is 10384 times 827? Explain the steps.")
        self.assertIsNotNone(expr)
        self.assertEqual(evaluate_expression(expr, {}), 10384 * 827)

    def test_calculate_symbolic_multiplication(self):
        expr = extract_arithmetic_expression("Calculate 45 * 92")
        self.assertIsNotNone(expr)
        self.assertEqual(evaluate_expression(expr, {}), 45 * 92)

    def test_percent_of(self):
        expr = extract_arithmetic_expression("What is 18% of 2400?")
        self.assertIsNotNone(expr)
        self.assertEqual(evaluate_expression(expr, {}), 0.18 * 2400)

    def test_add_list_with_thousands_separator_not_confused_with_list_comma(self):
        expr = extract_arithmetic_expression("Add 120, 450 and 991")
        self.assertIsNotNone(expr)
        self.assertEqual(evaluate_expression(expr, {}), 120 + 450 + 991)

    def test_parenthesized_expression(self):
        expr = extract_arithmetic_expression("Calculate (25 * 8) + 17")
        self.assertIsNotNone(expr)
        self.assertEqual(evaluate_expression(expr, {}), (25 * 8) + 17)

    def test_thousands_separator_number_still_parses(self):
        expr = extract_arithmetic_expression("Calculate 10,384 * 2")
        self.assertIsNotNone(expr)
        self.assertEqual(evaluate_expression(expr, {}), 10384 * 2)


class TestArithmeticRoutingGuard(unittest.TestCase):
    """False-positive guard: messages that merely mention numbers or math
    vocabulary must NOT be classified as arithmetic requests."""

    def test_explain_calculus_is_not_arithmetic(self):
        self.assertFalse(is_arithmetic_request("Explain calculus"))

    def test_what_is_machine_learning_is_not_arithmetic(self):
        self.assertFalse(is_arithmetic_request("What is machine learning?"))

    def test_conceptual_multiplication_question_is_not_arithmetic(self):
        self.assertFalse(is_arithmetic_request("How are multiplication and exponentiation different?"))

    def test_what_is_an_lstm_is_not_arithmetic(self):
        self.assertFalse(is_arithmetic_request("What is an LSTM?"))

    def test_message_with_incidental_digit_is_not_arithmetic(self):
        self.assertFalse(is_arithmetic_request("How much is a Tesla Model 3?"))

    def test_empty_message_is_not_arithmetic(self):
        self.assertFalse(is_arithmetic_request(""))
        self.assertFalse(is_arithmetic_request(None))

    def test_positive_cases_are_detected(self):
        for msg in [
            "What is 10384 times 827?",
            "Calculate 45 * 92",
            "What is 18% of 2400?",
            "Add 120, 450 and 991",
            "Calculate (25 * 8) + 17",
        ]:
            self.assertTrue(is_arithmetic_request(msg), msg)


if __name__ == "__main__":
    unittest.main()
