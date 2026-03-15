# TODO List

## High Priority

### Improve parsing of complex DOCX tables with schedules

**Problem:**
Documents such as university session/exam schedule files have a complex structure:
- Administrative header block (approval signatures, stamps)
- Merged cells in table headers
- The table header row is not in the first row
- The current algorithm incorrectly identifies the header row

**Current state:**
- 56 records are extracted (OK)
- But the headers are incorrect
- Result: useless chunks with repetitive text

**Possible solutions:**

1. **unstructured.io library** (recommended)
   ```bash
   pip install unstructured[docx]
   ```
   - Specializes in complex documents
   - Understands table structure
   - Automatically detects headers

2. **Analyze cell styles with python-docx**
   ```python
   if cell._element.get_or_add_tcPr().get_or_add_b():  # Bold = header
   ```
   - Headers are usually bold
   - Can also check font size

3. **Ask users to convert to XLSX**
   - Excel files are easier to parse
   - Fewer merged cells
   - Pandas handles XLSX very well

4. **Manual configuration for known formats**
   ```python
   # config.py
   SCHEDULE_FORMATS = {
       "exam_schedule": {
           "skip_rows": 5,  # skip the first 5 rows
           "header_keywords": ["date", "time", "group"]
       }
   }
   ```

**Interim workaround:**
Use simple parsing for regular documents; for schedules, recommend uploading in XLSX format.

---

## Medium Priority

### Other improvements
- Add TXT file support
- Improve PDF table parsing (tabula-py)
- Add extracted text preview in the UI

---

## Low Priority
- RTF file support
- Image support in documents (OCR)
