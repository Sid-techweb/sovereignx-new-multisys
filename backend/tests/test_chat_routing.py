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


class TestDocumentScopedPhraseVariations(unittest.TestCase):
    """
    Regression coverage for the "according to the uploaded document" routing
    gap: the original patterns matched "according to the document" but not
    "according to the uploaded document" (an extra uploaded/attached modifier
    between the determiner and the noun). Fixed via a shared document-
    reference grammar in routing.py rather than one-off literal sentences --
    these tests exercise that grammar across natural phrasings, not just the
    one reported sentence.
    """

    def test_according_to_uploaded_document(self):
        route = classify_route("According to the uploaded document, what is the maximum operating temperature?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_according_to_this_uploaded_document(self):
        route = classify_route("According to this uploaded document, what is the limit?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_according_to_the_pdf(self):
        route = classify_route("According to the PDF, what is the pressure rating?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_according_to_the_uploaded_pdf(self):
        route = classify_route("According to the uploaded PDF, summarize the findings.")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_based_on_the_uploaded_report(self):
        route = classify_route("Based on the uploaded report, what should I do?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_based_on_this_report(self):
        route = classify_route("Based on this report, what is recommended?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_from_the_document_i_uploaded(self):
        route = classify_route("From the document I uploaded, what is the spec?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_what_does_the_uploaded_file_say(self):
        route = classify_route("What does the uploaded file say about maintenance intervals?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_summarize_the_uploaded_document(self):
        route = classify_route("Summarize the uploaded document.")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_what_does_this_pdf_say(self):
        route = classify_route("What does this PDF say?")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_using_the_attached_report(self):
        route = classify_route("Using the attached report, calculate the downtime.")
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)

    def test_lstm_question_still_general_chat(self):
        # The exact false-positive guard the fix must not regress.
        self.assertEqual(classify_route("What is an LSTM?"), ChatRoute.GENERAL_CHAT)

    def test_generic_file_mention_stays_general_chat(self):
        # "file" alone (no determiner+uploaded modifier) is too ambiguous in a
        # technical assistant's chat to force RAG.
        route = classify_route("What is in the file structure of this repo?")
        self.assertEqual(route, ChatRoute.GENERAL_CHAT)

    def test_documentary_word_boundary_stays_general_chat(self):
        # "documentary" must not match the "document" noun as a substring.
        route = classify_route("Tell me about the documentary I watched last night.")
        self.assertEqual(route, ChatRoute.GENERAL_CHAT)

    def test_uploading_word_boundary_stays_general_chat(self):
        # "uploading" must not match the "upload" noun as a substring.
        route = classify_route("I am uploading a new file to the server.")
        self.assertEqual(route, ChatRoute.GENERAL_CHAT)


if __name__ == "__main__":
    unittest.main()
