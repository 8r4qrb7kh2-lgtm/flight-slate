import importlib
import unittest


EDITOR_MODULE_CANDIDATES = (
    "ui_lab.editor_document",
    "ui_lab.editor_renderer",
)


def load_editor_module():
    for module_name in EDITOR_MODULE_CANDIDATES:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
    raise unittest.SkipTest(
        "Editor document module is not implemented yet; expected one of: "
        + ", ".join(EDITOR_MODULE_CANDIDATES)
    )


class EditorDocumentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_editor_module()

    def test_document_round_trip_preserves_core_fields(self):
        module = self.module
        document_cls = getattr(module, "EditorDocument", None)
        self.assertIsNotNone(document_cls, "Expected EditorDocument to be exported")

        document = document_cls(
            width=128,
            height=64,
            background="#081018",
            elements=[
                {
                    "id": "background",
                    "type": "rect",
                    "x": 0,
                    "y": 0,
                    "width": 128,
                    "height": 64,
                    "fill": "#081018",
                },
                {
                    "id": "headline",
                    "type": "text",
                    "x": 8,
                    "y": 8,
                    "width": 72,
                    "height": 18,
                    "text": "FLIGHT SLATE",
                    "color": "#f2f8ff",
                    "wrap": "clip",
                },
                {
                    "id": "progress",
                    "type": "progress",
                    "x": 8,
                    "y": 40,
                    "width": 64,
                    "height": 8,
                    "value": 0.625,
                    "fill": "#5ee1ff",
                },
            ],
        )

        payload = document.to_dict()
        restored = document_cls.from_dict(payload)

        self.assertEqual(restored.width, 128)
        self.assertEqual(restored.height, 64)
        self.assertEqual(restored.background, "#081018")
        self.assertEqual(len(restored.elements), 3)
        self.assertEqual(restored.to_dict(), payload)

    def test_document_rejects_invalid_canvas_size(self):
        module = self.module
        document_cls = getattr(module, "EditorDocument", None)
        self.assertIsNotNone(document_cls, "Expected EditorDocument to be exported")

        with self.assertRaises((ValueError, TypeError)):
            document_cls(width=0, height=64, background="#081018", elements=[])

        with self.assertRaises((ValueError, TypeError)):
            document_cls(width=128, height=-1, background="#081018", elements=[])


if __name__ == "__main__":
    unittest.main()
