import unittest

from exporters import ExportedArtifact
from extractors import ExtractedPayload
from transformers import TransformResult


class PipelinePackageTests(unittest.TestCase):
    def test_pipeline_contract_packages_are_importable(self) -> None:
        extracted = ExtractedPayload(source_type="sample", payload={"ok": True}, metadata={"field": None})
        transformed = TransformResult(transactions=[{"name": "Example", "frequency": None}])
        exported = ExportedArtifact(name="sample.csv", media_type="text/csv", content="name\nExample\n")

        self.assertEqual(extracted.metadata["field"], None)
        self.assertEqual(transformed.transactions[0]["frequency"], None)
        self.assertEqual(exported.media_type, "text/csv")
