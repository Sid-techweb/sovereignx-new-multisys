import unittest
from app.chat.routing import ChatRoute, classify_route, is_document_scoped_message


class TestChatRoutingMatrix(unittest.TestCase):
    """
    Deterministic routing tests covering the manual validation matrix:
    GENERAL_CHAT must be the default for ordinary questions, even when a
    document happens to exist/be uploaded, unless the message is clearly
    document-scoped or a document is explicitly attached to the turn.
    """

    def test_general_knowledge_question_routes_general(self):
        self.assertEqual(classify_route("What is Python?"), ChatRoute.GENERAL_CHAT)

    def test_coding_request_routes_general(self):
        self.assertEqual(classify_route("Write a binary search algorithm"), ChatRoute.GENERAL_CHAT)

    def test_enterprise_topic_without_document_routes_general(self):
        self.assertEqual(classify_route("Explain OPC UA"), ChatRoute.GENERAL_CHAT)

    def test_predictive_maintenance_question_routes_general(self):
        self.assertEqual(classify_route("What is predictive maintenance?"), ChatRoute.GENERAL_CHAT)

    def test_explicit_pdf_reference_routes_document_rag(self):
        route = classify_route("What does the PDF say about pump P-101?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_summarize_uploaded_report_routes_document_rag(self):
        route = classify_route("Summarize the uploaded report")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_according_to_this_document_routes_document_rag(self):
        route = classify_route("According to this document, what is the temperature limit?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_lstm_question_with_pdf_uploaded_but_not_scoped_routes_general(self):
        # A PDF existing/being uploaded earlier in the conversation must not,
        # by itself, force RAG -- only an explicit attachment or document-
        # scoped phrasing should.
        route = classify_route("What is an LSTM?", attached_document_id=None)
        self.assertEqual(route, ChatRoute.GENERAL_CHAT)

    def test_hybrid_comparison_phrase_routes_document_rag(self):
        route = classify_route(
            "Compare the document's recommendation with general ML best practices"
        )
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_attached_pdf_document_routes_document_rag(self):
        route = classify_route(
            "What's in this?", attached_document_id="doc-1", attached_document_file_type="pdf"
        )
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_attached_image_document_routes_multimodal(self):
        route = classify_route(
            "What's in this?", attached_document_id="doc-2", attached_document_file_type="png"
        )
        self.assertEqual(route, ChatRoute.MULTIMODAL)

    def test_attached_document_overrides_general_phrasing(self):
        # Even an otherwise-general-sounding question, when a document is
        # explicitly attached to this turn, should be grounded in it.
        route = classify_route(
            "Explain this", attached_document_id="doc-3", attached_document_file_type="csv"
        )
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_empty_message_is_not_document_scoped(self):
        self.assertFalse(is_document_scoped_message(""))
        self.assertFalse(is_document_scoped_message(None))

    def test_case_insensitive_matching(self):
        route = classify_route("ACCORDING TO THE REPORT, what is the limit?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)


if __name__ == "__main__":
    unittest.main()
