import unittest,hashlib
from pathlib import Path
import template_preview_assets
class TemplatePreviewTests(unittest.TestCase):
 def test_original_and_pdf_are_paired(self):
  m=template_preview_assets.validate(Path(__file__).resolve().parents[1]);self.assertGreaterEqual(m['pages'],1)
 def test_viewer_does_not_replace_report_generator(self):
  root=Path(__file__).resolve().parents[1];js=(root/'frontend/features/reports/template-reference.js').read_text(encoding='utf-8-sig');self.assertIn("/media/namyangju-template.pdf",js);self.assertIn("getPage(templatePage)",js);self.assertNotIn("previewHandoverReport=",js)
