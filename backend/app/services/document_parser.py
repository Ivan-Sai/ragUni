import io
import logging
from zipfile import BadZipFile

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError
from docx import Document as DocxDocument
import pandas as pd

logger = logging.getLogger(__name__)


class DocumentParser:
    """Parser for different document formats"""

    @staticmethod
    async def parse_pdf(file_content: bytes) -> str:
        """Parse PDF file and extract text."""
        try:
            pdf_file = io.BytesIO(file_content)
            pdf_reader = PdfReader(pdf_file)

            text_parts = []
            for page_num, page in enumerate(pdf_reader.pages, 1):
                text = page.extract_text()
                if text:
                    text_parts.append(f"--- Page {page_num} ---\n{text}\n")

            return "\n".join(text_parts)

        except PdfReadError as e:
            logger.warning("Invalid or corrupted PDF file: %s", type(e).__name__)
            raise ValueError("Could not parse PDF file. The file may be corrupted or encrypted.")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Error reading PDF: %s", type(e).__name__)
            raise ValueError("Could not read PDF file.")

    @staticmethod
    async def parse_docx(file_content: bytes) -> str:
        """Parse DOCX file and extract text."""
        try:
            docx_file = io.BytesIO(file_content)
            doc = DocxDocument(docx_file)

            text_parts = []

            # Extract paragraphs
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            # Extract tables
            for table in doc.tables:
                table_text = []
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells)
                    if row_text:
                        table_text.append(row_text)

                if table_text:
                    text_parts.append("\n--- Table ---")
                    text_parts.extend(table_text)
                    text_parts.append("--- End of table ---\n")

            return "\n\n".join(text_parts)

        except BadZipFile:
            logger.warning("Invalid DOCX file (bad ZIP structure)")
            raise ValueError("Could not parse DOCX file. The file may be corrupted.")
        except (KeyError, OSError) as e:
            logger.warning("Error reading DOCX: %s", type(e).__name__)
            raise ValueError("Could not read DOCX file.")

    @staticmethod
    async def parse_xlsx(file_content: bytes) -> str:
        """Parse XLSX file and extract text."""
        try:
            xlsx_file = io.BytesIO(file_content)
            excel_file = pd.ExcelFile(xlsx_file)

            text_parts = []

            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)

                text_parts.append(f"\n--- Sheet: {sheet_name} ---")

                # Replace NaN with empty string
                df = df.fillna('')

                # Create header
                header = " | ".join(str(col) for col in df.columns)
                text_parts.append(header)
                text_parts.append("-" * len(header))

                # Add rows
                for _, row in df.iterrows():
                    row_text = " | ".join(str(val) for val in row.values)
                    text_parts.append(row_text)

                text_parts.append(f"--- End of sheet {sheet_name} ---\n")

            return "\n".join(text_parts)

        except BadZipFile:
            logger.warning("Invalid XLSX file (bad ZIP structure)")
            raise ValueError("Could not parse XLSX file. The file may be corrupted.")
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
            logger.warning("Error parsing XLSX data: %s", type(e).__name__)
            raise ValueError("Could not parse spreadsheet data.")
        except (KeyError, OSError) as e:
            logger.warning("Error reading XLSX: %s", type(e).__name__)
            raise ValueError("Could not read XLSX file.")

    @classmethod
    async def parse_file(cls, file_content: bytes, file_type: str) -> str:
        """Parse file based on its type."""
        file_type = file_type.lower()

        if file_type == "pdf":
            return await cls.parse_pdf(file_content)
        elif file_type == "docx":
            return await cls.parse_docx(file_content)
        elif file_type == "xlsx":
            return await cls.parse_xlsx(file_content)
        elif file_type == "txt":
            text = file_content.decode("utf-8", errors="replace")
            if "\ufffd" in text:
                logger.warning("File contains invalid UTF-8 characters that were replaced")
            return text
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
